"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "empresas",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("razao_social", sa.String(255), nullable=False),
        sa.Column("nome_fantasia", sa.String(255), nullable=True),
        sa.Column("cnpj", sa.String(14), nullable=False, unique=True),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "planos_contas",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("nome", sa.String(255), nullable=False),
        sa.Column("versao", sa.Integer, nullable=False, server_default="1"),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "contas",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "plano_conta_id", sa.Integer, sa.ForeignKey("planos_contas.id"), nullable=False
        ),
        sa.Column("codigo", sa.String(50), nullable=False),
        sa.Column("descricao", sa.String(255), nullable=False),
        sa.Column("natureza", sa.String(20), nullable=False),
        sa.Column("conta_analitica", sa.Boolean, nullable=False),
        sa.Column("conta_pai_id", sa.Integer, sa.ForeignKey("contas.id"), nullable=True),
    )

    for table_name in (
        "documentos",
        "ocr_resultados",
        "extracoes",
        "classificacoes",
        "aprendizado",
        "historico_alteracoes",
    ):
        op.create_table(
            table_name,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "empresa_id", sa.Integer, sa.ForeignKey("empresas.id"), nullable=False
            ),
            sa.Column("created_at", sa.DateTime, nullable=False),
        )

    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    for table_name in ("logs", "configuracoes"):
        op.create_table(
            table_name,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "empresa_id", sa.Integer, sa.ForeignKey("empresas.id"), nullable=True
            ),
            sa.Column("created_at", sa.DateTime, nullable=False),
        )


def downgrade() -> None:
    for table_name in (
        "configuracoes",
        "logs",
        "usuarios",
        "historico_alteracoes",
        "aprendizado",
        "classificacoes",
        "extracoes",
        "ocr_resultados",
        "documentos",
        "contas",
        "planos_contas",
        "empresas",
    ):
        op.drop_table(table_name)
