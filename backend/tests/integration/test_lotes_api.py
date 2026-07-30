import functools
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db, get_storage
from app.domain.enums import StatusDocumento, StatusLote
from app.infrastructure.db.base import Base
from app.infrastructure.db import models  # noqa: F401
from app.infrastructure.db.session import get_engine
from app.infrastructure.repositories.sqlalchemy_documento_repository import (
    SqlAlchemyDocumentoRepository,
)
from app.infrastructure.repositories.sqlalchemy_lote_processamento_repository import (
    SqlAlchemyLoteProcessamentoRepository,
)
from app.infrastructure.storage import file_storage
from app.infrastructure.storage.file_storage import LocalFileStorageService
from app.infrastructure.workers.lote_worker import processar_lote_em_background
from app.main import app


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
    session_factory: Callable
    storage_root: Path


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
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
    monkeypatch.setattr("app.core.config.settings.storage_root", str(tmp_path))
    # O worker roda fora do escopo da request e abre a própria sessão. Em vez de
    # monkeypatchar o SessionLocal global, injetamos a fábrica de sessões deste
    # teste no ponto de composição (o router) via functools.partial — o worker
    # aceita `session_factory` justamente para isso.
    monkeypatch.setattr(
        "app.api.routers.lotes_router.processar_lote_em_background",
        functools.partial(processar_lote_em_background, session_factory=TestSessionLocal),
    )
    yield Ambiente(
        client=TestClient(app), session_factory=TestSessionLocal, storage_root=tmp_path
    )
    app.dependency_overrides.clear()


@pytest.fixture
def client(ambiente):
    return ambiente.client


@pytest.fixture
def empresa_id(client):
    response = client.post(
        "/empresas", json={"razao_social": "Tesserato", "nome_fantasia": None, "cnpj": "12345678000199"}
    )
    return response.json()["id"]


def _upload(client, empresa_id, nome: str, texto: str) -> int:
    response = client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": (nome, _pdf_com_texto(texto), "application/pdf")},
    )
    return response.json()[0]["documento"]["id"]


def test_processar_lote_ate_concluir(client, empresa_id):
    _upload(client, empresa_id, "comprovante.pdf", "COMPROVANTE TESTE INTEGRACAO 12345678901234567890")

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


def test_processar_sem_documentos_pendentes_retorna_400_e_nao_cria_lote(client, empresa_id):
    response = client.post(f"/empresas/{empresa_id}/documentos/processar")

    assert response.status_code == 400
    # Nenhum lote criado — antes, um lote com total_documentos=0 era criado e
    # ficava preso em EM_ANDAMENTO para sempre.
    assert client.get("/lotes/1").status_code == 404


def test_segunda_chamada_de_processar_nao_reprocessa_documentos_ja_reivindicados(
    ambiente, empresa_id
):
    client = ambiente.client
    _upload(client, empresa_id, "a.pdf", "COMPROVANTE A 12345678901234567890")

    primeira = client.post(f"/empresas/{empresa_id}/documentos/processar")
    assert primeira.status_code == 201

    # O TestClient executa BackgroundTasks de forma síncrona, então o lote já
    # terminou aqui; o ponto do teste é que o documento saiu da fila de
    # pendentes no momento em que o lote foi criado, e não ao final do batch.
    segunda = client.post(f"/empresas/{empresa_id}/documentos/processar")
    assert segunda.status_code == 400


def test_iniciar_processamento_marca_documentos_como_processando(ambiente, empresa_id):
    """Verifica a reivindicação (PROCESSANDO) sem deixar o worker rodar."""
    client = ambiente.client
    documento_id = _upload(client, empresa_id, "a.pdf", "COMPROVANTE A 12345678901234567890")

    from app.application.use_cases.lote_use_cases import IniciarProcessamentoUseCase
    from app.infrastructure.repositories.sqlalchemy_empresa_repository import (
        SqlAlchemyEmpresaRepository,
    )

    session = ambiente.session_factory()
    try:
        documento_repo = SqlAlchemyDocumentoRepository(session)
        _, documento_ids = IniciarProcessamentoUseCase(
            documento_repo,
            SqlAlchemyLoteProcessamentoRepository(session),
            SqlAlchemyEmpresaRepository(session),
        ).executar(empresa_id)
        session.commit()
        assert documento_ids == [documento_id]
        assert documento_repo.listar_pendentes_por_empresa(empresa_id) == []
    finally:
        session.close()

    resposta = client.get(f"/empresas/{empresa_id}/documentos")
    assert resposta.json()[0]["status"] == "PROCESSANDO"


