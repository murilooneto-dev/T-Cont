# Fase 5 — Interface de Revisão/Edição — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Fila de Revisão" queue that surfaces documents needing human attention (no classification, or a FUZZY suggestion), with individual confirm/correct actions, batch correction across a checkbox selection, and basic keyboard navigation.

**Architecture:** No new tables/columns. The queue is a derived read (documents with no `Classificacao`, or `origem=FUZZY`, restricted to `status=CONCLUIDO`) exposed via a new `GET /empresas/{empresa_id}/documentos/fila-revisao` endpoint. Batch correction is a new `PATCH /documentos/classificacao/lote` endpoint that loops the existing Fase 4 `CorrigirClassificacaoUseCase` per document, tolerating partial failure. The individual "Confirmar" action reuses the existing Fase 4 `PATCH /documentos/{id}/classificacao` endpoint unchanged. Frontend adds a shared `CorrecaoClassificacao` component (extracted from `DocumentoList.tsx`) and a new `FilaRevisao.tsx` component, wired as a second tab inside `EmpresasPage.tsx`.

**Tech Stack:** FastAPI + Pydantic + SQLAlchemy (backend, unchanged), React + TypeScript + Tailwind (frontend, unchanged). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-18-fase5-interface-revisao-design.md`

## Global Constraints

- No new DB migration, table, or column — this phase is 100% new queries/endpoints over existing data (per spec's "Critério de inclusão na fila").
- Queue query filters in memory over `documento_repo.listar_por_empresa(empresa_id)` — no new repository method, no raw SQL (per spec: volume is "poucas dezenas", same simplicity precedent as existing queries).
- A document only enters the "sem classificação" branch of the queue if `documento.status == StatusDocumento.CONCLUIDO` — a `PENDENTE`/`PROCESSANDO`/`ERRO` document has no classification attempt yet (or OCR itself failed), which is not the same as "classification ran and found nothing." This rule is implied by the spec's intent but not spelled out verbatim in it; it must hold across every task that touches the queue's filter logic.
- Individual "Confirmar" reuses `PATCH /documentos/{id}/classificacao` unmodified — no new backend code for it (per spec's "Confirmação individual (sem endpoint novo)").
- Batch correction tolerates partial failure — one item failing must not stop or roll back the others (per spec, same principle as Fases 1-3's lote processing).
- Follow existing code style: Portuguese domain names, dataclass entities, `Fake*Repository` unit tests + `TestClient` integration tests, `get_engine()` (never raw `create_engine()`) in any new integration test fixture.

---

## Task 1: Domain use case — listar fila de revisão

**Files:**
- Create: `backend/app/application/use_cases/fila_revisao_use_cases.py`
- Test: `backend/tests/unit/test_fila_revisao_use_cases.py`

**Interfaces:**
- Consumes: `DocumentoRepository.listar_por_empresa(empresa_id) -> list[Documento]`, `ExtracaoRepository.obter_por_documento_id(documento_id) -> Extracao | None`, `ClassificacaoRepository.obter_por_documento_id(documento_id) -> Classificacao | None`, `ContaRepository.obter_por_id(conta_id) -> Conta | None` (all from `backend/app/application/repositories.py`, already implemented by `Fake*Repository` in `backend/tests/fakes.py`).
- Produces: `ItemFilaRevisao` and `SugestaoFilaRevisao` dataclasses, and `ListarFilaRevisaoUseCase.executar(empresa_id: int) -> list[ItemFilaRevisao]` — Task 2's endpoint consumes this exact signature and these exact field names.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_fila_revisao_use_cases.py`:

```python
import pytest

from app.application.use_cases.fila_revisao_use_cases import ListarFilaRevisaoUseCase
from app.domain.entities import Classificacao, Conta, Documento, Extracao, PlanoContas
from app.domain.enums import NaturezaConta, OrigemClassificacao, StatusDocumento, TipoDocumento
from tests.fakes import (
    FakeClassificacaoRepository,
    FakeContaRepository,
    FakeDocumentoRepository,
    FakeExtracaoRepository,
    FakePlanoContasRepository,
)


def _ambiente():
    documento_repo = FakeDocumentoRepository()
    extracao_repo = FakeExtracaoRepository()
    classificacao_repo = FakeClassificacaoRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    plano = plano_repo.criar(PlanoContas(id=None, empresa_id=1, nome="Plano"))
    conta = conta_repo.criar(
        Conta(
            id=None, plano_conta_id=plano.id, codigo="1", descricao="Energia",
            natureza=NaturezaConta.DESPESA, conta_analitica=True,
        )
    )
    return {
        "documento_repo": documento_repo, "extracao_repo": extracao_repo,
        "classificacao_repo": classificacao_repo, "conta_repo": conta_repo, "conta": conta,
    }


def _documento(ambiente, status=StatusDocumento.CONCLUIDO):
    return ambiente["documento_repo"].criar(
        Documento(
            id=None, empresa_id=1, nome_arquivo="a.pdf", nome_exibicao="a.pdf",
            caminho_arquivo="x/a.pdf", extensao=".pdf", tamanho_bytes=10, status=status,
        )
    )


def _use_case(ambiente):
    return ListarFilaRevisaoUseCase(
        ambiente["documento_repo"], ambiente["extracao_repo"],
        ambiente["classificacao_repo"], ambiente["conta_repo"],
    )


def test_documento_concluido_sem_classificacao_entra_na_fila():
    ambiente = _ambiente()
    documento = _documento(ambiente)

    itens = _use_case(ambiente).executar(1)

    assert len(itens) == 1
    assert itens[0].documento.id == documento.id
    assert itens[0].sugestao is None


def test_documento_pendente_sem_classificacao_nao_entra_na_fila():
    ambiente = _ambiente()
    _documento(ambiente, status=StatusDocumento.PENDENTE)

    itens = _use_case(ambiente).executar(1)

    assert itens == []


def test_documento_com_erro_nao_entra_na_fila():
    ambiente = _ambiente()
    _documento(ambiente, status=StatusDocumento.ERRO)

    itens = _use_case(ambiente).executar(1)

    assert itens == []


@pytest.mark.parametrize("origem", [OrigemClassificacao.REGRA, OrigemClassificacao.IA, OrigemClassificacao.MANUAL])
def test_classificacao_por_regra_ia_ou_manual_nao_entra_na_fila(origem):
    ambiente = _ambiente()
    documento = _documento(ambiente)
    ambiente["classificacao_repo"].criar(
        Classificacao(
            id=None, empresa_id=1, documento_id=documento.id, conta_id=ambiente["conta"].id,
            origem=origem,
        )
    )

    itens = _use_case(ambiente).executar(1)

    assert itens == []


def test_classificacao_fuzzy_entra_na_fila_com_sugestao():
    ambiente = _ambiente()
    documento = _documento(ambiente)
    ambiente["extracao_repo"].criar(
        Extracao(
            id=None, documento_id=documento.id, pagador_nome=None, pagador_documento=None,
            recebedor_nome="Loja X", recebedor_documento=None, valor=None,
            data_pagamento=None, tipo_documento=TipoDocumento.OUTRO, banco_nome=None,
        )
    )
    ambiente["classificacao_repo"].criar(
        Classificacao(
            id=None, empresa_id=1, documento_id=documento.id, conta_id=ambiente["conta"].id,
            origem=OrigemClassificacao.FUZZY, score_similaridade=0.42,
        )
    )

    itens = _use_case(ambiente).executar(1)

    assert len(itens) == 1
    item = itens[0]
    assert item.extracao is not None
    assert item.extracao.recebedor_nome == "Loja X"
    assert item.sugestao is not None
    assert item.sugestao.conta_id == ambiente["conta"].id
    assert item.sugestao.conta_codigo == "1"
    assert item.sugestao.conta_descricao == "Energia"
    assert item.sugestao.score_similaridade == 0.42


def test_filtra_apenas_pela_empresa_informada():
    ambiente = _ambiente()
    ambiente["documento_repo"].criar(
        Documento(
            id=None, empresa_id=2, nome_arquivo="b.pdf", nome_exibicao="b.pdf",
            caminho_arquivo="x/b.pdf", extensao=".pdf", tamanho_bytes=10,
            status=StatusDocumento.CONCLUIDO,
        )
    )

    itens = _use_case(ambiente).executar(1)

    assert itens == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_fila_revisao_use_cases.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.application.use_cases.fila_revisao_use_cases'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/application/use_cases/fila_revisao_use_cases.py`:

