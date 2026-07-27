from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


def _habilitar_foreign_keys_sqlite(engine) -> None:
    """SQLite desabilita a checagem de FK por padrão.

    Sem isso, linhas órfãs (ex.: conta apontando para um plano inexistente)
    passam silenciosamente em dev/teste e só explodem em PostgreSQL. Ligamos
    o PRAGMA em cada conexão nova para que o comportamento local seja igual
    ao de produção — defesa em profundidade, além da validação no use case.
    """

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


def get_engine(database_url: str | None = None):
    url = database_url or settings.database_url
    is_sqlite = url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    engine = create_engine(url, connect_args=connect_args)
    if is_sqlite:
        _habilitar_foreign_keys_sqlite(engine)
    return engine


engine = get_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
