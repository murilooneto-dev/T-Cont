from sqlalchemy import create_engine, inspect
from alembic import command
from alembic.config import Config


def test_migration_cria_regras_e_classificacoes_reais(tmp_path):
    db_path = tmp_path / "test_fase3_migration.db"
    db_url = f"sqlite:///{db_path}"

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(db_url)
    inspector = inspect(engine)

    regra_cols = {c["name"] for c in inspector.get_columns("regras")}
    assert regra_cols == {
        "id", "empresa_id", "conta_id", "lado_alvo", "documento_fiscal",
        "tipo_documento", "valor_min", "valor_max", "palavra_chave_nome",
        "ativo", "created_at",
    }

    classificacao_cols = {c["name"] for c in inspector.get_columns("classificacoes")}
    assert classificacao_cols == {
        "id", "empresa_id", "documento_id", "conta_id", "origem",
        "regra_id", "score_similaridade", "created_at",
    }

    regra_indexes = {idx["name"] for idx in inspector.get_indexes("regras")}
    assert "ix_regras_empresa_id" in regra_indexes

    classificacao_indexes = {idx["name"] for idx in inspector.get_indexes("classificacoes")}
    assert "ix_classificacoes_empresa_id" in classificacao_indexes

    # downgrade must be symmetric
    command.downgrade(alembic_cfg, "0003")
    inspector = inspect(engine)
    classificacao_cols = {c["name"] for c in inspector.get_columns("classificacoes")}
    assert classificacao_cols == {"id", "empresa_id", "created_at"}
    assert "regras" not in inspector.get_table_names()