```python
from dataclasses import dataclass

from app.application.repositories import (
    ClassificacaoRepository, ContaRepository, DocumentoRepository, ExtracaoRepository,
)
from app.domain.entities import Documento, Extracao
from app.domain.enums import OrigemClassificacao, StatusDocumento


@dataclass
class SugestaoFilaRevisao:
    conta_id: int
    conta_codigo: str
    conta_descricao: str
    score_similaridade: float | None


@dataclass
class ItemFilaRevisao:
    documento: Documento
    extracao: Extracao | None
    sugestao: SugestaoFilaRevisao | None


class ListarFilaRevisaoUseCase:
    def __init__(
        self,
        documento_repo: DocumentoRepository,
        extracao_repo: ExtracaoRepository,
        classificacao_repo: ClassificacaoRepository,
        conta_repo: ContaRepository,
    ):
        self._documento_repo = documento_repo
        self._extracao_repo = extracao_repo
        self._classificacao_repo = classificacao_repo
        self._conta_repo = conta_repo

    def executar(self, empresa_id: int) -> list[ItemFilaRevisao]:
        itens: list[ItemFilaRevisao] = []
        for documento in self._documento_repo.listar_por_empresa(empresa_id):
            if documento.status != StatusDocumento.CONCLUIDO:
                continue
            classificacao = self._classificacao_repo.obter_por_documento_id(documento.id)
            if classificacao is not None and classificacao.origem != OrigemClassificacao.FUZZY:
                continue

            sugestao = None
            if classificacao is not None:
                conta = self._conta_repo.obter_por_id(classificacao.conta_id)
                if conta is not None:
                    sugestao = SugestaoFilaRevisao(
                        conta_id=conta.id,
                        conta_codigo=conta.codigo,
                        conta_descricao=conta.descricao,
                        score_similaridade=classificacao.score_similaridade,
                    )

            extracao = self._extracao_repo.obter_por_documento_id(documento.id)
            itens.append(ItemFilaRevisao(documento=documento, extracao=extracao, sugestao=sugestao))
        return itens
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_fila_revisao_use_cases.py -v`
Expected: 7 passed (6 test functions, one parametrized 3x = 8 total — verify all pass)

- [ ] **Step 5: Commit**

```bash
git add backend/app/application/use_cases/fila_revisao_use_cases.py backend/tests/unit/test_fila_revisao_use_cases.py
git commit -m "feat: add ListarFilaRevisaoUseCase for review queue filtering"
```

---

## Task 2: API endpoint — GET fila de revisão

**Files:**
- Modify: `backend/app/api/schemas/documento_schemas.py`
- Modify: `backend/app/api/routers/documentos_router.py`
- Test: `backend/tests/integration/test_fila_revisao_api.py`

**Interfaces:**
- Consumes: `ListarFilaRevisaoUseCase` from Task 1 (`ItemFilaRevisao.documento`, `.extracao`, `.sugestao` with `SugestaoFilaRevisao.conta_id/conta_codigo/conta_descricao/score_similaridade`); existing `DocumentoOut`, `ExtracaoOut.from_extracao()` from `backend/app/api/schemas/documento_schemas.py`.
- Produces: `GET /empresas/{empresa_id}/documentos/fila-revisao` returning `list[ItemFilaRevisaoOut]`, each with `documento`, `extracao`, `classificacao_sugerida` (JSON key, matches what the frontend in Task 5 will read).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_fila_revisao_api.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/integration/test_fila_revisao_api.py -v`
Expected: FAIL with 404 (route doesn't exist yet)

- [ ] **Step 3: Add schemas**

In `backend/app/api/schemas/documento_schemas.py`, add after `ClassificacaoOut`:

```python
class ClassificacaoSugeridaOut(BaseModel):
    conta_id: int
    conta_codigo: str
    conta_descricao: str
    score_similaridade: float | None