def test_cancelar_lote_ja_concluido_retorna_409(client, empresa_id):
    _upload(client, empresa_id, "comprovante.pdf", "COMPROVANTE OUTRO TESTE 12345678901234567890")
    # O TestClient roda o BackgroundTask de forma síncrona: quando esta linha
    # retorna o lote já está CONCLUIDO.
    lote_id = client.post(f"/empresas/{empresa_id}/documentos/processar").json()["id"]

    response = client.post(f"/lotes/{lote_id}/cancelar")

    assert response.status_code == 409
    assert client.get(f"/lotes/{lote_id}").json()["status"] == "CONCLUIDO"


def test_obter_status_lote_inexistente_retorna_404(client):
    response = client.get("/lotes/999")
    assert response.status_code == 404


def _preparar_lote_sem_executar(ambiente, empresa_id, quantidade: int) -> tuple[int, list[int]]:
    """Faz upload de N documentos e cria o lote (reivindicando-os), sem rodar o worker."""
    from app.application.use_cases.lote_use_cases import IniciarProcessamentoUseCase
    from app.infrastructure.repositories.sqlalchemy_empresa_repository import (
        SqlAlchemyEmpresaRepository,
    )

    for indice in range(quantidade):
        _upload(
            ambiente.client, empresa_id, f"doc{indice}.pdf",
            f"COMPROVANTE {indice} 12345678901234567890",
        )

    session = ambiente.session_factory()
    try:
        lote, documento_ids = IniciarProcessamentoUseCase(
            SqlAlchemyDocumentoRepository(session),
            SqlAlchemyLoteProcessamentoRepository(session),
            SqlAlchemyEmpresaRepository(session),
        ).executar(empresa_id)
        session.commit()
        return lote.id, documento_ids
    finally:
        session.close()


def _ler_lote(ambiente, lote_id):
    session = ambiente.session_factory()
    try:
        return SqlAlchemyLoteProcessamentoRepository(session).obter_por_id(lote_id)
    finally:
        session.close()


def _ler_documento(ambiente, documento_id):
    session = ambiente.session_factory()
    try:
        return SqlAlchemyDocumentoRepository(session).obter_por_id(documento_id)
    finally:
        session.close()


def test_worker_marca_lote_como_falhou_quando_storage_falha(ambiente, empresa_id, monkeypatch):
    """Regressão: qualquer exceção no worker deixava o lote preso em EM_ANDAMENTO."""
    lote_id, documento_ids = _preparar_lote_sem_executar(ambiente, empresa_id, 1)

    class StorageQuebrado(LocalFileStorageService):
        def ler(self, caminho_relativo: str) -> bytes:
            raise FileNotFoundError(caminho_relativo)

    monkeypatch.setattr(file_storage, "LocalFileStorageService", StorageQuebrado)

    processar_lote_em_background(
        lote_id, documento_ids, str(ambiente.storage_root),
        session_factory=ambiente.session_factory,
    )

    lote = _ler_lote(ambiente, lote_id)
    assert lote.status == StatusLote.FALHOU
    assert lote.concluido_em is not None


def test_worker_para_de_submeter_apos_cancelamento(ambiente, empresa_id, monkeypatch):
    """Cancelamento real: o worker é chamado direto, sem depender do TestClient."""
    lote_id, documento_ids = _preparar_lote_sem_executar(ambiente, empresa_id, 3)
    session_factory = ambiente.session_factory

    class StorageQueCancela(LocalFileStorageService):
        """Cancela o lote logo após a primeira leitura, simulando um usuário
        clicando em "Cancelar" no meio da submissão do batch."""

        def ler(self, caminho_relativo: str) -> bytes:
            conteudo = super().ler(caminho_relativo)
            session = session_factory()
            try:
                repo = SqlAlchemyLoteProcessamentoRepository(session)
                lote = repo.obter_por_id(lote_id)
                if lote.status == StatusLote.EM_ANDAMENTO:
                    lote.status = StatusLote.CANCELADO
                    repo.atualizar(lote)
                    session.commit()
            finally:
                session.close()
            return conteudo

    monkeypatch.setattr(file_storage, "LocalFileStorageService", StorageQueCancela)

    processar_lote_em_background(
        lote_id, documento_ids, str(ambiente.storage_root), session_factory=session_factory
    )

    lote = _ler_lote(ambiente, lote_id)
    assert lote.status == StatusLote.CANCELADO
    # Só o primeiro documento chegou a ser submetido ao pool.
    assert lote.documentos_processados == 1
    assert _ler_documento(ambiente, documento_ids[0]).status == StatusDocumento.CONCLUIDO
    # Os demais nunca chegaram a ser processados: voltam para PENDENTE em vez
    # de ficarem presos em PROCESSANDO para sempre (regressão do commit
    # caf4ebd — antes ficavam PROCESSANDO e nunca mais eram selecionáveis por
    # um lote futuro).
    for documento_id in documento_ids[1:]:
        assert _ler_documento(ambiente, documento_id).status == StatusDocumento.PENDENTE


