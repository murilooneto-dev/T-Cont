import functools
import time

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
def ambiente_com_worker(tmp_path, monkeypatch):
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
    yield TestClient(app)
    app.dependency_overrides.clear()


def _pdf_com_paginas(*textos: str) -> bytes:
    documento = fitz.open()
    for texto in textos:
        pagina = documento.new_page()
        pagina.insert_text((72, 72), texto)
    conteudo = documento.tobytes()
    documento.close()
    return conteudo


def _processar_e_aguardar(client, empresa_id):
    lote_id = client.post(f"/empresas/{empresa_id}/documentos/processar").json()["id"]
    status_final = None
    for _ in range(30):
        status_final = client.get(f"/lotes/{lote_id}").json()
        if status_final["status"] != "EM_ANDAMENTO":
            break
        time.sleep(0.5)
    return status_final


def test_limpar_fila_revisao_apaga_documento_sem_classificacao(ambiente_com_worker):
    client = ambiente_com_worker
    empresa_id = client.post(
        "/empresas", json={"razao_social": "Teste", "nome_fantasia": None, "cnpj": "12345678000199"}
    ).json()["id"]
    conteudo = _pdf_com_paginas("Texto sem nenhum CNPJ reconhecivel\nValor: R$ 10,00")
    documento_id = client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("comprovante.pdf", conteudo, "application/pdf")},
    ).json()[0]["documento"]["id"]

    status_final = _processar_e_aguardar(client, empresa_id)
    assert status_final["status"] == "CONCLUIDO"

    fila_antes = client.get(f"/empresas/{empresa_id}/documentos/fila-revisao").json()
    assert len(fila_antes) == 1

    resposta = client.delete(f"/empresas/{empresa_id}/documentos/fila-revisao")
    assert resposta.status_code == 200
    assert resposta.json()["documentos_apagados"] == 1

    assert client.get(f"/empresas/{empresa_id}/documentos/fila-revisao").json() == []
    assert client.get(f"/documentos/{documento_id}/resultado").status_code == 404


def test_limpar_documentos_processados_apaga_dividido_e_filhos_sem_quebrar_fk(ambiente_com_worker):
    client = ambiente_com_worker
    empresa_id = client.post(
        "/empresas", json={"razao_social": "Teste", "nome_fantasia": None, "cnpj": "12345678000199"}
    ).json()["id"]
    conteudo = _pdf_com_paginas(
        "Favorecido: Loja A\nCNPJ: 11.222.333/0001-99\nValor: R$ 50,00",
        "Favorecido: Loja B\nCNPJ: 22.333.444/0001-99\nValor: R$ 60,00",
    )
    client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("unificado.pdf", conteudo, "application/pdf")},
    )

    status_final = _processar_e_aguardar(client, empresa_id)
    assert status_final["status"] == "CONCLUIDO"

    todos_antes = client.get(f"/empresas/{empresa_id}/documentos").json()
    assert len(todos_antes) == 3  # pai DIVIDIDO + 2 filhos CONCLUIDO

    resposta = client.delete(f"/empresas/{empresa_id}/documentos/processados")
    assert resposta.status_code == 200
    assert resposta.json()["documentos_apagados"] == 3

    todos_depois = client.get(f"/empresas/{empresa_id}/documentos").json()
    assert todos_depois == []


def test_limpar_documentos_processados_nao_apaga_pendente(ambiente_com_worker):
    client = ambiente_com_worker
    empresa_id = client.post(
        "/empresas", json={"razao_social": "Teste", "nome_fantasia": None, "cnpj": "12345678000199"}
    ).json()["id"]
    conteudo = _pdf_com_paginas("Texto qualquer\nValor: R$ 10,00")
    documento_id = client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("comprovante.pdf", conteudo, "application/pdf")},
    ).json()[0]["documento"]["id"]

    resposta = client.delete(f"/empresas/{empresa_id}/documentos/processados")
    assert resposta.status_code == 200
    assert resposta.json()["documentos_apagados"] == 0

    resultado = client.get(f"/documentos/{documento_id}/resultado")
    assert resultado.status_code == 200
    assert resultado.json()["documento"]["status"] == "PENDENTE"
