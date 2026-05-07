#!/usr/bin/env python3
"""
estimator.py
CLI entry point for the Azure SQL Managed Instance → AWS Aurora PostgreSQL
Migration Effort Estimator.

Usage:
    # Run with a JSON project profile:
    python estimator.py --input sample_inputs/sample_project.json

    # Interactive wizard mode:
    python estimator.py --interactive

    # Generate both HTML and JSON outputs:
    python estimator.py --input sample_inputs/sample_project.json --format both

    # Custom output path:
    python estimator.py --input sample_inputs/sample_project.json --output /tmp/my_report
"""

import argparse
import json
import sys
from pathlib import Path
from dataclasses import asdict

from models import ProjectProfile
from effort_matrix import estimate
from report_generator import generate_html, export_json


# ---------------------------------------------------------------------------
# Profile loading
# ---------------------------------------------------------------------------

def load_profile_from_json(path: str) -> ProjectProfile:
    """Load a ProjectProfile from a JSON file."""
    with open(path, "r") as f:
        data = json.load(f)

    profile = ProjectProfile()
    for key, value in data.items():
        if hasattr(profile, key):
            setattr(profile, key, value)
        else:
            print(f"  [!] Unknown field in input JSON: '{key}' — ignored")
    return profile


# ---------------------------------------------------------------------------
# Interactive wizard
# ---------------------------------------------------------------------------

def ask_bool(prompt: str, default: bool = False) -> bool:
    default_str = "Y/n" if default else "y/N"
    ans = input(f"  {prompt} [{default_str}]: ").strip().lower()
    if ans in ("y", "yes"):
        return True
    if ans in ("n", "no"):
        return False
    return default


def ask_int(prompt: str, default: int = 0) -> int:
    ans = input(f"  {prompt} [{default}]: ").strip()
    try:
        return int(ans) if ans else default
    except ValueError:
        return default


def ask_float(prompt: str, default: float = 0.0) -> float:
    ans = input(f"  {prompt} [{default}]: ").strip()
    try:
        return float(ans) if ans else default
    except ValueError:
        return default


def ask_str(prompt: str, default: str = "") -> str:
    ans = input(f"  {prompt} [{default}]: ").strip()
    return ans if ans else default


