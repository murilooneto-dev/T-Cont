import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db, get_storage
from app.api.routers import documentos_router
from app.infrastructure.db.base import Base
from app.infrastructure.db import models  # noqa: F401
from app.infrastructure.db.session import get_engine
from app.infrastructure.storage.file_storage import LocalFileStorageService
from app.main import app


@pytest.fixture
def client(tmp_path):
    # Reusa get_engine() (em vez de duplicar create_engine aqui) para que
    # este fixture rode com o mesmo PRAGMA foreign_keys=ON da aplicação.
    engine = get_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

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


def test_upload_rejeita_arquivo_acima_do_limite_sem_bufferizar_tudo(
    client, empresa_id, monkeypatch
):
    """O limite de tamanho é aplicado durante a leitura: no máximo limite+1
    bytes entram em memória (antes, o arquivo inteiro era lido primeiro)."""
    monkeypatch.setattr(documentos_router, "TAMANHO_MAXIMO_BYTES", 10)

    response = client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("grande.pdf", b"x" * 5000, "application/pdf")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body[0]["documento"] is None
    assert "tamanho máximo" in body[0]["erro"]
    # Nada foi persistido.
    assert client.get(f"/empresas/{empresa_id}/documentos").json() == []


def test_upload_rejeita_requisicao_com_arquivos_demais(client, empresa_id, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.max_arquivos_por_upload", 2)

    response = client.post(
        f"/empresas/{empresa_id}/documentos",
        files=[("arquivos", (f"a{i}.pdf", b"x", "application/pdf")) for i in range(3)],
    )

    assert response.status_code == 400
    assert "no máximo 2 arquivos" in response.json()["detail"]
