"""Archive historical synthetic results and trace full versus cropped input.

No documents, cases, predictions, metrics or credentials are deleted.
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_real_inputs"
down_revision = "0003_pdf_pages"
branch_labels = None
depends_on = None


def upgrade():
    dialect = op.get_bind().dialect.name
    marker = "raw_response ->> 'mode'" if dialect == "postgresql" else "json_extract(raw_response, '$.mode')"
    op.execute(sa.text(f"UPDATE pipeline_runs SET is_mock = true WHERE {marker} = 'mock'"))
    # Native rename/drop avoids rebuilding parent tables referenced by metrics.
    op.alter_column("pipeline_runs", "is_mock", new_column_name="archived",
                    existing_type=sa.Boolean(), existing_nullable=False)
    op.add_column("pipeline_runs", sa.Column("input_sha256", sa.String(64), nullable=True))
    op.add_column("pipeline_runs", sa.Column("input_width", sa.Integer(), nullable=True))
    op.add_column("pipeline_runs", sa.Column("input_height", sa.Integer(), nullable=True))
    op.execute("UPDATE pipeline_runs SET input_sha256 = crop_sha256, "
               "input_width = crop_width, input_height = crop_height")
    op.drop_column("pipeline_configs", "mode")
    op.execute("UPDATE pipeline_configs SET last_connection_status = NULL WHERE last_connection_status = 'mock_ready'")


def downgrade():
    op.add_column("pipeline_configs", sa.Column("mode", sa.String(20), nullable=False, server_default="real"))
    op.alter_column("pipeline_runs", "archived", new_column_name="is_mock", existing_type=sa.Boolean(),
                    existing_nullable=False)
    for name in ("input_height", "input_width", "input_sha256"):
        op.drop_column("pipeline_runs", name)
