"""Remember the one-time OCR draft independently from GT confirmation."""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0011_gt_prefill"
down_revision = "0010_dynamic_pipelines"
branch_labels = depends_on = None


def upgrade():
    op.add_column("test_cases", sa.Column("gt_prefill", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=True))


def downgrade():
    op.drop_column("test_cases", "gt_prefill")