class ItemFilaRevisaoOut(BaseModel):
    documento: DocumentoOut
    extracao: ExtracaoOut | None
    classificacao_sugerida: ClassificacaoSugeridaOut | None
```

- [ ] **Step 4: Add the endpoint**

In `backend/app/api/routers/documentos_router.py`, add the import and the route (after `listar_documentos`):

```python
from app.api.schemas.documento_schemas import (
    ClassificacaoOut,
    ClassificacaoSugeridaOut,
    CorrigirClassificacaoIn,
    DocumentoOut,
    DocumentoResultadoOut,
    ExtracaoOut,
    ItemFilaRevisaoOut,
    OcrResultadoOut,
    UploadItemOut,
)
from app.application.use_cases.fila_revisao_use_cases import ListarFilaRevisaoUseCase
```

```python
@router.get(
    "/empresas/{empresa_id}/documentos/fila-revisao", response_model=list[ItemFilaRevisaoOut]
)
def listar_fila_revisao(empresa_id: int, db: Session = Depends(get_db)):
    documento_repo = SqlAlchemyDocumentoRepository(db)
    extracao_repo = SqlAlchemyExtracaoRepository(db)
    classificacao_repo = SqlAlchemyClassificacaoRepository(db)
    conta_repo = SqlAlchemyContaRepository(db)
    itens = ListarFilaRevisaoUseCase(
        documento_repo, extracao_repo, classificacao_repo, conta_repo
    ).executar(empresa_id)
    return [
        ItemFilaRevisaoOut(
            documento=DocumentoOut.model_validate(item.documento, from_attributes=True),
            extracao=ExtracaoOut.from_extracao(item.extracao) if item.extracao else None,
            classificacao_sugerida=(
                ClassificacaoSugeridaOut(
                    conta_id=item.sugestao.conta_id,
                    conta_codigo=item.sugestao.conta_codigo,
                    conta_descricao=item.sugestao.conta_descricao,
                    score_similaridade=item.sugestao.score_similaridade,
                )
                if item.sugestao
                else None
            ),
        )
        for item in itens
    ]
```

**Important:** this route must be registered as its own path — it does not collide with `GET /empresas/{empresa_id}/documentos` (different path length) or any other existing route. Place it anywhere among the other `documentos_router` routes.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/python -m pytest tests/integration/test_fila_revisao_api.py -v`
Expected: 3 passed

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && .venv/Scripts/python -m pytest -v`
Expected: all previously-passing tests still pass, plus the new ones (no regressions)

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/schemas/documento_schemas.py backend/app/api/routers/documentos_router.py backend/tests/integration/test_fila_revisao_api.py
git commit -m "feat: add GET /empresas/{id}/documentos/fila-revisao endpoint"
```

---

## Task 3: Domain use case — correção em lote

**Files:**
- Modify: `backend/app/application/use_cases/classificacao_use_cases.py`
- Test: `backend/tests/unit/test_classificacao_em_lote_use_case.py`

**Interfaces:**
- Consumes: existing `CorrigirClassificacaoUseCase.executar(documento_id, conta_id) -> Classificacao` (raises `DocumentoNaoEncontrado`, `ContaNaoEncontrada`, `ContaNaoPertenceAEmpresa`, `ContaNaoAnalitica` from `app.core.exceptions`).
- Produces: `ResultadoCorrecaoLoteItem` dataclass (`documento_id: int`, `sucesso: bool`, `classificacao: Classificacao | None`, `erro: str | None`) and `CorrigirClassificacaoEmLoteUseCase(corrigir_use_case).executar(documento_ids: list[int], conta_id: int) -> list[ResultadoCorrecaoLoteItem]` — Task 4's endpoint consumes this exact signature.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_classificacao_em_lote_use_case.py`:

```python
from app.application.use_cases.classificacao_use_cases import (
    CorrigirClassificacaoEmLoteUseCase, CorrigirClassificacaoUseCase,
)
from app.domain.entities import Conta, Documento, NaturezaConta, PlanoContas
from app.domain.enums import OrigemClassificacao
from tests.fakes import (
    FakeAprendizadoRepository, FakeClassificacaoRepository, FakeContaRepository,
    FakeDocumentoRepository, FakeExtracaoRepository, FakePlanoContasRepository,
    FakeRegraRepository,
)


def _ambiente():
    documento_repo = FakeDocumentoRepository()
    extracao_repo = FakeExtracaoRepository()
    classificacao_repo = FakeClassificacaoRepository()
    regra_repo = FakeRegraRepository()
    aprendizado_repo = FakeAprendizadoRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()

    plano = plano_repo.criar(PlanoContas(id=None, empresa_id=1, nome="Plano"))
    conta = conta_repo.criar(
        Conta(
            id=None, plano_conta_id=plano.id, codigo="1", descricao="Energia",
            natureza=NaturezaConta.DESPESA, conta_analitica=True,
        )
    )
    documentos = [
        documento_repo.criar(
            Documento(
                id=None, empresa_id=1, nome_arquivo=f"{i}.pdf", nome_exibicao=f"{i}.pdf",
                caminho_arquivo=f"x/{i}.pdf", extensao=".pdf", tamanho_bytes=10,
            )
        )
        for i in range(3)
    ]
    corrigir_use_case = CorrigirClassificacaoUseCase(
        documento_repo, extracao_repo, classificacao_repo, regra_repo,
        aprendizado_repo, conta_repo, plano_repo,
    )
    return {"corrigir_use_case": corrigir_use_case, "conta": conta, "documentos": documentos}


def test_lote_com_todos_sucesso():
    ambiente = _ambiente()
    ids = [d.id for d in ambiente["documentos"]]

    resultados = CorrigirClassificacaoEmLoteUseCase(ambiente["corrigir_use_case"]).executar(
        ids, ambiente["conta"].id
    )

    assert len(resultados) == 3
    assert all(r.sucesso for r in resultados)
    assert all(r.classificacao.origem == OrigemClassificacao.MANUAL for r in resultados)
    assert all(r.erro is None for r in resultados)


def test_lote_com_falha_parcial_nao_interrompe_os_outros():
    ambiente = _ambiente()
    ids = [ambiente["documentos"][0].id, 9999, ambiente["documentos"][1].id]

    resultados = CorrigirClassificacaoEmLoteUseCase(ambiente["corrigir_use_case"]).executar(
        ids, ambiente["conta"].id
    )

    assert len(resultados) == 3
    assert resultados[0].sucesso is True
    assert resultados[1].sucesso is False
    assert resultados[1].erro is not None
    assert resultados[1].classificacao is None
    assert resultados[2].sucesso is True


def test_lote_vazio_retorna_lista_vazia():
    ambiente = _ambiente()

    resultados = CorrigirClassificacaoEmLoteUseCase(ambiente["corrigir_use_case"]).executar(
        [], ambiente["conta"].id
    )

    assert resultados == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_classificacao_em_lote_use_case.py -v`
