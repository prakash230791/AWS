"""
effort_matrix.py
Core effort calculation engine for Azure SQL MI → Aurora PostgreSQL migration.
Reads the YAML configuration and computes workstream-level and total estimates.
"""

import yaml
from pathlib import Path
from typing import Dict, List, Tuple
from models import (
    ComplexityBand,
    ProjectProfile,
    WorkstreamEstimate,
    MigrationEstimate,
)

CONFIG_PATH = Path(__file__).parent / "config" / "assessment_config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Complexity band resolution helpers
# ---------------------------------------------------------------------------

def _resolve_band(value: int | float, thresholds: dict) -> ComplexityBand:
    """Return the complexity band for a numeric value given threshold config."""
    if value <= thresholds["simple"]["max"]:
        return ComplexityBand.SIMPLE
    if value <= thresholds["medium"]["max"]:
        return ComplexityBand.MEDIUM
    if value <= thresholds["complex"]["max"]:
        return ComplexityBand.COMPLEX
    return ComplexityBand.VERY_COMPLEX


def _band_score(band: ComplexityBand) -> int:
    return {"simple": 1, "medium": 2, "complex": 3, "very_complex": 4}[band.value]


# ---------------------------------------------------------------------------
# Feature score computation
# ---------------------------------------------------------------------------

def compute_tsql_feature_score(profile: ProjectProfile, config: dict) -> Tuple[float, List[str]]:
    """
    Sum up the T-SQL feature weights for features enabled in the profile.
    Returns (total_score, list_of_active_feature_labels).
    """
    weights = config["tsql_feature_weights"]
    score = 0.0
    active: List[str] = []

    feature_map = {
        "cursors":                  profile.uses_cursors,
        "linked_servers":           profile.uses_linked_servers,
        "xml_data_type":            profile.uses_xml_data_type,
        "full_text_search":         profile.uses_full_text_search,
        "spatial_data":             profile.uses_spatial_data,
        "clr_assemblies":           profile.uses_clr_assemblies,
        "replication":              profile.uses_replication,
        "service_broker":           profile.uses_service_broker,
        "reporting_services":       profile.uses_ssrs_reports,
        "sql_agent_jobs":           profile.uses_sql_agent_jobs,
        "temp_tables":              profile.uses_temp_tables,
        "table_valued_parameters":  profile.uses_tvp,
        "json_support":             profile.uses_json_support,
        "dynamic_sql":              profile.uses_dynamic_sql,
        "merge_statement":          profile.uses_merge_statement,
        "cte_recursive":            profile.uses_recursive_cte,
        "partition_tables":         profile.uses_partition_tables,
        "row_level_security":       profile.uses_row_level_security,
        "always_encrypted":         profile.uses_always_encrypted,
        "indexed_views":            profile.uses_indexed_views,
        "computed_columns":         profile.uses_computed_columns,
        "hierarchyid":              profile.uses_hierarchyid,
        "filestream":               profile.uses_filestream,
        "openquery":                profile.uses_openquery,
        "identity_columns":         profile.uses_identity_columns,
        "nolock_hints":             profile.uses_nolock_hints,
        "error_handling":           profile.uses_error_handling,
    }

    for key, enabled in feature_map.items():
        if enabled and key in weights:
            score += weights[key]["weight"]
            active.append(weights[key]["description"])

    return score, active


def compute_datatype_score(profile: ProjectProfile, config: dict) -> Tuple[float, List[str]]:
    """Sum data type migration weights for types used in the schema."""
    weights = config["datatype_migration_weights"]
    score = 0.0
    active: List[str] = []

    dtype_map = {
        "uniqueidentifier":  profile.uses_dt_uniqueidentifier,
        "xml":               profile.uses_dt_xml,
        "geography":         profile.uses_dt_geography,
        "geometry":          profile.uses_dt_geometry,
        "hierarchyid":       profile.uses_dt_hierarchyid,
        "sql_variant":       profile.uses_dt_sql_variant,
        "varbinary_max":     profile.uses_dt_varbinary_max,
        "image":             profile.uses_dt_image,
        "text_ntext":        profile.uses_dt_text_ntext,
        "money":             profile.uses_dt_money,
        "rowversion":        profile.uses_dt_rowversion,
    }

    for key, enabled in dtype_map.items():
        if enabled and key in weights:
            entry = weights[key]
            score += entry["weight"]
            active.append(f"{key.upper()} → {entry['pg_equivalent']} ({entry['note']})")

    return score, active


