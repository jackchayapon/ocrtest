"""Add shared External OCR providers with separately isolated encrypted keys."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0013_external_providers"
down_revision = "0012_ocr_jobs"
branch_labels = depends_on = None


def upgrade():
    op.create_table("external_providers",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("config", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False),
        sa.Column("encrypted_credential", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    # Credentials belong to this table. Preserve them and their encryption keys
    # during application rollback instead of downgrading a live database.
    op.drop_table("external_providers")
