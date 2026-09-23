"""Add run-specific field Ground Truth and explicit ROI origin; preserve historical data."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0007_fields_roi_source"
down_revision = "0006_ocr_error_events"
branch_labels = depends_on = None


def upgrade():
    op.add_column(
        "test_cases", sa.Column("roi_source", sa.String(10), nullable=False, server_default="none")
    )
    json_type = sa.JSON().with_variant(JSONB(), "postgresql")
    op.create_table(
        "ocr_fields",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            "pipeline_run_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("field_index", sa.Integer(), nullable=False),
        sa.Column("geometry", json_type, nullable=False),
        sa.Column("ocr_text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("ground_truth_raw", sa.Text(), nullable=True),
        sa.Column("ground_truth_normalized", sa.Text(), nullable=True),
        sa.Column("evaluation", json_type, nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("pipeline_run_id", "field_index", name="uq_ocr_fields_run_index"),
    )
    op.create_index("ix_ocr_fields_pipeline_run_id", "ocr_fields", ["pipeline_run_id"])


def downgrade():
    op.drop_table("ocr_fields")
    op.drop_column("test_cases", "roi_source")
