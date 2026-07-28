from sqlalchemy import create_engine, inspect
from alembic import command
from alembic.config import Config


def test_migration_adds_extracoes_columns(tmp_path):
    db_path = tmp_path / "test_fase2_migration.db"
    db_url = f"sqlite:///{db_path}"

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(db_url)
    inspector = inspect(engine)

    extracao_cols = {c["name"] for c in inspector.get_columns("extracoes")}
    assert extracao_cols == {
        "id", "documento_id", "pagador_nome", "pagador_documento",
        "recebedor_nome", "recebedor_documento", "valor", "data_pagamento",
        "tipo_documento", "banco_nome", "created_at",
    }

    # downgrade must be symmetric
    command.downgrade(alembic_cfg, "0002")
    inspector = inspect(engine)
    extracao_cols = {c["name"] for c in inspector.get_columns("extracoes")}
    assert extracao_cols == {"id", "empresa_id", "created_at"}