# ---------------------------------------------------------------------------
# Overall complexity band
# ---------------------------------------------------------------------------

def determine_overall_complexity(
    profile: ProjectProfile,
    tsql_score: float,
    dtype_score: float,
    config: dict,
) -> Tuple[ComplexityBand, float]:
    """
    Compute a weighted composite complexity score across all dimensions.
    Returns (ComplexityBand, raw_score).
    """
    thresholds = config["complexity_thresholds"]

    # Per-dimension bands
    tbl_band  = _resolve_band(profile.num_tables,               thresholds["tables"])
    sp_band   = _resolve_band(profile.num_stored_procedures,    thresholds["stored_procedures"])
    trg_band  = _resolve_band(profile.num_triggers,             thresholds["triggers"])
    view_band = _resolve_band(profile.num_views,                thresholds["views"])
    size_band = _resolve_band(profile.database_size_gb,         thresholds["database_size_gb"])
    app_band  = _resolve_band(profile.num_connected_applications, thresholds["connected_applications"])

    # Weighted score (higher weight = bigger complexity driver)
    raw = (
        _band_score(tbl_band)  * 2.0 +   # tables
        _band_score(sp_band)   * 3.0 +   # stored procedures — biggest driver
        _band_score(trg_band)  * 1.5 +
        _band_score(view_band) * 1.0 +
        _band_score(size_band) * 1.5 +
        _band_score(app_band)  * 1.5 +
        (tsql_score / 20.0)   * 3.0 +   # normalised T-SQL feature score
        (dtype_score / 20.0)  * 1.5
    )

    # Normalise to 1–4 scale (1=simple, 4=very_complex)
    max_possible = (4 * 2.0) + (4 * 3.0) + (4 * 1.5) + (4 * 1.0) + (4 * 1.5) + (4 * 1.5) + (10 * 3.0 / 20.0 * 3.0) + (10 * 1.5)
    normalised   = (raw / max_possible) * 4.0

    if normalised < 1.2:
        band = ComplexityBand.SIMPLE
    elif normalised < 2.2:
        band = ComplexityBand.MEDIUM
    elif normalised < 3.2:
        band = ComplexityBand.COMPLEX
    else:
        band = ComplexityBand.VERY_COMPLEX

    return band, round(normalised, 2)


# ---------------------------------------------------------------------------
# Workstream-level complexity overrides
# ---------------------------------------------------------------------------

