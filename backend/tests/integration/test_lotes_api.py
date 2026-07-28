import time

import fitz
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db, get_storage
from app.infrastructure.db.base import Base
from app.infrastructure.db import models  # noqa: F401
from app.infrastructure.storage.file_storage import LocalFileStorageService
from app.main import app


def _pdf_com_texto(texto: str) -> bytes:
    documento = fitz.open()
    pagina = documento.new_page()
    pagina.insert_text((72, 72), texto)
    conteudo = documento.tobytes()
    documento.close()
    return conteudo


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        session = TestSessionLocal()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    def override_get_storage():
        return LocalFileStorageService(tmp_path)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage] = override_get_storage
    monkeypatch.setattr("app.core.config.settings.storage_root", str(tmp_path))
    # processar_lote_em_background opens its own session via
    # app.infrastructure.db.session.SessionLocal (it runs outside the
    # request scope, after the response is sent, so it can't reuse the
    # request-scoped `db` from get_db). That SessionLocal is bound to the
    # app's real configured database at import time, not this test's
    # in-memory SQLite. Point it at the same in-memory engine/session
    # factory so the background task's writes are visible to this test.
    monkeypatch.setattr("app.infrastructure.db.session.SessionLocal", TestSessionLocal)
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def empresa_id(client):
    response = client.post(
        "/empresas", json={"razao_social": "Tesserato", "nome_fantasia": None, "cnpj": "12345678000199"}
    )
    return response.json()["id"]


def test_processar_lote_ate_concluir(client, empresa_id):
    conteudo = _pdf_com_texto("COMPROVANTE TESTE INTEGRACAO 12345678901234567890")
    client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("comprovante.pdf", conteudo, "application/pdf")},
    )

    response = client.post(f"/empresas/{empresa_id}/documentos/processar")
    assert response.status_code == 201
    lote_id = response.json()["id"]
    assert response.json()["total_documentos"] == 1

    status_final = None
    for _ in range(20):
        status_response = client.get(f"/lotes/{lote_id}")
        status_final = status_response.json()
        if status_final["status"] != "EM_ANDAMENTO":
            break
        time.sleep(0.5)

    assert status_final["status"] == "CONCLUIDO"
    assert status_final["documentos_processados"] == 1


def test_processar_lote_empresa_inexistente_retorna_404(client):
    response = client.post("/empresas/999/documentos/processar")
    assert response.status_code == 404


def test_cancelar_lote(client, empresa_id):
    conteudo = _pdf_com_texto("COMPROVANTE OUTRO TESTE 12345678901234567890")
    client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("comprovante.pdf", conteudo, "application/pdf")},
    )
    lote_id = client.post(f"/empresas/{empresa_id}/documentos/processar").json()["id"]

    response = client.post(f"/lotes/{lote_id}/cancelar")
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELADO"


def test_obter_status_lote_inexistente_retorna_404(client):
    response = client.get("/lotes/999")
    assert response.status_code == 404
