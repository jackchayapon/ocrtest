"""Add structured application events without altering benchmark data."""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005_app_logs"
down_revision = "0004_real_inputs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "app_logs",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("level", sa.String(10), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("message", sa.String(255), nullable=False),
        sa.Column("test_case_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("document_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("pipeline_id", sa.String(50), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.String(100), nullable=True),
        sa.Column("gateway_request_id", sa.String(100), nullable=True),
        sa.Column("metadata", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
    )
    for field in ("created_at", "level", "event_type", "test_case_id", "pipeline_id", "request_id"):
        op.create_index(f"ix_app_logs_{field}", "app_logs", [field])


def downgrade():
    op.drop_table("app_logs")
