"""fase4 IA + aprendizado: tabela aprendizado real

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("aprendizado")
    op.create_table(
        "aprendizado",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("documento_id", sa.Integer, sa.ForeignKey("documentos.id"), nullable=False),
        sa.Column("conta_anterior_id", sa.Integer, sa.ForeignKey("contas.id"), nullable=True),
        sa.Column("origem_anterior", sa.String(20), nullable=True),
        sa.Column(
            "conta_corrigida_id", sa.Integer, sa.ForeignKey("contas.id"), nullable=False
        ),
        sa.Column("regra_id", sa.Integer, sa.ForeignKey("regras.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_aprendizado_empresa_id", "aprendizado", ["empresa_id"])


def downgrade() -> None:
    op.drop_index("ix_aprendizado_empresa_id", table_name="aprendizado")
    op.drop_table("aprendizado")
    op.create_table(
        "aprendizado",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