Expected: FAIL with `ImportError: cannot import name 'CorrigirClassificacaoEmLoteUseCase'`

- [ ] **Step 3: Write the implementation**

In `backend/app/application/use_cases/classificacao_use_cases.py`, add near the top-level imports:

```python
from dataclasses import dataclass

from app.core.exceptions import (
    ContaNaoAnalitica,
    ContaNaoEncontrada,
    ContaNaoPertenceAEmpresa,
    DocumentoNaoEncontrado,
)
```

(the `app.core.exceptions` import already exists in this file — just add `dataclass` and confirm all four exception names are imported; they already are per the current file contents).

Then, at the end of the file, add:

```python
@dataclass
class ResultadoCorrecaoLoteItem:
    documento_id: int
    sucesso: bool
    classificacao: Classificacao | None = None
    erro: str | None = None


class CorrigirClassificacaoEmLoteUseCase:
    def __init__(self, corrigir_use_case: CorrigirClassificacaoUseCase):
        self._corrigir_use_case = corrigir_use_case

    def executar(self, documento_ids: list[int], conta_id: int) -> list[ResultadoCorrecaoLoteItem]:
        resultados: list[ResultadoCorrecaoLoteItem] = []
        for documento_id in documento_ids:
            try:
                classificacao = self._corrigir_use_case.executar(documento_id, conta_id)
                resultados.append(
                    ResultadoCorrecaoLoteItem(
                        documento_id=documento_id, sucesso=True, classificacao=classificacao
                    )
                )
            except (
                DocumentoNaoEncontrado, ContaNaoEncontrada, ContaNaoPertenceAEmpresa,
                ContaNaoAnalitica,
            ) as exc:
                resultados.append(
                    ResultadoCorrecaoLoteItem(documento_id=documento_id, sucesso=False, erro=str(exc))
                )
        return resultados
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_classificacao_em_lote_use_case.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/application/use_cases/classificacao_use_cases.py backend/tests/unit/test_classificacao_em_lote_use_case.py
git commit -m "feat: add CorrigirClassificacaoEmLoteUseCase for batch review-queue correction"
```

---

## Task 4: API endpoint — PATCH correção em lote

**Files:**
- Modify: `backend/app/api/schemas/documento_schemas.py`
- Modify: `backend/app/api/routers/documentos_router.py`
- Test: `backend/tests/integration/test_classificacao_lote_api.py`

**Interfaces:**
- Consumes: `CorrigirClassificacaoEmLoteUseCase` from Task 3.
- Produces: `PATCH /documentos/classificacao/lote` returning `{"resultados": [...]}`, each item `{"documento_id", "sucesso", "classificacao", "erro"}` (JSON keys the frontend in Task 5 will read).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_classificacao_lote_api.py`:

```python
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db, get_storage
from app.infrastructure.db.base import Base
from app.infrastructure.db import models  # noqa: F401
from app.infrastructure.db.session import get_engine
from app.infrastructure.storage.file_storage import LocalFileStorageService
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


@pytest.fixture
def conta_id(client, empresa_id):
    plano_id = client.post(
        f"/empresas/{empresa_id}/planos-contas", json={"nome": "Plano"}
    ).json()["id"]
    return client.post(
        f"/planos-contas/{plano_id}/contas",
        json={
            "codigo": "1", "descricao": "Energia", "natureza": "DESPESA",
            "conta_analitica": True, "conta_pai_id": None,
        },
    ).json()["id"]


def test_lote_corrige_multiplos_documentos_com_sucesso(client, empresa_id, conta_id):
    ids = [
        client.post(
            f"/empresas/{empresa_id}/documentos",
            files={"arquivos": (f"{i}.pdf", b"conteudo", "application/pdf")},
        ).json()[0]["documento"]["id"]
        for i in range(2)
    ]

    resposta = client.patch(
        "/documentos/classificacao/lote", json={"documento_ids": ids, "conta_id": conta_id}
    )

    assert resposta.status_code == 200
    resultados = resposta.json()["resultados"]
    assert len(resultados) == 2
    assert all(r["sucesso"] for r in resultados)
    assert all(r["classificacao"]["conta_id"] == conta_id for r in resultados)


