from sqlalchemy import inspect
from sqlalchemy.pool import StaticPool

from app.infrastructure.db.base import Base
from app.infrastructure.db import models  # noqa: F401
from app.infrastructure.db.session import get_engine


def test_documentos_ganha_coluna_documento_origem_id():
    engine = get_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)

    inspetor = inspect(engine)
    colunas = {c["name"] for c in inspetor.get_columns("documentos")}

    assert "documento_origem_id" in colunas


def test_status_documento_aceita_dividido():
    from app.domain.enums import StatusDocumento

    assert StatusDocumento.DIVIDIDO.value == "DIVIDIDO"
