"""documentos unificados: documento_origem_id em documentos

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("documentos") as batch_op:
        batch_op.add_column(sa.Column("documento_origem_id", sa.Integer, nullable=True))
        batch_op.create_foreign_key(
            "fk_documentos_documento_origem_id", "documentos", ["documento_origem_id"], ["id"]
        )
    op.create_index(
        "ix_documentos_documento_origem_id", "documentos", ["documento_origem_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_documentos_documento_origem_id", table_name="documentos")
    with op.batch_alter_table("documentos") as batch_op:
        batch_op.drop_constraint("fk_documentos_documento_origem_id", type_="foreignkey")
        batch_op.drop_column("documento_origem_id")
