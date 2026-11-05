"""Add durable OCR queue. Existing cases and results are unchanged."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0012_ocr_jobs"
down_revision = "0011_gt_prefill"
branch_labels = depends_on = None


def upgrade():
    json_type = sa.JSON().with_variant(JSONB(), "postgresql")
    op.create_table(
        "ocr_jobs",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            "test_case_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("test_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        *[
            sa.Column(name, json_type, nullable=False)
            for name in ("pipeline_ids", "config_snapshot", "run_ids", "prefill_results")
        ],
        *[
            sa.Column(name, sa.Integer(), nullable=False)
            for name in (
                "total_fields",
                "total_pipelines",
                "completed_units",
                "failed_units",
                "completed_pipelines",
                "attempt_count",
            )
        ],
        sa.Column("current_pipeline_id", sa.String(50)),
        sa.Column("current_field_index", sa.Integer()),
        sa.Column("lease_owner", sa.String(100)),
        *[
            sa.Column(
                name, sa.DateTime(timezone=True), nullable=name not in ("created_at", "updated_at")
            )
            for name in (
                "lease_expires_at",
                "heartbeat_at",
                "started_at",
                "finished_at",
                "created_at",
                "updated_at",
            )
        ],
        sa.Column("error_code", sa.String(100)),
        sa.Column("safe_error_message", sa.String(255)),
        sa.UniqueConstraint("test_case_id", "idempotency_key", name="uq_ocr_job_request"),
    )
    op.create_index("ix_ocr_jobs_test_case_id", "ocr_jobs", ["test_case_id"])
    op.create_index("ix_ocr_job_queue", "ocr_jobs", ["status", "created_at"])
    op.create_index(
        "uq_ocr_job_active_case",
        "ocr_jobs",
        ["test_case_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
        sqlite_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade():
    op.drop_table("ocr_jobs")
