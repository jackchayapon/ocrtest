"""Create the benchmark schema, with PostgreSQL JSONB and UUID types."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001_benchmark_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    uuid = sa.Uuid(as_uuid=False)
    json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "documents",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("width", sa.Integer, nullable=False),
        sa.Column("height", sa.Integer, nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "test_cases",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("document_id", uuid, sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("roi", json),
        sa.Column("ground_truth_raw", sa.Text),
        sa.Column("ground_truth_normalized", sa.Text),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_test_cases_document_id", "test_cases", ["document_id"])
    op.create_index("ix_test_cases_created_at", "test_cases", ["created_at"])
    op.create_table(
        "pipeline_runs",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "test_case_id", uuid, sa.ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("pipeline_id", sa.String(50), nullable=False),
        sa.Column("pipeline_name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("raw_text", sa.Text),
        sa.Column("final_text", sa.Text),
        sa.Column("normalized_text", sa.Text),
        sa.Column("confidence", sa.Float),
        sa.Column("processing_time_ms", sa.Integer),
        sa.Column("boxes", json, nullable=False),
        sa.Column("raw_response", json),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("test_case_id", "pipeline_id", "created_at"):
        op.create_index(f"ix_pipeline_runs_{column}", "pipeline_runs", [column])
    op.create_table(
        "metrics",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "pipeline_run_id",
            uuid,
            sa.ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text_kind", sa.String(10), nullable=False),
        sa.Column("cer", sa.Float),
        sa.Column("wer", sa.Float),
        sa.Column("exact_match", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("pipeline_run_id", "text_kind", name="uq_metrics_run_kind"),
    )
    op.create_index("ix_metrics_pipeline_run_id", "metrics", ["pipeline_run_id"])
    op.create_table(
        "categories",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("display_name", sa.String(100), nullable=False),
    )
    op.create_table(
        "test_case_categories",
        sa.Column(
            "test_case_id",
            uuid,
            sa.ForeignKey("test_cases.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "category_id",
            uuid,
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "pipeline_configs",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("pipeline_id", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("mode", sa.String(10), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("endpoint", sa.String(500), nullable=False),
        sa.Column("http_method", sa.String(10), nullable=False),
        sa.Column("request_format", sa.String(30), nullable=False),
        sa.Column("file_field_name", sa.String(100), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("engine", sa.String(100)),
        sa.Column("include_roi", sa.Boolean, nullable=False),
        sa.Column("last_connection_status", sa.String(50)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    for table in (
        "pipeline_configs",
        "test_case_categories",
        "categories",
        "metrics",
        "pipeline_runs",
        "test_cases",
        "documents",
    ):
        op.drop_table(table)
