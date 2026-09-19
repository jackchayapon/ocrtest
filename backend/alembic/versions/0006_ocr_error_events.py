"""Add alignment events; existing metrics and benchmark data remain unchanged."""

import sqlalchemy as sa

from alembic import op

revision = "0006_ocr_error_events"
down_revision = "0005_app_logs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ocr_error_events",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            "pipeline_run_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "test_case_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("test_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text_kind", sa.String(10), nullable=False),
        sa.Column("error_level", sa.String(10), nullable=False),
        sa.Column("error_type", sa.String(20), nullable=False),
        sa.Column("ground_truth_unit", sa.Text(), nullable=True),
        sa.Column("ocr_unit", sa.Text(), nullable=True),
        sa.Column("ground_truth_position", sa.Integer(), nullable=True),
        sa.Column("ocr_position", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("pipeline_run_id", "test_case_id"):
        op.create_index(f"ix_ocr_error_events_{column}", "ocr_error_events", [column])


def downgrade():
    op.drop_table("ocr_error_events")