def _workstream_band(
    ws_id: str,
    overall: ComplexityBand,
    profile: ProjectProfile,
    tsql_score: float,
) -> Tuple[ComplexityBand, List[str]]:
    """
    Some workstreams have a complexity that differs from the overall band.
    Returns (band, notes).
    """
    notes: List[str] = []

    # SP/Functions/Triggers: driven primarily by procedure count + T-SQL score
    if ws_id == "sp_functions_triggers":
        total_routines = profile.num_stored_procedures + profile.num_functions + profile.num_triggers
        if total_routines == 0:
            return ComplexityBand.SIMPLE, ["No stored procedures, functions, or triggers found"]
        if total_routines > 300 or tsql_score > 80:
            band = ComplexityBand.VERY_COMPLEX
        elif total_routines > 100 or tsql_score > 40:
            band = ComplexityBand.COMPLEX
        elif total_routines > 20:
            band = ComplexityBand.MEDIUM
        else:
            band = ComplexityBand.SIMPLE

        if profile.uses_clr_assemblies:
            if band.value in ("simple", "medium"):
                band = ComplexityBand.COMPLEX
            notes.append("CLR assemblies detected – significant rewrite required (no CLR in Aurora PG)")
        if profile.uses_service_broker:
            notes.append("Service Broker detected – no direct equivalent; redesign with SQS/SNS needed")
        if profile.uses_cursors:
            notes.append("Cursor usage detected – refactor to set-based PL/pgSQL logic")
        return band, notes

    # Data migration: driven by size and number of databases
    if ws_id == "data_migration":
        if profile.database_size_gb > 2000 or profile.num_databases > 5:
            band = ComplexityBand.VERY_COMPLEX
        elif profile.database_size_gb > 500 or profile.num_databases > 2:
            band = ComplexityBand.COMPLEX
        elif profile.database_size_gb > 100:
            band = ComplexityBand.MEDIUM
        else:
            band = ComplexityBand.SIMPLE

        if profile.uses_replication:
            notes.append("Replication enabled – DMS CDC setup needed; extended testing required")
        if profile.num_databases > 1:
            notes.append(f"{profile.num_databases} databases detected on MI – multi-DB migration adds effort")
        return band, notes

    # Application changes: driven by number of apps + ORM usage
    if ws_id == "application_changes":
        if profile.num_connected_applications > 15 or profile.uses_ssis_packages:
            band = ComplexityBand.VERY_COMPLEX
        elif profile.num_connected_applications > 7:
            band = ComplexityBand.COMPLEX
        elif profile.num_connected_applications > 2:
            band = ComplexityBand.MEDIUM
        else:
            band = ComplexityBand.SIMPLE

        if profile.uses_orm:
            notes.append(f"ORM detected ({', '.join(profile.orm_names)}) – driver + dialect config changes required")
        if profile.uses_ssis_packages:
            notes.append("SSIS packages detected – rewrite as AWS Glue ETL jobs")
        if profile.uses_ssas:
            notes.append("SSAS detected – evaluate AWS Redshift or Athena for analytical workloads")
        return band, notes

    # Infrastructure: fairly standard but scales with HA/compliance
    if ws_id == "infrastructure_setup":
        if profile.high_availability_required and profile.compliance_requirements:
            band = ComplexityBand.COMPLEX
        elif profile.high_availability_required or profile.multiple_environments:
            band = ComplexityBand.MEDIUM
        else:
            band = ComplexityBand.SIMPLE
        if profile.multiple_environments:
            notes.append("Multiple environments (Dev/QA/Staging/Prod) multiply infra effort")
        return band, notes

    # Security/compliance workstream
    if ws_id == "security_compliance":
        if profile.compliance_requirements and profile.uses_always_encrypted:
            band = ComplexityBand.VERY_COMPLEX
            notes.append("Always Encrypted + compliance requirements – AWS KMS and app-layer changes needed")
        elif profile.compliance_requirements:
            band = ComplexityBand.COMPLEX
            notes.append(f"Compliance: {', '.join(profile.compliance_frameworks)}")
        elif profile.uses_row_level_security:
            band = ComplexityBand.MEDIUM
            notes.append("Row-level security – reimplement with PostgreSQL RLS policies")
        else:
            band = ComplexityBand.SIMPLE
        return band, notes

    # Testing: scales with overall complexity
    if ws_id == "testing_validation":
        if overall == ComplexityBand.VERY_COMPLEX or profile.zero_downtime_cutover:
            band = ComplexityBand.VERY_COMPLEX
        else:
            band = overall
        if profile.zero_downtime_cutover:
            notes.append("Zero-downtime cutover – additional CDC validation and rehearsal cycles required")
        if profile.parallel_run_required:
            notes.append("Parallel run required – dual-write/read validation increases test scope")
        return band, notes

    # Cutover planning
    if ws_id == "cutover_planning":
        if profile.zero_downtime_cutover:
            band = ComplexityBand.VERY_COMPLEX
            notes.append("Zero-downtime cutover – live CDC sync, dual-endpoint routing, rehearsals")
        elif overall in (ComplexityBand.COMPLEX, ComplexityBand.VERY_COMPLEX):
            band = ComplexityBand.COMPLEX
        else:
            band = ComplexityBand.MEDIUM
        return band, notes

    # Default: inherit overall complexity
    return overall, notes


# ---------------------------------------------------------------------------
# Global multipliers
# ---------------------------------------------------------------------------