def run_interactive_wizard() -> ProjectProfile:
    print("\n" + "=" * 70)
    print("  Azure SQL MI → AWS Aurora PostgreSQL — Migration Effort Estimator")
    print("=" * 70)
    print("  Answer the questions below. Press ENTER to accept the default.\n")

    profile = ProjectProfile()

    # Project metadata
    print("── Project Information ─────────────────────────────────────────────")
    profile.project_name = ask_str("Project name",  "Azure SQL MI Migration")
    profile.client_name  = ask_str("Client name",   "Client")
    profile.prepared_by  = ask_str("Prepared by",   "Migration Team")

    # Schema inventory
    print("\n── Schema Inventory ────────────────────────────────────────────────")
    profile.num_tables            = ask_int("Number of tables",                 50)
    profile.num_stored_procedures = ask_int("Number of stored procedures",      20)
    profile.num_functions         = ask_int("Number of user-defined functions",  5)
    profile.num_triggers          = ask_int("Number of triggers",               10)
    profile.num_views             = ask_int("Number of views",                  15)
    profile.num_indexes           = ask_int("Number of non-clustered indexes",   30)
    profile.num_constraints       = ask_int("Number of FK/check/unique constraints", 60)
    profile.num_databases         = ask_int("Number of databases on the MI instance", 1)

    # Data characteristics
    print("\n── Data Characteristics ────────────────────────────────────────────")
    profile.database_size_gb      = ask_float("Total database size (GB)",  50.0)
    profile.largest_table_rows_m  = ask_float("Largest table size (millions of rows)", 1.0)

    # Azure SQL MI specific features
    print("\n── Azure SQL MI Specific Features ──────────────────────────────────")
    print("  (These are features available in SQL MI but not Azure SQL Database)")
    profile.uses_clr_assemblies      = ask_bool("CLR assemblies used?")
    profile.uses_sql_agent_jobs      = ask_bool("SQL Server Agent jobs used?")
    profile.uses_service_broker      = ask_bool("Service Broker used?")
    profile.uses_linked_servers      = ask_bool("Linked servers used?")
    profile.uses_replication         = ask_bool("SQL Server replication used?")
    profile.cross_database_queries   = ask_bool("Cross-database queries used?")
    profile.uses_database_mail       = ask_bool("Database Mail (sp_send_dbmail) used?")

    # T-SQL features
    print("\n── T-SQL Feature Usage ─────────────────────────────────────────────")
    profile.uses_cursors             = ask_bool("Cursors used?")
    profile.uses_xml_data_type       = ask_bool("XML data type or FOR XML used?")
    profile.uses_full_text_search    = ask_bool("Full-text search (CONTAINS/FREETEXT)?")
    profile.uses_spatial_data        = ask_bool("Spatial data (Geography/Geometry)?")
    profile.uses_json_support        = ask_bool("JSON functions (FOR JSON, JSON_VALUE)?")
    profile.uses_dynamic_sql         = ask_bool("Dynamic SQL (EXEC / sp_executesql)?")
    profile.uses_merge_statement     = ask_bool("MERGE (upsert) statements?")
    profile.uses_recursive_cte       = ask_bool("Recursive CTEs?")
    profile.uses_partition_tables    = ask_bool("Table partitioning?")
    profile.uses_row_level_security  = ask_bool("Row-level security?")
    profile.uses_always_encrypted    = ask_bool("Always Encrypted columns?")
    profile.uses_indexed_views       = ask_bool("Indexed (materialised) views?")
    profile.uses_computed_columns    = ask_bool("Persisted computed columns?")
    profile.uses_hierarchyid         = ask_bool("HierarchyID data type?")
    profile.uses_filestream          = ask_bool("FILESTREAM / FileTable?")
    profile.uses_temp_tables         = ask_bool("Heavy temp table usage?")
    profile.uses_tvp                 = ask_bool("Table-Valued Parameters (TVPs)?")
    profile.uses_nolock_hints        = ask_bool("WITH(NOLOCK) hints?")

    # Data types
    print("\n── Non-Standard Data Types ─────────────────────────────────────────")
    profile.uses_dt_uniqueidentifier = ask_bool("UNIQUEIDENTIFIER columns?")
    profile.uses_dt_xml              = ask_bool("XML columns?")
    profile.uses_dt_geography        = ask_bool("Geography / Geometry spatial columns?")
    profile.uses_dt_sql_variant      = ask_bool("SQL_VARIANT columns?")
    profile.uses_dt_varbinary_max    = ask_bool("VARBINARY(MAX) / IMAGE columns?")
    profile.uses_dt_money            = ask_bool("MONEY / SMALLMONEY columns?")
    profile.uses_dt_rowversion       = ask_bool("ROWVERSION / TIMESTAMP columns?")

    # Application layer
    print("\n── Application Layer ───────────────────────────────────────────────")
    profile.num_connected_applications = ask_int("Number of applications connecting to the database", 1)
    apps_str = ask_str("Application languages (comma-separated, e.g. C#, Java)", "")
    profile.app_languages = [a.strip() for a in apps_str.split(",") if a.strip()]
    profile.uses_orm     = ask_bool("ORM framework used?")
    if profile.uses_orm:
        orm_str = ask_str("ORM name(s) (e.g. Entity Framework, Hibernate)", "")
        profile.orm_names = [o.strip() for o in orm_str.split(",") if o.strip()]
    profile.uses_ssrs_reports = ask_bool("SSRS reports query database directly?")
    profile.uses_ssas         = ask_bool("SSAS (Analysis Services) cubes used?")
    profile.uses_ssis_packages = ask_bool("SSIS packages used?")

    # Non-functional requirements
    print("\n── Non-Functional Requirements ─────────────────────────────────────")
    profile.high_availability_required = ask_bool("High availability required (Multi-AZ)?", True)
    profile.compliance_requirements    = ask_bool("Compliance requirements (HIPAA/PCI/SOC2/GDPR)?")
    if profile.compliance_requirements:
        cf_str = ask_str("Which frameworks? (comma-separated)", "")
        profile.compliance_frameworks = [f.strip() for f in cf_str.split(",") if f.strip()]
    profile.zero_downtime_cutover   = ask_bool("Zero-downtime cutover required (<1hr RTO)?")
    profile.multiple_environments   = ask_bool("Multiple environments (Dev/QA/Staging/Prod)?", True)
    profile.parallel_run_required   = ask_bool("Parallel run (side-by-side) required?")
    profile.use_aws_dms_sct         = ask_bool("Using AWS DMS + SCT tools?", True)
    profile.team_has_migration_experience = ask_bool("Team has prior Azure SQL→Aurora PG experience?")
    profile.documentation_available = ask_bool("Schema/code documentation available?", True)
    profile.active_development_during_migration = ask_bool("Active development will continue during migration?")

    return profile


