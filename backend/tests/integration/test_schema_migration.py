from sqlalchemy import create_engine, inspect
from alembic import command
from alembic.config import Config


def test_migration_creates_all_tables(tmp_path):
    db_path = tmp_path / "test_migration.db"
    db_url = f"sqlite:///{db_path}"

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(db_url)
    tables = set(inspect(engine).get_table_names())

    expected = {
        "empresas", "planos_contas", "contas", "documentos", "ocr_resultados",
        "extracoes", "classificacoes", "aprendizado", "historico_alteracoes",
        "usuarios", "logs", "configuracoes", "alembic_version",
    }
    assert expected.issubset(tables)
