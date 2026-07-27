from sqlalchemy import create_engine, inspect, text
from alembic import command
from alembic.config import Config

from app.infrastructure.db.session import get_engine


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


def _migrar(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'test_migration.db'}"
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")
    return create_engine(db_url)


def test_migration_cria_indices_de_foreign_key(tmp_path):
    inspetor = inspect(_migrar(tmp_path))

    colunas_indexadas = {
        tuple(idx["column_names"]) for idx in inspetor.get_indexes("contas")
    }
    assert ("plano_conta_id",) in colunas_indexadas
    assert ("conta_pai_id",) in colunas_indexadas

    colunas_planos = {
        tuple(idx["column_names"]) for idx in inspetor.get_indexes("planos_contas")
    }
    assert ("empresa_id",) in colunas_planos

    # cnpj já é coberto pelo índice implícito da constraint UNIQUE.
    unicas_empresas = {
        tuple(uc["column_names"]) for uc in inspetor.get_unique_constraints("empresas")
    }
    assert ("cnpj",) in unicas_empresas


def test_migration_cria_unique_de_codigo_por_plano(tmp_path):
    inspetor = inspect(_migrar(tmp_path))

    unicas = {
        uc["name"]: tuple(uc["column_names"])
        for uc in inspetor.get_unique_constraints("contas")
    }
    assert unicas.get("uq_contas_plano_codigo") == ("plano_conta_id", "codigo")


def test_todas_colunas_datetime_sao_timezone_aware():
    # SQLite não preserva timezone na reflexão, então a garantia é checada
    # sobre o metadata declarado — é ele que gera TIMESTAMPTZ no PostgreSQL.
    from sqlalchemy import DateTime

    from app.infrastructure.db.base import Base

    naive = [
        f"{tabela.name}.{coluna.name}"
        for tabela in Base.metadata.tables.values()
        for coluna in tabela.columns
        if isinstance(coluna.type, DateTime) and not coluna.type.timezone
    ]
    assert naive == []


def test_get_engine_habilita_foreign_keys_no_sqlite(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path / 'fk.db'}")

    with engine.connect() as conexao:
        assert conexao.execute(text("PRAGMA foreign_keys")).scalar() == 1
