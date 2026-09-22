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


def test_pdf_de_uma_pagina_processa_identico_ao_comportamento_atual(ambiente_com_worker):
    # Regressão: o caso de 1 segmento não pode virar DIVIDIDO nem ganhar filhos.
    client = ambiente_com_worker
    empresa_id = client.post(
        "/empresas", json={"razao_social": "Teste", "nome_fantasia": None, "cnpj": "12345678000199"}
    ).json()["id"]

    conteudo = _pdf_com_paginas("Favorecido: Teste\nCNPJ: 11.222.333/0001-99\nValor: R$ 50,00")
    documento_id = client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("comprovante.pdf", conteudo, "application/pdf")},
    ).json()[0]["documento"]["id"]

    status_final = _processar_e_aguardar(client, empresa_id)
    assert status_final["status"] == "CONCLUIDO"

    resultado = client.get(f"/documentos/{documento_id}/resultado").json()
    assert resultado["documento"]["status"] == "CONCLUIDO"
    assert resultado["documento"]["documento_origem_id"] is None
    assert resultado["extracao"] is not None
    assert resultado["extracao"]["valor"] == "50.00"

    todos = client.get(f"/empresas/{empresa_id}/documentos").json()
    assert len(todos) == 1  # nenhum filho foi criado


def test_pdf_de_duas_paginas_com_dois_comprovantes_cria_dois_filhos(ambiente_com_worker):
    client = ambiente_com_worker
    empresa_id = client.post(
        "/empresas", json={"razao_social": "Teste", "nome_fantasia": None, "cnpj": "12345678000199"}
    ).json()["id"]

    conteudo = _pdf_com_paginas(
        "Favorecido: Fornecedor Um\nCNPJ: 11.222.333/0001-99\nValor: R$ 50,00",
        "Favorecido: Fornecedor Dois\nCNPJ: 44.555.666/0001-77\nValor: R$ 80,00",
    )
    documento_original_id = client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("unificado.pdf", conteudo, "application/pdf")},
    ).json()[0]["documento"]["id"]

    status_final = _processar_e_aguardar(client, empresa_id)
    assert status_final["status"] == "CONCLUIDO"

    original = client.get(f"/documentos/{documento_original_id}/resultado").json()
    assert original["documento"]["status"] == "DIVIDIDO"
    assert original["extracao"] is None
    assert original["classificacao"] is None

    todos = client.get(f"/empresas/{empresa_id}/documentos").json()
    filhos = [d for d in todos if d["documento_origem_id"] == documento_original_id]
    assert len(filhos) == 2

    resultados_filhos = [
        client.get(f"/documentos/{f['id']}/resultado").json() for f in filhos
    ]
    valores = sorted(r["extracao"]["valor"] for r in resultados_filhos)
    assert valores == ["50.00", "80.00"]
    assert all(f["status"] == "CONCLUIDO" for f in filhos)
    assert "pág." in filhos[0]["nome_exibicao"]


def test_comprovante_de_duas_paginas_dentro_de_arquivo_unificado_fica_junto(ambiente_com_worker):
    # A segunda página (sem CNPJ/valor) é continuação da primeira; a terceira
    # é um comprovante novo e completo. Resultado esperado: 2 comprovantes,
    # o primeiro ocupando 2 páginas.
    client = ambiente_com_worker
    empresa_id = client.post(
        "/empresas", json={"razao_social": "Teste", "nome_fantasia": None, "cnpj": "12345678000199"}
    ).json()["id"]

    conteudo = _pdf_com_paginas(
        "Favorecido: Fornecedor Um\nCNPJ: 11.222.333/0001-99\nValor: R$ 50,00",
        "Detalhamento do boleto, sem dados novos de pagamento.",
        "Favorecido: Fornecedor Dois\nCNPJ: 44.555.666/0001-77\nValor: R$ 80,00",
    )
    documento_original_id = client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("unificado.pdf", conteudo, "application/pdf")},
    ).json()[0]["documento"]["id"]

    _processar_e_aguardar(client, empresa_id)

    todos = client.get(f"/empresas/{empresa_id}/documentos").json()
    filhos = [d for d in todos if d["documento_origem_id"] == documento_original_id]
    assert len(filhos) == 2
    nomes = sorted(f["nome_exibicao"] for f in filhos)
    assert "pág. 1-2" in nomes[0]
    assert "pág. 3" in nomes[1]


def test_lote_conta_arquivo_original_uma_vez_mesmo_quando_vira_varios_comprovantes(ambiente_com_worker):
    client = ambiente_com_worker
    empresa_id = client.post(
        "/empresas", json={"razao_social": "Teste", "nome_fantasia": None, "cnpj": "12345678000199"}
    ).json()["id"]

    conteudo = _pdf_com_paginas(
        "Favorecido: Fornecedor Um\nCNPJ: 11.222.333/0001-99\nValor: R$ 50,00",
        "Favorecido: Fornecedor Dois\nCNPJ: 44.555.666/0001-77\nValor: R$ 80,00",
    )
    client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("unificado.pdf", conteudo, "application/pdf")},
    )

    status_final = _processar_e_aguardar(client, empresa_id)

    assert status_final["total_documentos"] == 1
    assert status_final["documentos_processados"] == 1
