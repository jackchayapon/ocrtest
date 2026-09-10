"""Add canonical crop and Gateway trace fields without deleting prior results."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0002_gateway_crop_trace"
down_revision = "0001_benchmark_schema"
branch_labels = None
depends_on = None

STRING_FIELDS = {
    "request_id": 100,
    "gateway_request_id": 100,
    "gateway_service": 255,
    "gateway_model": 500,
    "detector_model": 255,
    "recognizer_model": 255,
    "crop_sha256": 64,
    "input_format": 30,
    "crop_stage": 30,
    "error_code": 100,
}
INTEGER_FIELDS = (
    "original_width",
    "original_height",
    "crop_width",
    "crop_height",
    "input_byte_size",
)


def upgrade():
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.add_column("documents", sa.Column("sha256", sa.String(64), nullable=True))
    op.add_column(
        "pipeline_configs",
        sa.Column("query_params", json_type, nullable=False, server_default="{}"),
    )
    op.add_column(
        "pipeline_runs",
        sa.Column("is_mock", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("pipeline_runs", sa.Column("gateway_duration_ms", sa.Float(), nullable=True))
    op.add_column("pipeline_runs", sa.Column("roi", json_type, nullable=True))
    for name, length in STRING_FIELDS.items():
        op.add_column("pipeline_runs", sa.Column(name, sa.String(length), nullable=True))
    for name in INTEGER_FIELDS:
        op.add_column("pipeline_runs", sa.Column(name, sa.Integer(), nullable=True))
    # Legacy mock diagnostics carried mode=mock. This preserves truthful labeling.
    op.execute(
        sa.text(
            'UPDATE pipeline_runs SET is_mock = true WHERE CAST(raw_response AS TEXT) LIKE \'%"mode": "mock"%\''
        )
    )


def downgrade():
    for name in (*STRING_FIELDS, *INTEGER_FIELDS, "roi", "gateway_duration_ms", "is_mock"):
        op.drop_column("pipeline_runs", name)
    op.drop_column("pipeline_configs", "query_params")
    op.drop_column("documents", "sha256")
