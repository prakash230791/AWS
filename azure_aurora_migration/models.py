"""
models.py
Data models for the Azure SQL MI → AWS Aurora PostgreSQL Migration Estimator.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum


class ComplexityBand(str, Enum):
    SIMPLE       = "simple"
    MEDIUM       = "medium"
    COMPLEX      = "complex"
    VERY_COMPLEX = "very_complex"

    @property
    def label(self) -> str:
        return {
            "simple":       "Simple",
            "medium":       "Medium",
            "complex":      "Complex",
            "very_complex": "Very Complex",
        }[self.value]

    @property
    def color(self) -> str:
        return {
            "simple":       "#28a745",
            "medium":       "#ffc107",
            "complex":      "#fd7e14",
            "very_complex": "#dc3545",
        }[self.value]


@dataclass
class ProjectProfile:
    """Input profile describing the Azure SQL MI source environment."""

    # Project metadata
    project_name:    str = "Azure SQL MI Migration"
    client_name:     str = "Client"
    prepared_by:     str = "Migration Team"

    # ---------- Schema inventory ----------
    num_tables:               int = 0
    num_stored_procedures:    int = 0
    num_functions:            int = 0
    num_triggers:             int = 0
    num_views:                int = 0
    num_indexes:              int = 0
    num_constraints:          int = 0   # FK + Check + Unique

    # ---------- Data characteristics ----------
    database_size_gb:         float = 0.0
    largest_table_rows_m:     float = 0.0   # millions of rows
    num_databases:            int = 1        # MI supports multiple databases
    cross_database_queries:   bool = False

    # ---------- T-SQL feature usage (Azure SQL MI specific) ----------
    # MI-specific features (not available in Azure SQL DB)
    uses_clr_assemblies:          bool = False
    uses_sql_agent_jobs:          bool = False
    uses_service_broker:          bool = False
    uses_linked_servers:          bool = False
    uses_replication:             bool = False
    uses_cross_db_queries:        bool = False
    uses_database_mail:           bool = False

    # Common T-SQL features
    uses_cursors:                 bool = False
    uses_xml_data_type:           bool = False
    uses_full_text_search:        bool = False
    uses_spatial_data:            bool = False
    uses_json_support:            bool = False
    uses_dynamic_sql:             bool = False
    uses_merge_statement:         bool = False
    uses_recursive_cte:           bool = False
    uses_partition_tables:        bool = False
    uses_row_level_security:      bool = False
    uses_always_encrypted:        bool = False
    uses_indexed_views:           bool = False
    uses_computed_columns:        bool = False
    uses_hierarchyid:             bool = False
    uses_filestream:              bool = False
    uses_openquery:               bool = False
    uses_temp_tables:             bool = False
    uses_tvp:                     bool = False   # Table-Valued Parameters
    uses_identity_columns:        bool = True    # Almost always used
    uses_nolock_hints:            bool = False
    uses_error_handling:          bool = False

    # ---------- Data types used ----------
    uses_dt_uniqueidentifier:   bool = False
    uses_dt_xml:                bool = False
    uses_dt_geography:          bool = False
    uses_dt_geometry:           bool = False
    uses_dt_hierarchyid:        bool = False
    uses_dt_sql_variant:        bool = False
    uses_dt_varbinary_max:      bool = False
    uses_dt_image:              bool = False
    uses_dt_text_ntext:         bool = False
    uses_dt_money:              bool = False
    uses_dt_rowversion:         bool = False

    # ---------- Application layer ----------
    num_connected_applications: int = 1
    app_languages:              List[str] = field(default_factory=list)   # e.g. ["C#", "Java"]
    uses_orm:                   bool = False
    orm_names:                  List[str] = field(default_factory=list)   # e.g. ["Entity Framework"]
    uses_ssrs_reports:          bool = False
    uses_ssas:                  bool = False
    uses_ssis_packages:         bool = False

    # ---------- Non-functional requirements ----------
    high_availability_required:          bool = True
    compliance_requirements:             bool = False
    compliance_frameworks:               List[str] = field(default_factory=list)
    zero_downtime_cutover:               bool = False
    target_rto_hours:                    float = 4.0
    target_rpo_minutes:                  float = 60.0
    multiple_environments:               bool = True    # Dev, QA, Staging, Prod
    parallel_run_required:               bool = False
    use_aws_dms_sct:                     bool = True    # Using AWS SCT/DMS tools
    team_has_migration_experience:       bool = False
    documentation_available:             bool = True
    active_development_during_migration: bool = False


@dataclass
class WorkstreamEstimate:
    """Effort estimate for a single migration workstream."""

    workstream_id:    str
    label:            str
    description:      str
    complexity_band:  ComplexityBand
    base_effort_days: float
    risk_buffer_days: float
    total_effort_days: float
    notes:            List[str] = field(default_factory=list)

    @property
    def min_effort_days(self) -> float:
        return round(self.base_effort_days * 0.80, 1)

    @property
    def max_effort_days(self) -> float:
        return round(self.total_effort_days * 1.25, 1)

    @property
    def effort_weeks(self) -> float:
        return round(self.total_effort_days / 5, 1)


@dataclass
class MigrationEstimate:
    """Full effort estimation result."""

    project_name:       str
    client_name:        str
    prepared_by:        str
    overall_complexity: ComplexityBand
    complexity_score:   float
    workstreams:        List[WorkstreamEstimate] = field(default_factory=list)
    global_multiplier:  float = 1.0
    multiplier_notes:   List[str] = field(default_factory=list)
    contingency_pct:    float = 20.0
    mi_specific_notes:  List[str] = field(default_factory=list)
    risk_flags:         List[str] = field(default_factory=list)
    recommendations:    List[str] = field(default_factory=list)

    @property
    def subtotal_days(self) -> float:
        return round(sum(w.total_effort_days for w in self.workstreams), 1)

    @property
    def adjusted_days(self) -> float:
        return round(self.subtotal_days * self.global_multiplier, 1)

    @property
    def contingency_days(self) -> float:
        return round(self.adjusted_days * (self.contingency_pct / 100), 1)

    @property
    def total_days(self) -> float:
        return round(self.adjusted_days + self.contingency_days, 1)

    @property
    def total_weeks(self) -> float:
        return round(self.total_days / 5, 1)

    @property
    def total_months(self) -> float:
        return round(self.total_weeks / 4.33, 1)

    @property
    def optimistic_days(self) -> float:
        return round(self.total_days * 0.80, 1)

    @property
    def pessimistic_days(self) -> float:
        return round(self.total_days * 1.30, 1)

    def workstream_by_id(self, ws_id: str) -> Optional[WorkstreamEstimate]:
        return next((w for w in self.workstreams if w.workstream_id == ws_id), None)
