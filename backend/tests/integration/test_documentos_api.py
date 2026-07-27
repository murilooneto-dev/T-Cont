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


@pytest.fixture
def client(tmp_path):
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
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def empresa_id(client):
    response = client.post(
        "/empresas", json={"razao_social": "Tesserato", "nome_fantasia": None, "cnpj": "12345678000199"}
    )
    return response.json()["id"]


def test_upload_lista_e_obtem_resultado_de_documento(client, empresa_id):
    response = client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("comprovante.pdf", b"conteudo-pdf", "application/pdf")},
    )
    assert response.status_code == 201
    body = response.json()
    assert len(body) == 1
    assert body[0]["erro"] is None
    documento_id = body[0]["documento"]["id"]

    response = client.get(f"/empresas/{empresa_id}/documentos")
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = client.get(f"/documentos/{documento_id}/resultado")
    assert response.status_code == 200
    body = response.json()
    assert body["documento"]["status"] == "PENDENTE"
    assert body["resultado"] is None


def test_upload_extensao_invalida_retorna_erro_no_item_mas_201(client, empresa_id):
    response = client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("virus.exe", b"x", "application/octet-stream")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body[0]["documento"] is None
    assert body[0]["erro"] is not None


def test_upload_para_empresa_inexistente_retorna_404(client):
    response = client.post(
        "/empresas/999/documentos",
        files={"arquivos": ("a.pdf", b"x", "application/pdf")},
    )
    assert response.status_code == 404


def test_obter_resultado_documento_inexistente_retorna_404(client):
    response = client.get("/documentos/999/resultado")
    assert response.status_code == 404