def test_cancelar_lote_em_andamento_via_api(ambiente, empresa_id):
    lote_id, _ = _preparar_lote_sem_executar(ambiente, empresa_id, 1)

    response = ambiente.client.post(f"/lotes/{lote_id}/cancelar")

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELADO"
    # Segundo cancelamento é rejeitado.
    assert ambiente.client.post(f"/lotes/{lote_id}/cancelar").status_code == 409


def test_cancelar_lote_inexistente_retorna_404(client):
    assert client.post("/lotes/999/cancelar").status_code == 404


def test_worker_reseta_documentos_processando_para_pendente_quando_lote_falha(
    ambiente, empresa_id, monkeypatch
):
    """Regressão: sem o reset, um documento PROCESSANDO de um lote que FALHOU
    ficava preso para sempre — nunca mais aparecia em
    `listar_pendentes_por_empresa`, e `POST .../processar` retornava 400
    NenhumDocumentoPendente indefinidamente."""
    lote_id, documento_ids = _preparar_lote_sem_executar(ambiente, empresa_id, 1)

    class StorageQuebrado(LocalFileStorageService):
        def ler(self, caminho_relativo: str) -> bytes:
            raise FileNotFoundError(caminho_relativo)

    monkeypatch.setattr(file_storage, "LocalFileStorageService", StorageQuebrado)

    processar_lote_em_background(
        lote_id, documento_ids, str(ambiente.storage_root),
        session_factory=ambiente.session_factory,
    )

    lote = _ler_lote(ambiente, lote_id)
    assert lote.status == StatusLote.FALHOU
    assert _ler_documento(ambiente, documento_ids[0]).status == StatusDocumento.PENDENTE


def test_novo_lote_pode_ser_iniciado_apos_lote_anterior_falhar(ambiente, empresa_id, monkeypatch):
    """Caminho de recuperação real: depois que o fix devolve os documentos
    presos para PENDENTE, um novo POST .../processar deve conseguir
    reivindicá-los em vez de continuar retornando 400 para sempre."""
    client = ambiente.client
    lote_id, documento_ids = _preparar_lote_sem_executar(ambiente, empresa_id, 1)

    class StorageQuebrado(LocalFileStorageService):
        def ler(self, caminho_relativo: str) -> bytes:
            raise FileNotFoundError(caminho_relativo)

    # Escopo isolado (`monkeypatch.context()`) para que o patch do storage
    # quebrado seja revertido sozinho ao sair do `with`, sem afetar os outros
    # patches feitos pela fixture `ambiente` (session_factory do worker etc).
    with monkeypatch.context() as m:
        m.setattr(file_storage, "LocalFileStorageService", StorageQuebrado)
        processar_lote_em_background(
            lote_id, documento_ids, str(ambiente.storage_root),
            session_factory=ambiente.session_factory,
        )
    assert _ler_lote(ambiente, lote_id).status == StatusLote.FALHOU

    resposta = client.post(f"/empresas/{empresa_id}/documentos/processar")

    assert resposta.status_code == 201
    novo_lote = resposta.json()
    assert novo_lote["id"] != lote_id
    assert novo_lote["total_documentos"] == 1

    status_final = None
    for _ in range(20):
        status_final = client.get(f"/lotes/{novo_lote['id']}").json()
        if status_final["status"] != "EM_ANDAMENTO":
            break
        time.sleep(0.5)

    assert status_final["status"] == "CONCLUIDO"
    assert status_final["documentos_processados"] == 1


def test_processar_lote_extrai_dados_do_documento(client, empresa_id):
    conteudo = _pdf_com_texto(
        "Comprovante de Transferencia PIX\n"
        "Pagador: Joao da Silva\n"
        "CPF: 123.456.789-00\n"
        "Favorecido: Energisa\n"
        "CNPJ: 12.345.678/0001-95\n"
        "Valor: R$ 250,00\n"
        "Data do pagamento: 20/04/2026\n"
    )
    client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("comprovante.pdf", conteudo, "application/pdf")},
    )

    response = client.post(f"/empresas/{empresa_id}/documentos/processar")
    lote_id = response.json()["id"]

    status_final = None
    for _ in range(20):
        status_final = client.get(f"/lotes/{lote_id}").json()
        if status_final["status"] != "EM_ANDAMENTO":
            break
        time.sleep(0.5)

    assert status_final["status"] == "CONCLUIDO"

    documentos = client.get(f"/empresas/{empresa_id}/documentos").json()
    documento_id = documentos[0]["id"]
    resultado = client.get(f"/documentos/{documento_id}/resultado").json()

    assert resultado["extracao"]["tipo_documento"] == "PIX"
    assert resultado["extracao"]["pagador_nome"] == "JOAO DA SILVA"
    assert resultado["extracao"]["pagador_documento"] == "12345678900"
    assert resultado["extracao"]["recebedor_nome"] == "ENERGISA"
    assert resultado["extracao"]["recebedor_documento"] == "12345678000195"
    assert resultado["extracao"]["valor"] == "250.00"
    assert resultado["extracao"]["data_pagamento"] == "2026-04-20"


