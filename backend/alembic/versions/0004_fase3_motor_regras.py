"""fase3 motor de regras: tabela regras + classificacoes reais

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "regras",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("conta_id", sa.Integer, sa.ForeignKey("contas.id"), nullable=False),
        sa.Column("lado_alvo", sa.String(20), nullable=True),
        sa.Column("documento_fiscal", sa.String(14), nullable=True),
        sa.Column("tipo_documento", sa.String(20), nullable=True),
        sa.Column("valor_min", sa.Numeric(12, 2), nullable=True),
        sa.Column("valor_max", sa.Numeric(12, 2), nullable=True),
        sa.Column("palavra_chave_nome", sa.String(255), nullable=True),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.drop_table("classificacoes")
    op.create_table(
        "classificacoes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column(
            "documento_id", sa.Integer, sa.ForeignKey("documentos.id"),
            nullable=False, unique=True,
        ),
        sa.Column("conta_id", sa.Integer, sa.ForeignKey("contas.id"), nullable=False),
        sa.Column("origem", sa.String(20), nullable=False),
        sa.Column("regra_id", sa.Integer, sa.ForeignKey("regras.id"), nullable=True),
        sa.Column("score_similaridade", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_index("ix_regras_empresa_id", "regras", ["empresa_id"])
    op.create_index("ix_classificacoes_empresa_id", "classificacoes", ["empresa_id"])


def downgrade() -> None:
    op.drop_index("ix_classificacoes_empresa_id", table_name="classificacoes")
    op.drop_index("ix_regras_empresa_id", table_name="regras")
    op.drop_table("classificacoes")
    op.create_table(
        "classificacoes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.drop_table("regras")