# ---------------------------------------------------------------------------
# Console report printer
# ---------------------------------------------------------------------------

def print_summary(result) -> None:
    W = 70
    print("\n" + "=" * W)
    print(f"  MIGRATION EFFORT ESTIMATE — {result.project_name}")
    print("=" * W)
    print(f"  Overall Complexity : {result.overall_complexity.label} "
          f"(score {result.complexity_score}/4.0)")
    print(f"  Global Multiplier  : {result.global_multiplier:.2f}x")
    print()
    print(f"  {'Workstream':<42} {'Band':<13} {'Days':>6}")
    print("  " + "-" * 62)
    for ws in result.workstreams:
        print(f"  {ws.label:<42} {ws.complexity_band.label:<13} {ws.total_effort_days:>6.1f}")
    print("  " + "-" * 62)
    print(f"  {'Sub-total':<42} {'':13} {result.subtotal_days:>6.1f}")
    print(f"  {'After global multiplier':<42} {'':13} {result.adjusted_days:>6.1f}")
    print(f"  {'Contingency (20%)':<42} {'':13} {result.contingency_days:>6.1f}")
    print("  " + "=" * 62)
    print(f"  {'TOTAL':<42} {'':13} {result.total_days:>6.1f}  days")
    print(f"  {'':42} {'':13} {result.total_weeks:>6.1f}  weeks")
    print(f"  {'':42} {'':13} {result.total_months:>6.1f}  months")
    print("  " + "=" * 62)
    print(f"\n  Optimistic : {result.optimistic_days:.0f}d  |  "
          f"Most Likely : {result.total_days:.0f}d  |  "
          f"Pessimistic : {result.pessimistic_days:.0f}d")

    if result.multiplier_notes:
        print("\n  Global Modifiers Applied:")
        for note in result.multiplier_notes:
            print(f"    • {note}")

    if result.risk_flags:
        print(f"\n  Risk Flags ({len(result.risk_flags)}):")
        for flag in result.risk_flags:
            sev = flag.split(":")[0] if ":" in flag else "INFO"
            print(f"    [{sev}] {flag.split(':', 1)[-1].strip()[:80]}")

    print("=" * W + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Azure SQL MI → AWS Aurora PostgreSQL Migration Effort Estimator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--input", "-i",
        metavar="FILE",
        help="Path to a JSON project profile file.",
    )
    parser.add_argument(
        "--interactive", "-w",
        action="store_true",
        help="Run interactive wizard to enter project details.",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["html", "json", "both"],
        default="both",
        help="Output format (default: both).",
    )
    parser.add_argument(
        "--output", "-o",
        metavar="PATH",
        help="Output file path (without extension). Default: outputs/<project_name>.",
    )
    parser.add_argument(
        "--no-console",
        action="store_true",
        help="Suppress console summary output.",
    )

    args = parser.parse_args()

    if not args.input and not args.interactive:
        parser.print_help()
        print("\n  [!] Provide --input <file> or use --interactive mode.\n")
        sys.exit(1)

    # Load profile
    if args.interactive:
        profile = run_interactive_wizard()
    else:
        print(f"\n  Loading profile from: {args.input}")
        profile = load_profile_from_json(args.input)

    # Run estimation
    print(f"\n  Running estimation for: {profile.project_name} ...")
    result = estimate(profile)

    # Console output
    if not args.no_console:
        print_summary(result)

    # File outputs
    out_base = args.output
    if out_base:
        out_base = Path(out_base)
    else:
        safe = profile.project_name.replace(" ", "_").lower()
        out_base = Path(__file__).parent / "outputs" / safe

    out_base.parent.mkdir(parents=True, exist_ok=True)

    if args.format in ("html", "both"):
        html_path = generate_html(result, Path(str(out_base) + "_report.html"))
        print(f"  HTML report  : {html_path}")

    if args.format in ("json", "both"):
        json_path = export_json(result, Path(str(out_base) + "_estimate.json"))
        print(f"  JSON export  : {json_path}")

    print()


if __name__ == "__main__":
    main()
