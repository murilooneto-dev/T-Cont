"""partida dobrada: conta_bancaria_id e direcao em classificacoes

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("classificacoes") as batch_op:
        batch_op.add_column(sa.Column("conta_bancaria_id", sa.Integer, nullable=True))
        batch_op.add_column(sa.Column("direcao", sa.String(20), nullable=True))
        batch_op.create_foreign_key(
            "fk_classificacoes_conta_bancaria_id", "contas", ["conta_bancaria_id"], ["id"]
        )
    op.create_index(
        "ix_classificacoes_conta_bancaria_id", "classificacoes", ["conta_bancaria_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_classificacoes_conta_bancaria_id", table_name="classificacoes")
    with op.batch_alter_table("classificacoes") as batch_op:
        batch_op.drop_constraint("fk_classificacoes_conta_bancaria_id", type_="foreignkey")
        batch_op.drop_column("direcao")
        batch_op.drop_column("conta_bancaria_id")
