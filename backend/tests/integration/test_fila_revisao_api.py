import functools
import time
from dataclasses import dataclass
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db, get_storage
from app.infrastructure.db.base import Base
from app.infrastructure.db import models  # noqa: F401
from app.infrastructure.db.session import get_engine
from app.infrastructure.storage.file_storage import LocalFileStorageService
from app.infrastructure.workers.lote_worker import processar_lote_em_background
from app.main import app


@pytest.fixture
def client(tmp_path):
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


def test_fila_revisao_vazia_quando_sem_documentos(client, empresa_id):
    response = client.get(f"/empresas/{empresa_id}/documentos/fila-revisao")
    assert response.status_code == 200
    assert response.json() == []


def test_fila_revisao_ignora_documento_pendente(client, empresa_id):
    client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("a.pdf", b"conteudo", "application/pdf")},
    )

    response = client.get(f"/empresas/{empresa_id}/documentos/fila-revisao")
    assert response.status_code == 200
    assert response.json() == []


@dataclass
class Ambiente:
    client: TestClient
    session_factory: object
    storage_root: Path


@pytest.fixture
def ambiente_com_worker(tmp_path, monkeypatch):
    """Reaproveita o mesmo padrão de test_documentos_api.py: habilita o
    processamento síncrono do worker de lote dentro do TestClient, para que
    um documento realmente chegue a status=CONCLUIDO sem mock de sessão."""
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
    monkeypatch.setattr("app.core.config.settings.storage_root", str(tmp_path))
    monkeypatch.setattr(
        "app.api.routers.lotes_router.processar_lote_em_background",
        functools.partial(processar_lote_em_background, session_factory=TestSessionLocal),
    )
    yield Ambiente(
        client=TestClient(app), session_factory=TestSessionLocal, storage_root=tmp_path
    )
    app.dependency_overrides.clear()


def _pdf_sem_dados_extraiveis() -> bytes:
    documento = fitz.open()
    pagina = documento.new_page()
    pagina.insert_text((72, 72), "Texto sem CNPJ, CPF ou valor reconhecivel.")
    conteudo = documento.tobytes()
    documento.close()
    return conteudo


def test_fila_revisao_inclui_documento_concluido_sem_classificacao(ambiente_com_worker):
    client = ambiente_com_worker.client
    empresa_id = client.post(
        "/empresas", json={"razao_social": "Tesserato", "nome_fantasia": None, "cnpj": "12345678000199"}
    ).json()["id"]

    documento_id = client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("a.pdf", _pdf_sem_dados_extraiveis(), "application/pdf")},
    ).json()[0]["documento"]["id"]

    lote_id = client.post(f"/empresas/{empresa_id}/documentos/processar").json()["id"]
    status_final = None
    for _ in range(20):
        status_final = client.get(f"/lotes/{lote_id}").json()
        if status_final["status"] != "EM_ANDAMENTO":
            break
        time.sleep(0.5)
    assert status_final["status"] == "CONCLUIDO"

    response = client.get(f"/empresas/{empresa_id}/documentos/fila-revisao")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["documento"]["id"] == documento_id
    assert body[0]["classificacao_sugerida"] is None
