import functools
import time

import fitz
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db, get_storage
from app.domain.enums import DirecaoLancamento
from app.infrastructure.db.base import Base
from app.infrastructure.db import models  # noqa: F401
from app.infrastructure.db.session import get_engine
from app.infrastructure.repositories.sqlalchemy_classificacao_repository import (
    SqlAlchemyClassificacaoRepository,
)
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
    client = TestClient(app)
    # Exposto para testes que precisam inspecionar dados persistidos que a
    # API ainda não expõe (ex.: `Classificacao.direcao`/`conta_bancaria_id`,
    # cujo schema de saída é responsabilidade de uma tarefa posterior).
    client.session_factory = TestSessionLocal
    yield client
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


def _empresa_e_plano_com_banco(client, cnpj: str, nome_banco: str) -> tuple[int, int, int]:
    empresa_id = client.post(
        "/empresas", json={"razao_social": "Teste", "nome_fantasia": None, "cnpj": cnpj}
    ).json()["id"]
    plano_id = client.post(
        f"/empresas/{empresa_id}/planos-contas", json={"nome": "Plano"}
    ).json()["id"]
    conta_despesa_id = client.post(
        f"/planos-contas/{plano_id}/contas",
        json={
            "codigo": "3.2.01", "descricao": "Despesa Teste", "natureza": "DESPESA",
            "conta_analitica": True, "conta_pai_id": None,
        },
    ).json()["id"]
    conta_banco_id = client.post(
        f"/planos-contas/{plano_id}/contas",
        json={
            "codigo": "1.1.01.002.00001", "descricao": nome_banco, "natureza": "ATIVO",
            "conta_analitica": True, "conta_pai_id": None,
        },
    ).json()["id"]
    return empresa_id, conta_despesa_id, conta_banco_id


def _obter_classificacao_persistida(client, documento_id: int):
    # A API (`/documentos/{id}/resultado`) ainda não expõe `direcao`/
    # `conta_bancaria_id` no `ClassificacaoOut` — isso é responsabilidade de
    # uma tarefa posterior do plano (schema de saída). Esta tarefa só cuida
    # da persistência feita pelo worker, então inspecionamos o dado
    # diretamente via repositório, usando a mesma fábrica de sessão do
    # ambiente de teste.
    session = client.session_factory()
    try:
        repo = SqlAlchemyClassificacaoRepository(session)
        return repo.obter_por_documento_id(documento_id)
    finally:
        session.close()


def test_pagamento_resolve_direcao_e_conta_bancaria(ambiente_com_worker):
    client = ambiente_com_worker
    cnpj_empresa = "12345678000199"
    empresa_id, conta_despesa_id, conta_banco_id = _empresa_e_plano_com_banco(
        client, cnpj_empresa, "Banco do Brasil S.A."
    )
    client.post(
        f"/empresas/{empresa_id}/regras",
        json={
            "conta_id": conta_despesa_id, "lado_alvo": "RECEBEDOR",
            "documento_fiscal": "99988877000166", "tipo_documento": None,
            "valor_min": None, "valor_max": None, "palavra_chave_nome": None,
        },
    )
    conteudo = _pdf_com_paginas(
        "CNPJ DO PAGADOR: 12.345.678/0001-99\nFavorecido: Fornecedor Teste\n"
        "CNPJ DO RECEBEDOR: 99.988.877/0001-66\nBanco: Banco do Brasil S.A.\n"
        "Valor: R$ 150,00"
    )
    documento_id = client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("comprovante.pdf", conteudo, "application/pdf")},
    ).json()[0]["documento"]["id"]

    status_final = _processar_e_aguardar(client, empresa_id)
    assert status_final["status"] == "CONCLUIDO"

    classificacao = _obter_classificacao_persistida(client, documento_id)
    assert classificacao is not None
    assert classificacao.direcao == DirecaoLancamento.PAGAMENTO
    assert classificacao.conta_id == conta_despesa_id
    assert classificacao.conta_bancaria_id == conta_banco_id


def test_banco_nao_identificado_deixa_conta_bancaria_nao_resolvida(ambiente_com_worker):
    client = ambiente_com_worker
    cnpj_empresa = "12345678000199"
    empresa_id, conta_despesa_id, _ = _empresa_e_plano_com_banco(
        client, cnpj_empresa, "Banco do Brasil S.A."
    )
    client.post(
        f"/empresas/{empresa_id}/regras",
        json={
            "conta_id": conta_despesa_id, "lado_alvo": "RECEBEDOR",
            "documento_fiscal": "99988877000166", "tipo_documento": None,
            "valor_min": None, "valor_max": None, "palavra_chave_nome": None,
        },
    )
    conteudo = _pdf_com_paginas(
        "CNPJ DO PAGADOR: 12.345.678/0001-99\nFavorecido: Fornecedor Teste\n"
        "CNPJ DO RECEBEDOR: 99.988.877/0001-66\nValor: R$ 150,00"
    )
    documento_id = client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("comprovante.pdf", conteudo, "application/pdf")},
    ).json()[0]["documento"]["id"]

    status_final = _processar_e_aguardar(client, empresa_id)
    assert status_final["status"] == "CONCLUIDO"

    classificacao = _obter_classificacao_persistida(client, documento_id)
    assert classificacao is not None
    assert classificacao.direcao == DirecaoLancamento.PAGAMENTO
    assert classificacao.conta_id == conta_despesa_id
    assert classificacao.conta_bancaria_id is None


def test_pdf_de_uma_pagina_continua_sem_classificacao_bancaria_quando_nao_ha_cnpj_da_empresa(
    ambiente_com_worker,
):
    # Regressão do caminho de 1 segmento: quando o documento não tem nenhum
    # documento fiscal batendo com a empresa, direção fica None e a conta
    # bancária fica None — sem quebrar o processamento.
    client = ambiente_com_worker
    empresa_id, conta_despesa_id, _ = _empresa_e_plano_com_banco(
        client, "12345678000199", "Banco do Brasil S.A."
    )
    conteudo = _pdf_com_paginas("Texto sem nenhum CNPJ reconhecivel\nValor: R$ 10,00")
    documento_id = client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("comprovante.pdf", conteudo, "application/pdf")},
    ).json()[0]["documento"]["id"]

    status_final = _processar_e_aguardar(client, empresa_id)
    assert status_final["status"] == "CONCLUIDO"
