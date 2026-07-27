"""fase1 ocr pipeline: real documentos/ocr_resultados columns + lotes_processamento

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("documentos")
    op.create_table(
        "documentos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("nome_arquivo", sa.String(255), nullable=False),
        sa.Column("nome_exibicao", sa.String(255), nullable=False),
        sa.Column("caminho_arquivo", sa.String(500), nullable=False),
        sa.Column("extensao", sa.String(10), nullable=False),
        sa.Column("tamanho_bytes", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDENTE"),
        sa.Column("mensagem_erro", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_documentos_empresa_id", "documentos", ["empresa_id"])

    op.drop_table("ocr_resultados")
    op.create_table(
        "ocr_resultados",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "documento_id", sa.Integer, sa.ForeignKey("documentos.id"),
            nullable=False, unique=True,
        ),
        sa.Column("texto_extraido", sa.Text, nullable=False),
        sa.Column("metodo", sa.String(20), nullable=False),
        sa.Column("tempo_processamento_ms", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "lotes_processamento",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("total_documentos", sa.Integer, nullable=False),
        sa.Column(
            "documentos_processados", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="EM_ANDAMENTO"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("concluido_em", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("lotes_processamento")
    op.drop_table("ocr_resultados")
    op.drop_index("ix_documentos_empresa_id", table_name="documentos")
    op.drop_table("documentos")

    op.create_table(
        "documentos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "ocr_resultados",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
