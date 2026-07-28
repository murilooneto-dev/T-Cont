"""fase2 extracao de dados: real extracoes table

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("extracoes")
    op.create_table(
        "extracoes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "documento_id", sa.Integer, sa.ForeignKey("documentos.id"),
            nullable=False, unique=True,
        ),
        sa.Column("pagador_nome", sa.String(255), nullable=True),
        sa.Column("pagador_documento", sa.String(14), nullable=True),
        sa.Column("recebedor_nome", sa.String(255), nullable=True),
        sa.Column("recebedor_documento", sa.String(14), nullable=True),
        sa.Column("valor", sa.Numeric(12, 2), nullable=True),
        sa.Column("data_pagamento", sa.Date, nullable=True),
        sa.Column("tipo_documento", sa.String(20), nullable=False, server_default="OUTRO"),
        sa.Column("banco_nome", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("extracoes")
    op.create_table(
        "extracoes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