def compute_global_multiplier(profile: ProjectProfile, config: dict) -> Tuple[float, List[str]]:
    """Apply global multipliers from the config based on profile flags."""
    multipliers = config["global_multipliers"]
    combined = 1.0
    notes: List[str] = []

    flag_map = {
        "high_availability_required":          profile.high_availability_required,
        "compliance_requirements":             profile.compliance_requirements,
        "zero_downtime_cutover":               profile.zero_downtime_cutover,
        "multiple_environments":               profile.multiple_environments,
        "parallel_run_required":               profile.parallel_run_required,
        "third_party_etl_tools":               profile.use_aws_dms_sct,
        "experienced_team":                    profile.team_has_migration_experience,
        "no_documentation_available":          not profile.documentation_available,
        "active_development_during_migration": profile.active_development_during_migration,
    }

    for key, enabled in flag_map.items():
        if enabled and key in multipliers:
            entry  = multipliers[key]
            factor = entry["factor"]
            combined *= factor
            direction = "+" if factor > 1.0 else "-"
            pct = abs(round((factor - 1.0) * 100))
            notes.append(f"{direction}{pct}% – {entry['description']}")

    return round(combined, 4), notes


# ---------------------------------------------------------------------------
# MI-specific risk flags
# ---------------------------------------------------------------------------

def generate_mi_risk_flags(profile: ProjectProfile) -> List[str]:
    """Generate risk flags specific to Azure SQL Managed Instance features."""
    flags: List[str] = []

    if profile.uses_clr_assemblies:
        flags.append(
            "CRITICAL: CLR assemblies are not supported in Aurora PostgreSQL. "
            "All CLR objects must be rewritten in PL/pgSQL, Python, or moved to application layer."
        )
    if profile.uses_service_broker:
        flags.append(
            "HIGH: Service Broker has no Aurora PostgreSQL equivalent. "
            "Redesign with Amazon SQS + SNS or AWS EventBridge."
        )
    if profile.uses_linked_servers:
        flags.append(
            "HIGH: Linked servers are not supported in Aurora PostgreSQL. "
            "Replace with postgres_fdw extension, dblink, or application-level orchestration."
        )
    if profile.uses_replication:
        flags.append(
            "HIGH: SQL Server replication topology must be fully redesigned. "
            "Consider AWS DMS continuous replication or Aurora PostgreSQL logical replication."
        )
    if profile.uses_sql_agent_jobs:
        flags.append(
            "MEDIUM: SQL Server Agent jobs must be migrated to AWS EventBridge Scheduler, "
            "AWS Lambda, or pg_cron extension."
        )
    if profile.uses_filestream:
        flags.append(
            "HIGH: FILESTREAM/FileTable is not supported. "
            "Migrate binary data to Amazon S3; update application references."
        )
    if profile.uses_always_encrypted:
        flags.append(
            "HIGH: Always Encrypted column-level encryption must be replaced with "
            "AWS KMS client-side encryption or pgcrypto."
        )
    if profile.num_databases > 1:
        flags.append(
            f"MEDIUM: {profile.num_databases} databases on MI — Aurora PostgreSQL is single-database per cluster. "
            "Cross-database queries must be rewritten using schema separation or multiple Aurora clusters."
        )
    if profile.uses_cross_db_queries or profile.cross_database_queries:
        flags.append(
            "HIGH: Cross-database queries detected. Aurora PostgreSQL uses single-database model; "
            "refactor with postgres_fdw or schema consolidation."
        )
    if profile.uses_full_text_search:
        flags.append(
            "MEDIUM: Full-text search (CONTAINS/FREETEXT) must be replaced with "
            "PostgreSQL tsvector/tsquery or Amazon OpenSearch Service."
        )
    if profile.uses_spatial_data:
        flags.append(
            "MEDIUM: Spatial data types (Geography/Geometry) require PostGIS extension on Aurora PostgreSQL. "
            "Function signatures and coordinate system handling differ."
        )
    if profile.uses_dt_sql_variant:
        flags.append(
            "HIGH: SQL_VARIANT data type has no PostgreSQL equivalent. "
            "Columns must be redesigned with proper typed alternatives."
        )
    if profile.uses_ssas:
        flags.append(
            "MEDIUM: SSAS cubes/tabular models — evaluate migration to Amazon Redshift, "
            "AWS Glue + Athena, or Aurora ML for analytical workloads."
        )
    if profile.uses_ssis_packages:
        flags.append(
            "MEDIUM: SSIS packages must be migrated to AWS Glue ETL jobs or Step Functions workflows."
        )
    if profile.active_development_during_migration:
        flags.append(
            "HIGH: Active schema development during migration greatly increases risk. "
            "Establish a schema freeze policy or use branch-based migration strategy."
        )

    return flags


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