def test_lote_com_documento_inexistente_reporta_erro_por_item_sem_falhar_o_resto(
    client, empresa_id, conta_id
):
    documento_id = client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("a.pdf", b"conteudo", "application/pdf")},
    ).json()[0]["documento"]["id"]

    resposta = client.patch(
        "/documentos/classificacao/lote",
        json={"documento_ids": [documento_id, 9999], "conta_id": conta_id},
    )

    assert resposta.status_code == 200
    resultados = resposta.json()["resultados"]
    assert resultados[0]["sucesso"] is True
    assert resultados[1]["sucesso"] is False
    assert resultados[1]["erro"] is not None
    assert resultados[1]["classificacao"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/integration/test_classificacao_lote_api.py -v`
Expected: FAIL with 404 (route doesn't exist yet)

- [ ] **Step 3: Add schemas**

In `backend/app/api/schemas/documento_schemas.py`, add at the end of the file:

```python
class CorrigirClassificacaoLoteIn(BaseModel):
    documento_ids: list[int]
    conta_id: int


class ResultadoCorrecaoLoteItemOut(BaseModel):
    documento_id: int
    sucesso: bool
    classificacao: ClassificacaoOut | None = None
    erro: str | None = None


class CorrigirClassificacaoLoteOut(BaseModel):
    resultados: list[ResultadoCorrecaoLoteItemOut]
```

- [ ] **Step 4: Add the endpoint**

In `backend/app/api/routers/documentos_router.py`, add to the schema import block:

```python
    CorrigirClassificacaoLoteIn,
    CorrigirClassificacaoLoteOut,
    ResultadoCorrecaoLoteItemOut,
```

Add to the use-case import:

```python
from app.application.use_cases.classificacao_use_cases import (
    CorrigirClassificacaoEmLoteUseCase,
    CorrigirClassificacaoUseCase,
)
```

Add the route (place it before `corrigir_classificacao` so the batch route reads first, though route order does not actually matter here since the two paths' literal segments differ):

```python
@router.patch("/documentos/classificacao/lote", response_model=CorrigirClassificacaoLoteOut)
def corrigir_classificacao_em_lote(
    payload: CorrigirClassificacaoLoteIn, db: Session = Depends(get_db)
):
    documento_repo = SqlAlchemyDocumentoRepository(db)
    extracao_repo = SqlAlchemyExtracaoRepository(db)
    classificacao_repo = SqlAlchemyClassificacaoRepository(db)
    regra_repo = SqlAlchemyRegraRepository(db)
    aprendizado_repo = SqlAlchemyAprendizadoRepository(db)
    conta_repo = SqlAlchemyContaRepository(db)
    plano_repo = SqlAlchemyPlanoContasRepository(db)
    corrigir_use_case = CorrigirClassificacaoUseCase(
        documento_repo, extracao_repo, classificacao_repo, regra_repo,
        aprendizado_repo, conta_repo, plano_repo,
    )
    resultados = CorrigirClassificacaoEmLoteUseCase(corrigir_use_case).executar(
        payload.documento_ids, payload.conta_id
    )
    resultados_out = []
    for resultado in resultados:
        classificacao_out = None
        if resultado.classificacao is not None:
            conta = conta_repo.obter_por_id(resultado.classificacao.conta_id)
            classificacao_out = ClassificacaoOut.from_classificacao(resultado.classificacao, conta)
        resultados_out.append(
            ResultadoCorrecaoLoteItemOut(
                documento_id=resultado.documento_id, sucesso=resultado.sucesso,
                classificacao=classificacao_out, erro=resultado.erro,
            )
        )
    return CorrigirClassificacaoLoteOut(resultados=resultados_out)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/python -m pytest tests/integration/test_classificacao_lote_api.py -v`
Expected: 2 passed

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && .venv/Scripts/python -m pytest -v`
Expected: all tests pass, no regressions

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/schemas/documento_schemas.py backend/app/api/routers/documentos_router.py backend/tests/integration/test_classificacao_lote_api.py
git commit -m "feat: add PATCH /documentos/classificacao/lote endpoint"
```

---

## Task 5: Frontend types and API client methods

**Files:**
- Modify: `frontend/src/types/documento.ts`
- Modify: `frontend/src/api/client.ts`

**Interfaces:**
- Consumes: existing `Classificacao`, `Documento`, `Extracao` types from `frontend/src/types/documento.ts`.
- Produces: `ClassificacaoSugerida`, `ItemFilaRevisao`, `ResultadoCorrecaoLoteItem`, `CorrecaoLoteResultado` types; `api.documentos.filaRevisao(empresaId)` and `api.documentos.corrigirClassificacaoLote(documentoIds, contaId)` methods — Task 7's `FilaRevisao.tsx` consumes these exact names.

- [ ] **Step 1: Add types**

In `frontend/src/types/documento.ts`, add at the end of the file:

```typescript
export interface ClassificacaoSugerida {
  conta_id: number;
  conta_codigo: string;
  conta_descricao: string;
  score_similaridade: number | null;
}

export interface ItemFilaRevisao {
  documento: Documento;
  extracao: Extracao | null;
  classificacao_sugerida: ClassificacaoSugerida | null;
}

export interface ResultadoCorrecaoLoteItem {
  documento_id: number;
  sucesso: boolean;
  classificacao: Classificacao | null;
  erro: string | null;
}

export interface CorrecaoLoteResultado {
  resultados: ResultadoCorrecaoLoteItem[];
}
```

- [ ] **Step 2: Add client methods**

In `frontend/src/api/client.ts`, update the type import at the top:

```typescript
import type {
  Classificacao, CorrecaoLoteResultado, Documento, DocumentoResultado, ItemFilaRevisao, Lote,
  UploadItemResultado,
} from "../types/documento";
```

Add to the `documentos` object (after `corrigirClassificacao`):

```typescript
    filaRevisao: (empresaId: number) =>
      request<ItemFilaRevisao[]>(`/empresas/${empresaId}/documentos/fila-revisao`),
    corrigirClassificacaoLote: (documentoIds: number[], contaId: number) =>
      request<CorrecaoLoteResultado>("/documentos/classificacao/lote", {
        method: "PATCH",
        body: JSON.stringify({ documento_ids: documentoIds, conta_id: contaId }),
      }),
```

- [ ] **Step 3: Verify the frontend still typechecks**

Run: `cd frontend && npm run build`
Expected: build succeeds (this task adds unused-so-far exports and methods, which TypeScript does not flag as errors)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/documento.ts frontend/src/api/client.ts
git commit -m "feat: add fila-revisao types and API client methods"
```

---

## Task 6: Extract shared CorrecaoClassificacao component

**Files:**
- Create: `frontend/src/components/CorrecaoClassificacao.tsx`
- Modify: `frontend/src/components/DocumentoList.tsx`

**Interfaces:**
- Consumes: `Classificacao`, `OrigemClassificacao` from `frontend/src/types/documento.ts`; `Conta` from `frontend/src/types/planoContas.ts`.
- Produces: `CorrecaoClassificacao({ classificacao, contas, onCorrigir }): JSX.Element` where `onCorrigir: (contaId: number) => Promise<void>` — Task 7's `FilaRevisao.tsx` consumes this exact component and prop shape. Also exports `rotuloOrigem(origem: OrigemClassificacao): string` (moved out of `DocumentoList.tsx`) — Task 7 reuses it too.

This is a pure refactor (no behavior change) — the goal is to remove the duplication risk before Task 7 needs the same seletor+erro+filtro logic in a second place. There is no automated test for this (the project has no frontend component test framework yet, same as every prior phase); verification is `npm run build` plus the existing manual behavior in `DocumentoList.tsx` staying identical, confirmed in Task 9's end-to-end pass.

- [ ] **Step 1: Create the shared component**

Create `frontend/src/components/CorrecaoClassificacao.tsx`:

```tsx
import { useState } from "react";
import type { Classificacao, OrigemClassificacao } from "../types/documento";
import type { Conta } from "../types/planoContas";

export function rotuloOrigem(origem: OrigemClassificacao): string {
  switch (origem) {
    case "REGRA":
      return "por regra";
    case "IA":
      return "sugestão por IA";
    case "MANUAL":
      return "corrigida manualmente";
    default:
      return "sugestão por similaridade";
  }
}

export function CorrecaoClassificacao({
  classificacao,
  contas,
  onCorrigir,
}: {
  classificacao: Classificacao | null;
  contas: Conta[];
  onCorrigir: (contaId: number) => Promise<void>;
}) {
  const [contaCorrecaoId, setContaCorrecaoId] = useState<number | "">("");
  const [erro, setErro] = useState<string | null>(null);

  async function handleCorrigir() {
    if (contaCorrecaoId === "") return;
    setErro(null);
    try {
      await onCorrigir(contaCorrecaoId);
      setContaCorrecaoId("");
    } catch (err) {
      setErro((err as Error).message);
    }
  }

  return (
    <div className="rounded border border-slate-200 bg-white p-2">
      <span className="font-semibold">Classificação: </span>
      {classificacao ? (
        <span>
          {classificacao.conta_codigo} — {classificacao.conta_descricao} (
          {rotuloOrigem(classificacao.origem)}
          {classificacao.score_similaridade !== null &&
            ` — ${Math.round(classificacao.score_similaridade * 100)}%`}
          )
        </span>
      ) : (
        <span>SEM CLASSIFICAÇÃO</span>
      )}
      <div className="mt-2 flex items-center gap-2">
        <select
          className="rounded border border-slate-300 px-2 py-1 text-xs"
          value={contaCorrecaoId}
          onChange={(e) => setContaCorrecaoId(e.target.value ? Number(e.target.value) : "")}
        >
          <option value="">Corrigir para...</option>
          {contas
            .filter((conta) => conta.conta_analitica)
            .map((conta) => (
              <option key={conta.id} value={conta.id}>
                {conta.codigo} — {conta.descricao}
              </option>
            ))}
        </select>
        <button
          onClick={handleCorrigir}
          disabled={contaCorrecaoId === ""}
          className="rounded bg-slate-800 px-2 py-1 text-xs text-white disabled:opacity-50"
        >
          Corrigir
        </button>
      </div>
      {erro && <p className="mt-1 text-red-600">{erro}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Update DocumentoList.tsx to use it**

In `frontend/src/components/DocumentoList.tsx`, replace the whole file with:

```tsx
import { useState } from "react";
import { api } from "../api/client";
import { CorrecaoClassificacao } from "./CorrecaoClassificacao";
import type { Documento, DocumentoResultado } from "../types/documento";
import type { Conta } from "../types/planoContas";

function corStatus(status: Documento["status"]): string {
  switch (status) {
    case "CONCLUIDO":
      return "text-green-700";
    case "ERRO":
      return "text-red-700";
    case "PROCESSANDO":
      return "text-amber-700";
    default:
      return "text-slate-500";
  }
}

export function DocumentoList({
  documentos,
  contas,
}: {
  documentos: Documento[];
  contas: Conta[];
}) {
  const [resultadoAberto, setResultadoAberto] = useState<DocumentoResultado | null>(null);

  async function verResultado(documentoId: number) {
    const resultado = await api.documentos.resultado(documentoId);
    setResultadoAberto(resultado);
  }

  async function corrigirClassificacao(contaId: number) {
    if (resultadoAberto === null) return;
    const classificacao = await api.documentos.corrigirClassificacao(
      resultadoAberto.documento.id,
      contaId,
    );
    setResultadoAberto({ ...resultadoAberto, classificacao });
  }

  if (documentos.length === 0) {
    return <p className="text-sm text-slate-500">Nenhum documento enviado ainda.</p>;
  }

  return (
    <div className="flex flex-col gap-2">
      <ul className="flex flex-col gap-1">
        {documentos.map((documento) => (
          <li
            key={documento.id}
            className="flex items-center justify-between rounded border border-slate-200 px-3 py-1.5 text-sm"
          >
            <span>{documento.nome_exibicao}</span>
            <div className="flex items-center gap-2">
              <span className={corStatus(documento.status)}>{documento.status}</span>
              {documento.status === "CONCLUIDO" && (
                <button
                  onClick={() => verResultado(documento.id)}
                  className="rounded bg-slate-200 px-2 py-0.5 text-xs"
                >
                  Ver texto
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
      {resultadoAberto && (
        <div className="rounded border border-slate-300 bg-slate-50 p-3 text-xs">
          {resultadoAberto.extracao && (
            <div className="mb-3 grid grid-cols-2 gap-x-4 gap-y-1">
              <span className="font-semibold">Tipo:</span>
              <span>{resultadoAberto.extracao.tipo_documento}</span>
              <span className="font-semibold">Pagador:</span>
              <span>{resultadoAberto.extracao.pagador_nome}</span>
              <span className="font-semibold">CPF/CNPJ Pagador:</span>
              <span>{resultadoAberto.extracao.pagador_documento}</span>
              <span className="font-semibold">Recebedor:</span>
              <span>{resultadoAberto.extracao.recebedor_nome}</span>
              <span className="font-semibold">CPF/CNPJ Recebedor:</span>
              <span>{resultadoAberto.extracao.recebedor_documento}</span>
              <span className="font-semibold">Valor:</span>
              <span>{resultadoAberto.extracao.valor}</span>
              <span className="font-semibold">Data:</span>
              <span>{resultadoAberto.extracao.data_pagamento}</span>
              <span className="font-semibold">Banco:</span>
              <span>{resultadoAberto.extracao.banco_nome}</span>
            </div>
          )}
          <div className="mb-3">
            <CorrecaoClassificacao
              classificacao={resultadoAberto.classificacao}
              contas={contas}
              onCorrigir={corrigirClassificacao}
            />
          </div>
          <p className="mb-1 font-semibold">
            Método: {resultadoAberto.resultado?.metodo} (
            {resultadoAberto.resultado?.tempo_processamento_ms}ms)
          </p>
          <pre className="whitespace-pre-wrap">{resultadoAberto.resultado?.texto_extraido}</pre>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Verify the frontend builds**

Run: `cd frontend && npm run build`
Expected: build succeeds with no TypeScript errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/CorrecaoClassificacao.tsx frontend/src/components/DocumentoList.tsx
git commit -m "refactor: extract CorrecaoClassificacao shared component from DocumentoList"
```

---

## Task 7: FilaRevisao component (queue, batch selection, keyboard shortcuts)

**Files:**
- Create: `frontend/src/components/FilaRevisao.tsx`

**Interfaces:**
- Consumes: `api.documentos.filaRevisao`, `api.documentos.corrigirClassificacao`, `api.documentos.corrigirClassificacaoLote` from `frontend/src/api/client.ts` (Task 5); `CorrecaoClassificacao` from `frontend/src/components/CorrecaoClassificacao.tsx` (Task 6); `ItemFilaRevisao` type (Task 5).
- Produces: `FilaRevisao({ empresaId, contas }): JSX.Element` — Task 8's `EmpresasPage.tsx` consumes this exact component and prop shape (`empresaId: number`, `contas: Conta[]`).

This component has no automated test (same reasoning as Task 6 — no frontend component test framework in this project yet); it is verified manually in Task 9.

- [ ] **Step 1: Create the component**

Create `frontend/src/components/FilaRevisao.tsx`:

```tsx
import { useEffect, useState, type KeyboardEvent } from "react";
import { api } from "../api/client";
import { CorrecaoClassificacao } from "./CorrecaoClassificacao";
import type { Classificacao, ItemFilaRevisao } from "../types/documento";
import type { Conta } from "../types/planoContas";

function paraClassificacaoView(item: ItemFilaRevisao): Classificacao | null {
  if (item.classificacao_sugerida === null) return null;
  return {
    conta_id: item.classificacao_sugerida.conta_id,
    conta_codigo: item.classificacao_sugerida.conta_codigo,
    conta_descricao: item.classificacao_sugerida.conta_descricao,
    origem: "FUZZY",
    regra_id: null,
    score_similaridade: item.classificacao_sugerida.score_similaridade,
  };
}

export function FilaRevisao({
  empresaId,
  contas,
}: {
  empresaId: number;
  contas: Conta[];
}) {
  const [itens, setItens] = useState<ItemFilaRevisao[]>([]);
  const [selecionados, setSelecionados] = useState<Set<number>>(new Set());
  const [contaLoteId, setContaLoteId] = useState<number | "">("");
  const [errosLote, setErrosLote] = useState<Record<number, string>>({});
  const [focoIndex, setFocoIndex] = useState(0);

  function carregarFila() {
    api.documentos.filaRevisao(empresaId).then((novosItens) => {
      setItens(novosItens);
      setSelecionados(new Set());
      setFocoIndex(0);
    });
  }

  useEffect(() => {
    carregarFila();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [empresaId]);

  function alternarSelecao(documentoId: number) {
    setSelecionados((atual) => {
      const novo = new Set(atual);
      if (novo.has(documentoId)) novo.delete(documentoId);
      else novo.add(documentoId);
      return novo;
    });
  }

  async function confirmar(documentoId: number, contaId: number) {
    await api.documentos.corrigirClassificacao(documentoId, contaId);
    carregarFila();
  }

  async function aplicarLote() {
    if (contaLoteId === "" || selecionados.size === 0) return;
    const resultado = await api.documentos.corrigirClassificacaoLote(
      Array.from(selecionados),
      contaLoteId,
    );
    const novosErros: Record<number, string> = {};
    const idsComSucesso = new Set<number>();
    for (const item of resultado.resultados) {
      if (item.sucesso) idsComSucesso.add(item.documento_id);
      else novosErros[item.documento_id] = item.erro ?? "Erro desconhecido.";
    }
    setErrosLote(novosErros);
    setSelecionados((atual) => {
      const restantes = new Set(atual);
      idsComSucesso.forEach((id) => restantes.delete(id));
      return restantes;
    });
    setContaLoteId("");
    carregarFila();
  }

  function handleKeyDown(e: KeyboardEvent) {
    if (itens.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setFocoIndex((atual) => Math.min(atual + 1, itens.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setFocoIndex((atual) => Math.max(atual - 1, 0));
    } else if (e.key === "Enter" || e.key === "c" || e.key === "C") {
      const item = itens[focoIndex];
      if (item && item.classificacao_sugerida) {
        confirmar(item.documento.id, item.classificacao_sugerida.conta_id);
      }
    }
  }

  if (itens.length === 0) {
    return <p className="text-sm text-slate-500">Nenhum documento pendente de revisão.</p>;
  }

  const contasAnaliticas = contas.filter((conta) => conta.conta_analitica);

  return (
    <div className="flex flex-col gap-2" onKeyDown={handleKeyDown} tabIndex={0}>
      {selecionados.size > 0 && (
        <div className="flex items-center gap-2 rounded border border-slate-300 bg-slate-100 p-2 text-xs">
          <span>{selecionados.size} selecionado(s)</span>
          <select
            className="rounded border border-slate-300 px-2 py-1"
            value={contaLoteId}
            onChange={(e) => setContaLoteId(e.target.value ? Number(e.target.value) : "")}
          >
            <option value="">Aplicar conta...</option>
            {contasAnaliticas.map((conta) => (
              <option key={conta.id} value={conta.id}>
                {conta.codigo} — {conta.descricao}
              </option>
            ))}
          </select>
          <button
            onClick={aplicarLote}
            disabled={contaLoteId === ""}
            className="rounded bg-slate-800 px-2 py-1 text-white disabled:opacity-50"
          >
            Aplicar aos selecionados
          </button>
        </div>
      )}
      <ul className="flex flex-col gap-2">
        {itens.map((item, index) => (
          <li
            key={item.documento.id}
            className={`rounded border p-2 text-xs ${
              index === focoIndex ? "border-slate-500 bg-slate-50" : "border-slate-200"
            }`}
          >
            <div className="mb-1 flex items-center gap-2">
              <input
                type="checkbox"
                checked={selecionados.has(item.documento.id)}
                onChange={() => alternarSelecao(item.documento.id)}
              />
              <span className="font-semibold">{item.documento.nome_exibicao}</span>
            </div>
            {item.extracao && (
              <p className="mb-1 text-slate-600">
                {item.extracao.recebedor_nome} — {item.extracao.valor}
              </p>
            )}
            <div className="flex items-start gap-2">
              <div className="flex-1">
                <CorrecaoClassificacao
                  classificacao={paraClassificacaoView(item)}
                  contas={contas}
                  onCorrigir={(contaId) => confirmar(item.documento.id, contaId)}
                />
              </div>
              {item.classificacao_sugerida && (
                <button
                  onClick={() => confirmar(item.documento.id, item.classificacao_sugerida!.conta_id)}
                  className="rounded bg-green-700 px-2 py-1 text-white"
                >
                  Confirmar
                </button>
              )}
            </div>
            {errosLote[item.documento.id] && (
              <p className="mt-1 text-red-600">{errosLote[item.documento.id]}</p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 2: Verify the frontend builds**

Run: `cd frontend && npm run build`
Expected: build succeeds with no TypeScript errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/FilaRevisao.tsx
git commit -m "feat: add FilaRevisao component with batch correction and keyboard navigation"
```

---

## Task 8: Wire "Fila de Revisão" tab into EmpresasPage

**Files:**
- Modify: `frontend/src/pages/EmpresasPage.tsx`

**Interfaces:**
- Consumes: `FilaRevisao` from Task 7 (`empresaId: number`, `contas: Conta[]`); existing `todasContasEmpresa` state already computed in this file.
- Produces: no new exports — this is the final wiring point.

- [ ] **Step 1: Add the import and tab state**

In `frontend/src/pages/EmpresasPage.tsx`, add the import:

```typescript
import { FilaRevisao } from "../components/FilaRevisao";
```

Add a new state near the other `useState` calls (after `lote`):

```typescript
  const [abaDocumentos, setAbaDocumentos] = useState<"lista" | "fila-revisao">("lista");
```

- [ ] **Step 2: Replace the "Comprovantes" section body**

Replace this block:

```tsx
          {lote && <ProgressoLote lote={lote} onCancelar={handleCancelarLote} />}
          <DocumentoList documentos={documentos} contas={todasContasEmpresa} />
```

with:

```tsx
          {lote && <ProgressoLote lote={lote} onCancelar={handleCancelarLote} />}
          <div className="flex gap-2 border-b border-slate-200">
            <button
              onClick={() => setAbaDocumentos("lista")}
              className={`px-3 py-1.5 text-sm ${
                abaDocumentos === "lista"
                  ? "border-b-2 border-slate-800 font-semibold text-slate-800"
                  : "text-slate-500"
              }`}
            >
              Todos os Documentos
            </button>
            <button
              onClick={() => setAbaDocumentos("fila-revisao")}
              className={`px-3 py-1.5 text-sm ${
                abaDocumentos === "fila-revisao"
                  ? "border-b-2 border-slate-800 font-semibold text-slate-800"
                  : "text-slate-500"
              }`}
            >
              Fila de Revisão
            </button>
          </div>
          {abaDocumentos === "lista" ? (
            <DocumentoList documentos={documentos} contas={todasContasEmpresa} />
          ) : (
            <FilaRevisao empresaId={empresaSelecionadaId} contas={todasContasEmpresa} />
          )}
```

- [ ] **Step 3: Verify the frontend builds**

Run: `cd frontend && npm run build`
Expected: build succeeds with no TypeScript errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/EmpresasPage.tsx
git commit -m "feat: wire Fila de Revisão tab into EmpresasPage"
```

---

## Task 9: Manual end-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend suite one more time**

Run: `cd backend && .venv/Scripts/python -m pytest -v`
Expected: all tests pass, no regressions from any of Tasks 1-4

- [ ] **Step 2: Run the frontend build one more time**

Run: `cd frontend && npm run build`
Expected: build succeeds

- [ ] **Step 3: Start the backend and frontend, walk through the UI**

Start backend: `cd backend && .venv/Scripts/python -m uvicorn app.main:app --reload`
Start frontend: `cd frontend && npm run dev`

Using the browser (or the Claude Browser tool), verify:

1. Create an empresa, plano de contas, and at least 2 analytic contas.
2. Upload 3 documentos with different synthetic content: one that will match a `Regra` you create first (should end up `REGRA`, never appears in the fila), one that will end up with no classification at all (garbage content, ends up `CONCLUIDO` with `classificacao=null`), and reuse the existing Fase 3/4 manual-verification technique (an existing classified document, then manually re-run FUZZY by uploading a similar-but-not-identical document to a previously MANUAL-classified supplier) to get one `FUZZY` result.
3. Open the "Fila de Revisão" tab — confirm it shows exactly the "sem classificação" document and the "FUZZY" document, and NOT the "REGRA" one.
4. Click "Confirmar" on the FUZZY item — confirm it disappears from the fila (refetch), and `GET /documentos/{id}/resultado` shows `origem=MANUAL`.
5. Select the "sem classificação" item's checkbox, pick a conta in the batch bar, click "Aplicar aos selecionados" — confirm it disappears from the fila too.
6. Upload 2 more unclassified documentos, open the fila, use `↓`/`↑` to move focus between rows (visually highlighted), confirm `Enter` on a row with a FUZZY suggestion applies it (only if that row has one) — rows without a suggestion should be unaffected by `Enter`/`C`.
7. Confirm the "Todos os Documentos" tab still works exactly as before (no regression in the original list/correction flow from Fase 4).

- [ ] **Step 4: Report results**

Document what was verified (pass/fail per item above) before proceeding to the final whole-branch review.
