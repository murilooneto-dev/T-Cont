from sqlalchemy import create_engine, inspect
from alembic import command
from alembic.config import Config


def test_migration_cria_aprendizado_real(tmp_path):
    db_path = tmp_path / "test_fase4_migration.db"
    db_url = f"sqlite:///{db_path}"

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(db_url)
    inspector = inspect(engine)

    aprendizado_cols = {c["name"] for c in inspector.get_columns("aprendizado")}
    assert aprendizado_cols == {
        "id", "empresa_id", "documento_id", "conta_anterior_id", "origem_anterior",
        "conta_corrigida_id", "regra_id", "created_at",
    }
    aprendizado_indexes = {idx["name"] for idx in inspector.get_indexes("aprendizado")}
    assert "ix_aprendizado_empresa_id" in aprendizado_indexes

    # downgrade must be symmetric
    command.downgrade(alembic_cfg, "0004")
    inspector = inspect(engine)
    aprendizado_cols = {c["name"] for c in inspector.get_columns("aprendizado")}
    assert aprendizado_cols == {"id", "empresa_id", "created_at"}
