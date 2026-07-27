from sqlalchemy import create_engine, inspect
from alembic import command
from alembic.config import Config


def test_migration_adds_fase1_columns_and_table(tmp_path):
    db_path = tmp_path / "test_fase1_migration.db"
    db_url = f"sqlite:///{db_path}"

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(db_url)
    inspector = inspect(engine)

    documento_cols = {c["name"] for c in inspector.get_columns("documentos")}
    assert documento_cols == {
        "id", "empresa_id", "nome_arquivo", "nome_exibicao", "caminho_arquivo",
        "extensao", "tamanho_bytes", "status", "mensagem_erro", "created_at", "updated_at",
    }

    ocr_cols = {c["name"] for c in inspector.get_columns("ocr_resultados")}
    assert ocr_cols == {
        "id", "documento_id", "texto_extraido", "metodo", "tempo_processamento_ms", "created_at",
    }

    assert "lotes_processamento" in inspector.get_table_names()
    lote_cols = {c["name"] for c in inspector.get_columns("lotes_processamento")}
    assert lote_cols == {
        "id", "empresa_id", "total_documentos", "documentos_processados", "status",
        "created_at", "concluido_em",
    }

    # downgrade must be symmetric
    command.downgrade(alembic_cfg, "0001")
    inspector = inspect(engine)
    documento_cols = {c["name"] for c in inspector.get_columns("documentos")}
    assert documento_cols == {"id", "empresa_id", "created_at"}
    assert "lotes_processamento" not in inspector.get_table_names()
