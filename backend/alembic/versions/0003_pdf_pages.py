"""Retain original PDFs and bind test cases to one-based raster pages."""

import sqlalchemy as sa

from alembic import op

revision = "0003_pdf_pages"
down_revision = "0002_gateway_crop_trace"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "documents",
        sa.Column("document_type", sa.String(10), nullable=False, server_default="image"),
    )
    op.add_column(
        "documents", sa.Column("page_count", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column("documents", sa.Column("pdf_render_dpi", sa.Integer(), nullable=True))
    for name in ("page_number", "page_width", "page_height"):
        op.add_column("test_cases", sa.Column(name, sa.Integer(), nullable=True))


def downgrade():
    for name in ("page_height", "page_width", "page_number"):
        op.drop_column("test_cases", name)
    for name in ("pdf_render_dpi", "page_count", "document_type"):
        op.drop_column("documents", name)