def test_processar_lote_classifica_documento_por_regra(client, empresa_id):
    plano_id = client.post(
        f"/empresas/{empresa_id}/planos-contas", json={"nome": "Plano"}
    ).json()["id"]
    conta_id = client.post(
        f"/planos-contas/{plano_id}/contas",
        json={
            "codigo": "1", "descricao": "Energia", "natureza": "DESPESA",
            "conta_analitica": True, "conta_pai_id": None,
        },
    ).json()["id"]
    client.post(
        f"/empresas/{empresa_id}/regras",
        json={
            "conta_id": conta_id, "lado_alvo": "RECEBEDOR",
            "documento_fiscal": "12345678000195", "tipo_documento": None,
            "valor_min": None, "valor_max": None, "palavra_chave_nome": None,
        },
    )

    _upload(
        client, empresa_id, "comprovante.pdf",
        "Favorecido: Energisa\nCNPJ: 12.345.678/0001-95\nValor: R$ 100,00",
    )
    response = client.post(f"/empresas/{empresa_id}/documentos/processar")
    lote_id = response.json()["id"]

    status_final = None
    for _ in range(20):
        status_final = client.get(f"/lotes/{lote_id}").json()
        if status_final["status"] != "EM_ANDAMENTO":
            break
        time.sleep(0.5)
    assert status_final["status"] == "CONCLUIDO"

    documentos = client.get(f"/empresas/{empresa_id}/documentos").json()
    documento_id = documentos[0]["id"]
    resultado = client.get(f"/documentos/{documento_id}/resultado").json()

    assert resultado["classificacao"]["conta_id"] == conta_id
    assert resultado["classificacao"]["origem"] == "REGRA"


def test_processar_lote_classifica_por_fuzzy_usando_documento_anterior_do_mesmo_lote(client, empresa_id):
    plano_id = client.post(
        f"/empresas/{empresa_id}/planos-contas", json={"nome": "Plano"}
    ).json()["id"]
    conta_id = client.post(
        f"/planos-contas/{plano_id}/contas",
        json={
            "codigo": "1", "descricao": "Energia", "natureza": "DESPESA",
            "conta_analitica": True, "conta_pai_id": None,
        },
    ).json()["id"]
    client.post(
        f"/empresas/{empresa_id}/regras",
        json={
            "conta_id": conta_id, "lado_alvo": "RECEBEDOR",
            "documento_fiscal": "12345678000195", "tipo_documento": None,
            "valor_min": None, "valor_max": None, "palavra_chave_nome": None,
        },
    )

    _upload(
        client, empresa_id, "primeiro.pdf",
        "Favorecido: Energisa Ceara\nCNPJ: 12.345.678/0001-95\nValor: R$ 100,00",
    )
    _upload(
        client, empresa_id, "segundo.pdf",
        "Favorecido: Energisa Cear\nCNPJ: 98.765.432/0001-10\nValor: R$ 50,00",
    )

    response = client.post(f"/empresas/{empresa_id}/documentos/processar")
    lote_id = response.json()["id"]

    status_final = None
    for _ in range(20):
        status_final = client.get(f"/lotes/{lote_id}").json()
        if status_final["status"] != "EM_ANDAMENTO":
            break
        time.sleep(0.5)
    assert status_final["status"] == "CONCLUIDO"

    documentos = client.get(f"/empresas/{empresa_id}/documentos").json()
    documento_ids_por_nome = {d["nome_exibicao"]: d["id"] for d in documentos}

    resultado_primeiro = client.get(
        f"/documentos/{documento_ids_por_nome['primeiro.pdf']}/resultado"
    ).json()
    assert resultado_primeiro["classificacao"]["origem"] == "REGRA"

    resultado_segundo = client.get(
        f"/documentos/{documento_ids_por_nome['segundo.pdf']}/resultado"
    ).json()
    assert resultado_segundo["classificacao"] is not None
    assert resultado_segundo["classificacao"]["conta_id"] == conta_id
    assert resultado_segundo["classificacao"]["origem"] == "FUZZY"
