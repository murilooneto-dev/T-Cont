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
from app.api.routers import documentos_router
from app.infrastructure.db.base import Base
from app.infrastructure.db import models  # noqa: F401
from app.infrastructure.db.session import get_engine
from app.infrastructure.storage.file_storage import LocalFileStorageService
from app.infrastructure.workers.lote_worker import processar_lote_em_background
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
    assert body["extracao"] is None
    assert body["classificacao"] is None


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


def _pdf_com_texto(texto: str) -> bytes:
    documento = fitz.open()
    pagina = documento.new_page()
    pagina.insert_text((72, 72), texto)
    conteudo = documento.tobytes()
    documento.close()
    return conteudo


@dataclass
class Ambiente:
    client: TestClient
    session_factory: object
    storage_root: Path


@pytest.fixture
def ambiente_com_worker(tmp_path, monkeypatch):
    """Fixture that enables background lote worker processing for tests."""
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


def test_resultado_com_classificacao_apos_conta_deletada(ambiente_com_worker):
    """Regressão: GET /resultado deve retornar 200 com classificacao=None
    se a conta foi deletada, em vez de crashar com AttributeError."""
    from sqlalchemy import text

    client = ambiente_com_worker.client
    session_factory = ambiente_com_worker.session_factory

    # Criar empresa
    response = client.post(
        "/empresas", json={"razao_social": "Tesserato", "nome_fantasia": None, "cnpj": "12345678000199"}
    )
    empresa_id = response.json()["id"]

    # Criar plano de contas
    plano_id = client.post(
        f"/empresas/{empresa_id}/planos-contas", json={"nome": "Plano"}
    ).json()["id"]

    # Criar conta
    conta_id = client.post(
        f"/planos-contas/{plano_id}/contas",
        json={
            "codigo": "1", "descricao": "Energia", "natureza": "DESPESA",
            "conta_analitica": True, "conta_pai_id": None,
        },
    ).json()["id"]

    # Criar regra que classifica por CNPJ do recebedor
    client.post(
        f"/empresas/{empresa_id}/regras",
        json={
            "conta_id": conta_id, "lado_alvo": "RECEBEDOR",
            "documento_fiscal": "12345678000195", "tipo_documento": None,
            "valor_min": None, "valor_max": None, "palavra_chave_nome": None,
        },
    )

    # Upload documento com texto que vai casar a regra
    pdf_content = _pdf_com_texto(
        "Favorecido: Energisa\nCNPJ: 12.345.678/0001-95\nValor: R$ 100,00"
    )
    response = client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("comprovante.pdf", pdf_content, "application/pdf")},
    )
    documento_id = response.json()[0]["documento"]["id"]

    # Processar lote (sincronamente via TestClient)
    response = client.post(f"/empresas/{empresa_id}/documentos/processar")
    lote_id = response.json()["id"]

    # Aguardar conclusão
    status_final = None
    for _ in range(20):
        status_final = client.get(f"/lotes/{lote_id}").json()
        if status_final["status"] != "EM_ANDAMENTO":
            break
        time.sleep(0.5)

    assert status_final["status"] == "CONCLUIDO"

    # Verificar que classificação foi criada
    resultado = client.get(f"/documentos/{documento_id}/resultado").json()
    assert resultado["classificacao"] is not None
    assert resultado["classificacao"]["conta_id"] == conta_id
    assert resultado["classificacao"]["conta_codigo"] == "1"
    assert resultado["classificacao"]["conta_descricao"] == "Energia"

    # Simular deleção de conta mesmo com FK constraint (cenário que o fix protege).
    # Disable FK enforcement temporarily, delete the conta, then re-enable.
    session = session_factory()
    try:
        session.execute(text("PRAGMA foreign_keys=OFF"))
        session.execute(text(f"DELETE FROM contas WHERE id = {conta_id}"))
        session.commit()
    finally:
        session.execute(text("PRAGMA foreign_keys=ON"))
        session.close()

    # Chamar GET resultado novamente — deve retornar 200 com classificacao=None
    # (antes do fix, crashava com AttributeError produzindo 500)
    response = client.get(f"/documentos/{documento_id}/resultado")
    assert response.status_code == 200
    resultado = response.json()
    assert resultado["classificacao"] is None
    # Documento está intacto
    assert resultado["documento"]["id"] == documento_id
