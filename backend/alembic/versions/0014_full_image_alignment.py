"""Persist confirmed full-image GT/DET correspondence per run."""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision = "0014_full_image_alignment"
down_revision = "0013_external_providers"
branch_labels = depends_on = None


def upgrade():
    op.add_column("test_cases", sa.Column("full_image_alignment", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=True))


def downgrade():
    op.drop_column("test_cases", "full_image_alignment")