def generate_recommendations(profile: ProjectProfile) -> List[str]:
    """Generate actionable migration recommendations."""
    recs: List[str] = []

    recs.append(
        "Run AWS Schema Conversion Tool (SCT) against the MI source to generate a detailed "
        "Database Migration Assessment Report before finalising estimates."
    )
    if profile.num_stored_procedures + profile.num_functions > 50:
        recs.append(
            "Prioritise stored procedure conversion early — this is typically the longest workstream. "
            "Consider AWS SCT automated conversion + manual review cycle."
        )
    if profile.uses_clr_assemblies:
        recs.append(
            "Inventory all CLR assemblies and classify by: (a) rewrite in PL/pgSQL, "
            "(b) move to AWS Lambda functions, or (c) use PostgreSQL extensions."
        )
    if profile.database_size_gb > 500:
        recs.append(
            f"Database size {profile.database_size_gb:.0f} GB — use AWS DMS full-load with parallel tables "
            "and a subsequent CDC phase to minimise cutover window."
        )
    if not profile.team_has_migration_experience:
        recs.append(
            "Engage AWS Professional Services or a certified migration partner with Azure SQL MI → "
            "Aurora PostgreSQL experience to accelerate delivery and reduce risk."
        )
    if profile.zero_downtime_cutover:
        recs.append(
            "Zero-downtime cutover: implement AWS DMS CDC, validate latency SLA, "
            "perform at least two full cutover rehearsals before go-live."
        )
    if profile.uses_spatial_data:
        recs.append(
            "Enable PostGIS extension on Aurora PostgreSQL cluster and validate spatial "
            "function equivalents (ST_Distance, ST_Contains, etc.) early in the project."
        )
    if profile.num_databases > 1:
        recs.append(
            f"Plan database consolidation strategy for {profile.num_databases} source databases — "
            "evaluate schema-based separation vs. separate Aurora clusters per workload."
        )
    recs.append(
        "Establish a performance baseline on Azure SQL MI using Query Store before migration. "
        "Use pg_stat_statements and AWS Performance Insights post-migration for comparison."
    )
    recs.append(
        "Consider Amazon Aurora Babelfish if a phased migration approach is preferred — "
        "Babelfish allows T-SQL wire protocol compatibility while fully running on Aurora PostgreSQL."
    )

    return recs


# ---------------------------------------------------------------------------
# Main estimation function
# ---------------------------------------------------------------------------

def estimate(profile: ProjectProfile) -> MigrationEstimate:
    """Run the full estimation and return a MigrationEstimate object."""
    config = load_config()

    tsql_score, tsql_features = compute_tsql_feature_score(profile, config)
    dtype_score, dtype_features = compute_datatype_score(profile, config)
    overall_band, complexity_score = determine_overall_complexity(
        profile, tsql_score, dtype_score, config
    )
    global_multiplier, multiplier_notes = compute_global_multiplier(profile, config)
    mi_flags = generate_mi_risk_flags(profile)
    recommendations = generate_recommendations(profile)

    workstreams: List[WorkstreamEstimate] = []
    matrix = config["workstream_effort_matrix"]

    for ws_id, ws_cfg in matrix.items():
        ws_band, ws_notes = _workstream_band(ws_id, overall_band, profile, tsql_score)

        base = float(ws_cfg[ws_band.value])
        risk_buffer = round(base * (ws_cfg["risk_buffer_pct"] / 100.0), 1)
        total = round(base + risk_buffer, 1)

        ws = WorkstreamEstimate(
            workstream_id=ws_id,
            label=ws_cfg["label"],
            description=ws_cfg["description"],
            complexity_band=ws_band,
            base_effort_days=base,
            risk_buffer_days=risk_buffer,
            total_effort_days=total,
            notes=ws_notes,
        )
        workstreams.append(ws)

    return MigrationEstimate(
        project_name=profile.project_name,
        client_name=profile.client_name,
        prepared_by=profile.prepared_by,
        overall_complexity=overall_band,
        complexity_score=complexity_score,
        workstreams=workstreams,
        global_multiplier=global_multiplier,
        multiplier_notes=multiplier_notes,
        contingency_pct=20.0,
        mi_specific_notes=tsql_features + dtype_features,
        risk_flags=mi_flags,
        recommendations=recommendations,
    )
