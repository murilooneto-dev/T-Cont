# Fase 6 — Exportação de Planilha — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user download, with one click, an `.xlsx` spreadsheet of all processed (`CONCLUIDO`) documents of the selected empresa, with extracted data and current accounting classification, ready to import into another system.

**Architecture:** A read-only use case (`ExportarDocumentosUseCase`) builds typed rows from existing repositories and knows nothing about Excel; an infrastructure generator (`gerar_planilha_documentos`) turns those rows into `.xlsx` bytes with `openpyxl` and knows nothing about repositories. A new `GET /empresas/{id}/documentos/exportar` endpoint wires them and returns the bytes as an attachment. The frontend adds an `ExportarPlanilha` button next to "Processar" that downloads the blob and warns when the Fase 5 review queue is not empty.

**Tech Stack:** FastAPI + `openpyxl==3.1.5` (already in `backend/requirements.txt`), React + TypeScript + Tailwind. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-21-fase6-exportacao-planilha-design.md`

## Global Constraints

- Format is `.xlsx` only. No CSV, no PDF. No new dependency (`openpyxl==3.1.5` is already installed).
- No schema change: no migration, no table, no column, no new repository method. The use case filters in memory over `DocumentoRepository.listar_por_empresa` (same precedent as `ListarFilaRevisaoUseCase`, Fase 5).
- Only documents with `status == StatusDocumento.CONCLUIDO` are exported. `PENDENTE`, `PROCESSANDO` and `ERRO` never appear.
- The sheet is named `Documentos` and has exactly these 12 columns, in this exact order: `Arquivo`, `Data do pagamento`, `Valor`, `Tipo`, `Pagador (nome)`, `Pagador (CPF/CNPJ)`, `Recebedor (nome)`, `Recebedor (CPF/CNPJ)`, `Banco`, `Conta (código)`, `Conta (descrição)`, `Origem`. The first row is the header; then one row per document, in the order returned by `listar_por_empresa`.
- A field the extraction did not identify (`None`, or an empty/whitespace-only string) is an EMPTY cell — never the text `NÃO IDENTIFICADO` (that is only a display label of the API/UI).
- A document without classification has empty `Conta (código)`, `Conta (descrição)` and `Origem`. A classification whose conta no longer exists has empty conta columns but keeps `Origem`. A document without extraction has only `Arquivo` filled.
- `Data do pagamento` and `Valor` are native Excel types (date and number). CPF/CNPJ are text (leading zeros preserved).
- Every text cell is stored as a plain string, never as a formula: a value starting with `=`, `+`, `-`, `@` or `#` must stay text. `openpyxl` auto-detects `=…` as a formula and `#N/A`-like values as errors, so every text cell must be forced to `data_type = "s"` (verified empirically against `openpyxl` 3.1.5).
- Endpoint: `GET /empresas/{empresa_id}/documentos/exportar`; `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`; `Content-Disposition: attachment; filename="comprovantes_<cnpj>_<AAAA-MM-DD>.xlsx"` (CNPJ in digits only + export date). Unknown empresa → 404 via `EmpresaNaoEncontrada`. Empresa with no `CONCLUIDO` document → 200 with a valid header-only `.xlsx`. Nothing is written to disk.
- Frontend: button "Exportar planilha" beside "Processar", visible whenever an empresa is selected, in any tab; disabled while exporting; the pending-review warning reuses the existing `api.documentos.filaRevisao` (no new backend code for it); every failure is shown on screen (no silent failure — Fase 5 lesson).
- Tests: backend unit tests use the `Fake*Repository` classes from `backend/tests/fakes.py`; integration tests use `get_engine()` from `app.infrastructure.db.session` (never a raw `create_engine()`, to keep `PRAGMA foreign_keys=ON`). Frontend has no component test framework: verification is `npm run build` plus the manual pass in Task 6.
- Style: Portuguese domain names, dataclasses, no docstrings unless truly non-obvious.

**Plan refinements of the spec (decided while writing this plan; each preserves the spec's intent):**
1. `ExportarDocumentosUseCase` also receives `EmpresaRepository` and returns `ExportacaoDocumentos(cnpj_empresa, linhas)` instead of a bare list, because the 404 and the download filename both need the empresa. It still does not know Excel.
2. `CORSMiddleware` in `backend/app/main.py` must add `expose_headers=["Content-Disposition"]`. The frontend runs on another origin (`localhost:5173` → `localhost:8000`), and browsers hide every non-safelisted response header from cross-origin `fetch` unless it is exposed; without this the frontend could never read the filename. (Task 3 adds it and tests it.)
3. The frontend component is mounted with `key={empresaSelecionadaId}` so switching empresa remounts it and discards any stale warning/error/in-flight state, with no extra logic.

---

## Task 1: Use case — `ExportarDocumentosUseCase`

**Files:**
- Create: `backend/app/application/use_cases/exportacao_use_cases.py`
- Test: `backend/tests/unit/test_exportacao_use_cases.py`

**Interfaces:**
- Consumes: `EmpresaRepository.obter_por_id(empresa_id) -> Empresa | None`, `DocumentoRepository.listar_por_empresa(empresa_id) -> list[Documento]`, `ExtracaoRepository.obter_por_documento_id(documento_id) -> Extracao | None`, `ClassificacaoRepository.obter_por_documento_id(documento_id) -> Classificacao | None`, `ContaRepository.obter_por_id(conta_id) -> Conta | None` (all in `backend/app/application/repositories.py`, all implemented by the `Fake*Repository` classes in `backend/tests/fakes.py`); `EmpresaNaoEncontrada` from `app.core.exceptions`.
- Produces (Task 2 and Task 3 rely on these exact names): dataclass `LinhaExportacao` with fields `arquivo: str`, `data_pagamento: date | None`, `valor: Decimal | None`, `tipo: str | None`, `pagador_nome: str | None`, `pagador_documento: str | None`, `recebedor_nome: str | None`, `recebedor_documento: str | None`, `banco_nome: str | None`, `conta_codigo: str | None`, `conta_descricao: str | None`, `origem: str | None`; dataclass `ExportacaoDocumentos` with `cnpj_empresa: str` and `linhas: list[LinhaExportacao]`; class `ExportarDocumentosUseCase(empresa_repo, documento_repo, extracao_repo, classificacao_repo, conta_repo)` with `executar(empresa_id: int) -> ExportacaoDocumentos`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_exportacao_use_cases.py`:

```python
from datetime import date
from decimal import Decimal

import pytest

from app.application.use_cases.exportacao_use_cases import (
    ExportacaoDocumentos,
    ExportarDocumentosUseCase,
    LinhaExportacao,
)
from app.core.exceptions import EmpresaNaoEncontrada
from app.domain.entities import (
    Classificacao, Conta, Documento, Empresa, Extracao, PlanoContas,
)
from app.domain.enums import (
    NaturezaConta, OrigemClassificacao, StatusDocumento, TipoDocumento,
)
from tests.fakes import (
    FakeClassificacaoRepository,
    FakeContaRepository,
    FakeDocumentoRepository,
    FakeEmpresaRepository,
    FakeExtracaoRepository,
    FakePlanoContasRepository,
)


def _ambiente():
    empresa_repo = FakeEmpresaRepository()
    documento_repo = FakeDocumentoRepository()
    extracao_repo = FakeExtracaoRepository()
    classificacao_repo = FakeClassificacaoRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()

    empresa = empresa_repo.criar(
        Empresa(id=None, razao_social="Tesserato", nome_fantasia=None, cnpj="12345678000199")
    )
    plano = plano_repo.criar(PlanoContas(id=None, empresa_id=empresa.id, nome="Plano"))
    conta = conta_repo.criar(
        Conta(
            id=None, plano_conta_id=plano.id, codigo="1", descricao="Energia",
            natureza=NaturezaConta.DESPESA, conta_analitica=True,
        )
    )
    return {
        "empresa_repo": empresa_repo, "documento_repo": documento_repo,
        "extracao_repo": extracao_repo, "classificacao_repo": classificacao_repo,
        "conta_repo": conta_repo, "empresa": empresa, "conta": conta,
    }


def _documento(ambiente, nome="a.pdf", status=StatusDocumento.CONCLUIDO, empresa_id=None):
    return ambiente["documento_repo"].criar(
        Documento(
            id=None,
            empresa_id=empresa_id if empresa_id is not None else ambiente["empresa"].id,
            nome_arquivo=nome, nome_exibicao=nome, caminho_arquivo=f"x/{nome}",
            extensao=".pdf", tamanho_bytes=10, status=status,
        )
    )


def _use_case(ambiente):
    return ExportarDocumentosUseCase(
        ambiente["empresa_repo"], ambiente["documento_repo"], ambiente["extracao_repo"],
        ambiente["classificacao_repo"], ambiente["conta_repo"],
    )


def test_empresa_inexistente_levanta_erro():
    ambiente = _ambiente()

    with pytest.raises(EmpresaNaoEncontrada):
        _use_case(ambiente).executar(999)


def test_empresa_sem_documentos_devolve_cnpj_e_nenhuma_linha():
    ambiente = _ambiente()

    resultado = _use_case(ambiente).executar(ambiente["empresa"].id)

    assert isinstance(resultado, ExportacaoDocumentos)
    assert resultado.cnpj_empresa == "12345678000199"
    assert resultado.linhas == []


@pytest.mark.parametrize(
    "status",
    [StatusDocumento.PENDENTE, StatusDocumento.PROCESSANDO, StatusDocumento.ERRO],
)
def test_documento_nao_concluido_nao_entra(status):
    ambiente = _ambiente()
    _documento(ambiente, status=status)

    resultado = _use_case(ambiente).executar(ambiente["empresa"].id)

    assert resultado.linhas == []


def test_linha_completa_traz_extracao_e_classificacao():
    ambiente = _ambiente()
    documento = _documento(ambiente, nome="comprovante.pdf")
    ambiente["extracao_repo"].criar(
        Extracao(
            id=None, documento_id=documento.id, pagador_nome="Tesserato",
            pagador_documento="12345678000199", recebedor_nome="Energisa",
            recebedor_documento="11222333000199", valor=Decimal("150.00"),
            data_pagamento=date(2026, 9, 18), tipo_documento=TipoDocumento.PIX,
            banco_nome="Itau",
        )
    )
    ambiente["classificacao_repo"].criar(
        Classificacao(
            id=None, empresa_id=ambiente["empresa"].id, documento_id=documento.id,
            conta_id=ambiente["conta"].id, origem=OrigemClassificacao.REGRA,
        )
    )

    linhas = _use_case(ambiente).executar(ambiente["empresa"].id).linhas

    assert linhas == [
        LinhaExportacao(
            arquivo="comprovante.pdf", data_pagamento=date(2026, 9, 18),
            valor=Decimal("150.00"), tipo="PIX", pagador_nome="Tesserato",
            pagador_documento="12345678000199", recebedor_nome="Energisa",
            recebedor_documento="11222333000199", banco_nome="Itau",
            conta_codigo="1", conta_descricao="Energia", origem="REGRA",
        )
    ]


def test_campos_none_ou_em_branco_viram_none():
    ambiente = _ambiente()
    documento = _documento(ambiente)
    ambiente["extracao_repo"].criar(
        Extracao(
            id=None, documento_id=documento.id, pagador_nome=None,
            pagador_documento="", recebedor_nome="   ", recebedor_documento=None,
            valor=None, data_pagamento=None, tipo_documento=TipoDocumento.OUTRO,
            banco_nome=None,
        )
    )

    linha = _use_case(ambiente).executar(ambiente["empresa"].id).linhas[0]

    assert linha.pagador_nome is None
    assert linha.pagador_documento is None
    assert linha.recebedor_nome is None
    assert linha.recebedor_documento is None
    assert linha.banco_nome is None
    assert linha.valor is None
    assert linha.data_pagamento is None
    assert linha.tipo == "OUTRO"


def test_documento_sem_extracao_nem_classificacao_so_traz_o_arquivo():
    ambiente = _ambiente()
    _documento(ambiente, nome="solto.pdf")

    linha = _use_case(ambiente).executar(ambiente["empresa"].id).linhas[0]

    assert linha == LinhaExportacao(
        arquivo="solto.pdf", data_pagamento=None, valor=None, tipo=None,
        pagador_nome=None, pagador_documento=None, recebedor_nome=None,
        recebedor_documento=None, banco_nome=None, conta_codigo=None,
        conta_descricao=None, origem=None,
    )


def test_conta_deletada_deixa_colunas_de_conta_vazias_mas_mantem_a_origem():
    ambiente = _ambiente()
    documento = _documento(ambiente)
    ambiente["classificacao_repo"].criar(
        Classificacao(
            id=None, empresa_id=ambiente["empresa"].id, documento_id=documento.id,
            conta_id=9999, origem=OrigemClassificacao.MANUAL,
        )
    )

    linha = _use_case(ambiente).executar(ambiente["empresa"].id).linhas[0]

    assert linha.conta_codigo is None
    assert linha.conta_descricao is None
    assert linha.origem == "MANUAL"


def test_nao_inclui_documentos_de_outra_empresa():
    ambiente = _ambiente()
    _documento(ambiente, nome="outra.pdf", empresa_id=999)

    resultado = _use_case(ambiente).executar(ambiente["empresa"].id)

    assert resultado.linhas == []


def test_preserva_a_ordem_de_listagem_dos_documentos():
    ambiente = _ambiente()
    _documento(ambiente, nome="primeiro.pdf")
    _documento(ambiente, nome="segundo.pdf")

    linhas = _use_case(ambiente).executar(ambiente["empresa"].id).linhas

    assert [linha.arquivo for linha in linhas] == ["primeiro.pdf", "segundo.pdf"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_exportacao_use_cases.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.application.use_cases.exportacao_use_cases'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/application/use_cases/exportacao_use_cases.py`:

```python
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.application.repositories import (
    ClassificacaoRepository,
    ContaRepository,
    DocumentoRepository,
    EmpresaRepository,
    ExtracaoRepository,
)
from app.core.exceptions import EmpresaNaoEncontrada
from app.domain.enums import StatusDocumento


@dataclass
class LinhaExportacao:
    arquivo: str
    data_pagamento: date | None
    valor: Decimal | None
    tipo: str | None
    pagador_nome: str | None
    pagador_documento: str | None
    recebedor_nome: str | None
    recebedor_documento: str | None
    banco_nome: str | None
    conta_codigo: str | None
    conta_descricao: str | None
    origem: str | None


@dataclass
class ExportacaoDocumentos:
    cnpj_empresa: str
    linhas: list[LinhaExportacao]


def _texto(valor: str | None) -> str | None:
    return (valor or "").strip() or None


class ExportarDocumentosUseCase:
    def __init__(
        self,
        empresa_repo: EmpresaRepository,
        documento_repo: DocumentoRepository,
        extracao_repo: ExtracaoRepository,
        classificacao_repo: ClassificacaoRepository,
        conta_repo: ContaRepository,
    ):
        self._empresa_repo = empresa_repo
        self._documento_repo = documento_repo
        self._extracao_repo = extracao_repo
        self._classificacao_repo = classificacao_repo
        self._conta_repo = conta_repo

    def executar(self, empresa_id: int) -> ExportacaoDocumentos:
        empresa = self._empresa_repo.obter_por_id(empresa_id)
        if empresa is None:
            raise EmpresaNaoEncontrada(empresa_id)

        linhas: list[LinhaExportacao] = []
        for documento in self._documento_repo.listar_por_empresa(empresa_id):
            if documento.status != StatusDocumento.CONCLUIDO:
                continue
            extracao = self._extracao_repo.obter_por_documento_id(documento.id)
            classificacao = self._classificacao_repo.obter_por_documento_id(documento.id)
            conta = (
                self._conta_repo.obter_por_id(classificacao.conta_id)
                if classificacao is not None
                else None
            )
            linhas.append(
                LinhaExportacao(
                    arquivo=documento.nome_exibicao,
                    data_pagamento=extracao.data_pagamento if extracao else None,
                    valor=extracao.valor if extracao else None,
                    tipo=extracao.tipo_documento.value if extracao else None,
                    pagador_nome=_texto(extracao.pagador_nome) if extracao else None,
                    pagador_documento=_texto(extracao.pagador_documento) if extracao else None,
                    recebedor_nome=_texto(extracao.recebedor_nome) if extracao else None,
                    recebedor_documento=(
                        _texto(extracao.recebedor_documento) if extracao else None
                    ),
                    banco_nome=_texto(extracao.banco_nome) if extracao else None,
                    conta_codigo=conta.codigo if conta else None,
                    conta_descricao=conta.descricao if conta else None,
                    origem=classificacao.origem.value if classificacao else None,
                )
            )
        return ExportacaoDocumentos(cnpj_empresa=empresa.cnpj, linhas=linhas)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_exportacao_use_cases.py -v`
Expected: 11 passed (9 test functions, one parametrized 3x)

- [ ] **Step 5: Commit**

```bash
git add backend/app/application/use_cases/exportacao_use_cases.py backend/tests/unit/test_exportacao_use_cases.py
git commit -m "feat: add ExportarDocumentosUseCase for spreadsheet export rows"
```

---

## Task 2: Generator — `.xlsx` from rows

**Files:**
- Create: `backend/app/infrastructure/spreadsheet/documentos_exporter.py`
- Test: `backend/tests/unit/test_documentos_exporter.py`

**Interfaces:**
- Consumes: `LinhaExportacao` from Task 1 (`backend/app/application/use_cases/exportacao_use_cases.py`), with exactly the 12 field names listed in Task 1.
- Produces (Task 3 relies on these exact names): `XLSX_MEDIA_TYPE: str` (`"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"`) and `gerar_planilha_documentos(linhas: list[LinhaExportacao]) -> bytes`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_documentos_exporter.py`:

```python
import io
from datetime import date, datetime
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from app.application.use_cases.exportacao_use_cases import LinhaExportacao
from app.infrastructure.spreadsheet.documentos_exporter import (
    XLSX_MEDIA_TYPE,
    gerar_planilha_documentos,
)

CABECALHO = [
    "Arquivo", "Data do pagamento", "Valor", "Tipo", "Pagador (nome)",
    "Pagador (CPF/CNPJ)", "Recebedor (nome)", "Recebedor (CPF/CNPJ)", "Banco",
    "Conta (código)", "Conta (descrição)", "Origem",
]


def _linha(**sobrescritas) -> LinhaExportacao:
    campos = dict(
        arquivo="comprovante.pdf", data_pagamento=date(2026, 9, 18),
        valor=Decimal("150.00"), tipo="PIX", pagador_nome="Tesserato",
        pagador_documento="01234567000199", recebedor_nome="Energisa",
        recebedor_documento="11222333000199", banco_nome="Itau",
        conta_codigo="1", conta_descricao="Energia", origem="REGRA",
    )
    campos.update(sobrescritas)
    return LinhaExportacao(**campos)


def _abrir(conteudo: bytes):
    return load_workbook(io.BytesIO(conteudo))


def test_media_type_e_o_do_excel():
    assert XLSX_MEDIA_TYPE == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def test_sem_linhas_gera_apenas_o_cabecalho():
    aba = _abrir(gerar_planilha_documentos([]))["Documentos"]

    assert [celula.value for celula in aba[1]] == CABECALHO
    assert aba.max_row == 1


def test_aba_unica_chamada_documentos():
    workbook = _abrir(gerar_planilha_documentos([_linha()]))

    assert workbook.sheetnames == ["Documentos"]


def test_linha_de_dados_na_ordem_das_colunas():
    aba = _abrir(gerar_planilha_documentos([_linha()]))["Documentos"]

    valores = [celula.value for celula in aba[2]]

    assert valores == [
        "comprovante.pdf", datetime(2026, 9, 18), 150, "PIX", "Tesserato",
        "01234567000199", "Energisa", "11222333000199", "Itau", "1", "Energia", "REGRA",
    ]


def test_data_e_valor_sao_tipos_nativos_e_documentos_sao_texto():
    aba = _abrir(gerar_planilha_documentos([_linha()]))["Documentos"]

    assert aba["B2"].data_type == "d"
    assert aba["C2"].data_type == "n"
    assert aba["F2"].data_type == "s"
    assert aba["F2"].value == "01234567000199"


def test_campos_none_viram_celula_vazia():
    linha = _linha(
        data_pagamento=None, valor=None, tipo=None, pagador_nome=None,
        pagador_documento=None, recebedor_nome=None, recebedor_documento=None,
        banco_nome=None, conta_codigo=None, conta_descricao=None, origem=None,
    )
    aba = _abrir(gerar_planilha_documentos([linha]))["Documentos"]

    valores = [celula.value for celula in aba[2]]

    assert valores == ["comprovante.pdf"] + [None] * 11


@pytest.mark.parametrize("texto", ["=1+1", "+cmd", "-2+3", "@SUM(A1)", "#N/A"])
def test_texto_livre_nunca_vira_formula_ou_erro(texto):
    aba = _abrir(gerar_planilha_documentos([_linha(recebedor_nome=texto)]))["Documentos"]

    assert aba["G2"].value == texto
    assert aba["G2"].data_type == "s"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_documentos_exporter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.infrastructure.spreadsheet.documentos_exporter'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/infrastructure/spreadsheet/documentos_exporter.py`:

```python
import io

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from app.application.use_cases.exportacao_use_cases import LinhaExportacao

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_NOME_ABA = "Documentos"
_COLUNAS = [
    ("Arquivo", 30),
    ("Data do pagamento", 18),
    ("Valor", 14),
    ("Tipo", 10),
    ("Pagador (nome)", 28),
    ("Pagador (CPF/CNPJ)", 20),
    ("Recebedor (nome)", 28),
    ("Recebedor (CPF/CNPJ)", 20),
    ("Banco", 22),
    ("Conta (código)", 14),
    ("Conta (descrição)", 30),
    ("Origem", 10),
]
_COLUNA_DATA = 2
_COLUNA_VALOR = 3


def gerar_planilha_documentos(linhas: list[LinhaExportacao]) -> bytes:
    workbook = Workbook()
    aba = workbook.active
    aba.title = _NOME_ABA

    for indice, (titulo, largura) in enumerate(_COLUNAS, start=1):
        celula = aba.cell(row=1, column=indice, value=titulo)
        celula.font = Font(bold=True)
        aba.column_dimensions[get_column_letter(indice)].width = largura

    for numero_linha, linha in enumerate(linhas, start=2):
        valores = [
            linha.arquivo, linha.data_pagamento, linha.valor, linha.tipo,
            linha.pagador_nome, linha.pagador_documento, linha.recebedor_nome,
            linha.recebedor_documento, linha.banco_nome, linha.conta_codigo,
            linha.conta_descricao, linha.origem,
        ]
        for numero_coluna, valor in enumerate(valores, start=1):
            celula = aba.cell(row=numero_linha, column=numero_coluna, value=valor)
            if isinstance(valor, str):
                celula.data_type = "s"
        aba.cell(row=numero_linha, column=_COLUNA_DATA).number_format = "DD/MM/YYYY"
        aba.cell(row=numero_linha, column=_COLUNA_VALOR).number_format = "#,##0.00"

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_documentos_exporter.py -v`
Expected: 11 passed (7 test functions, one parametrized 5x)

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/spreadsheet/documentos_exporter.py backend/tests/unit/test_documentos_exporter.py
git commit -m "feat: add xlsx generator for exported documents"
```

---

## Task 3: API endpoint + CORS header exposure

**Files:**
- Modify: `backend/app/api/routers/documentos_router.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/integration/test_exportacao_api.py`

**Interfaces:**
- Consumes: `ExportarDocumentosUseCase(empresa_repo, documento_repo, extracao_repo, classificacao_repo, conta_repo).executar(empresa_id) -> ExportacaoDocumentos` (Task 1); `gerar_planilha_documentos(linhas) -> bytes` and `XLSX_MEDIA_TYPE` (Task 2); existing `SqlAlchemyEmpresaRepository`, `SqlAlchemyDocumentoRepository`, `SqlAlchemyExtracaoRepository`, `SqlAlchemyClassificacaoRepository`, `SqlAlchemyContaRepository` (already imported in `documentos_router.py`), `EmpresaNaoEncontrada` (already imported there).
- Produces: `GET /empresas/{empresa_id}/documentos/exportar` (binary `.xlsx` attachment) — Task 4's frontend client consumes this path and the `Content-Disposition` header. The route does not collide with any existing one: `GET /empresas/{empresa_id}/documentos/fila-revisao` differs in its literal last segment, `GET /empresas/{empresa_id}/documentos` has fewer segments, and the only other `/documentos/processar` sibling is a `POST`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/integration/test_exportacao_api.py`:

```python
import functools
import io
import re
import time

import fitz
import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db, get_storage
from app.infrastructure.db.base import Base
from app.infrastructure.db import models  # noqa: F401
from app.infrastructure.db.session import get_engine
from app.infrastructure.storage.file_storage import LocalFileStorageService
from app.infrastructure.workers.lote_worker import processar_lote_em_background
from app.main import app

CABECALHO = [
    "Arquivo", "Data do pagamento", "Valor", "Tipo", "Pagador (nome)",
    "Pagador (CPF/CNPJ)", "Recebedor (nome)", "Recebedor (CPF/CNPJ)", "Banco",
    "Conta (código)", "Conta (descrição)", "Origem",
]


@pytest.fixture
def client(tmp_path, monkeypatch):
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


@pytest.fixture
def empresa_id(client):
    response = client.post(
        "/empresas",
        json={"razao_social": "Tesserato", "nome_fantasia": None, "cnpj": "12345678000199"},
    )
    return response.json()["id"]


def _pdf(texto: str) -> bytes:
    documento = fitz.open()
    pagina = documento.new_page()
    pagina.insert_text((72, 72), texto)
    conteudo = documento.tobytes()
    documento.close()
    return conteudo


def _processar_e_aguardar(client, empresa_id):
    lote_id = client.post(f"/empresas/{empresa_id}/documentos/processar").json()["id"]
    status_final = None
    for _ in range(20):
        status_final = client.get(f"/lotes/{lote_id}").json()
        if status_final["status"] != "EM_ANDAMENTO":
            break
        time.sleep(0.5)
    assert status_final["status"] == "CONCLUIDO"


def _abrir(response):
    return load_workbook(io.BytesIO(response.content))


def test_empresa_inexistente_retorna_404(client):
    response = client.get("/empresas/999/documentos/exportar")

    assert response.status_code == 404


def test_empresa_sem_documentos_retorna_xlsx_so_com_cabecalho(client, empresa_id):
    response = client.get(f"/empresas/{empresa_id}/documentos/exportar")

    assert response.status_code == 200
    assert response.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert re.fullmatch(
        r'attachment; filename="comprovantes_12345678000199_\d{4}-\d{2}-\d{2}\.xlsx"',
        response.headers["content-disposition"],
    )
    aba = _abrir(response)["Documentos"]
    assert [celula.value for celula in aba[1]] == CABECALHO
    assert aba.max_row == 1


def test_documento_pendente_nao_aparece_na_planilha(client, empresa_id):
    client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("a.pdf", b"conteudo", "application/pdf")},
    )

    response = client.get(f"/empresas/{empresa_id}/documentos/exportar")

    assert _abrir(response)["Documentos"].max_row == 1


def test_documento_processado_e_classificado_aparece_com_todos_os_dados(client, empresa_id):
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
            "documento_fiscal": "11222333000199", "tipo_documento": None,
            "valor_min": None, "valor_max": None, "palavra_chave_nome": None,
        },
    )
    client.post(
        f"/empresas/{empresa_id}/documentos",
        files={
            "arquivos": (
                "comprovante.pdf",
                _pdf("Favorecido: Energisa Distribuidora\nCNPJ: 11.222.333/0001-99\nValor: R$ 150,00"),
                "application/pdf",
            )
        },
    )
    _processar_e_aguardar(client, empresa_id)

    response = client.get(f"/empresas/{empresa_id}/documentos/exportar")

    aba = _abrir(response)["Documentos"]
    assert aba.max_row == 2
    linha = {titulo: celula.value for titulo, celula in zip(CABECALHO, aba[2])}
    assert linha["Arquivo"] == "comprovante.pdf"
    assert linha["Valor"] == 150
    assert linha["Recebedor (CPF/CNPJ)"] == "11222333000199"
    assert linha["Conta (código)"] == "1"
    assert linha["Conta (descrição)"] == "Energia"
    assert linha["Origem"] == "REGRA"


def test_cors_expoe_content_disposition_para_o_frontend(client, empresa_id):
    response = client.get(
        f"/empresas/{empresa_id}/documentos/exportar",
        headers={"Origin": "http://localhost:5173"},
    )

    assert "content-disposition" in response.headers["access-control-expose-headers"].lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/integration/test_exportacao_api.py -v`
Expected: FAIL — the route does not exist yet (the 404-for-unknown-empresa test may pass by accident; the others fail with 404/KeyError)

- [ ] **Step 3: Expose the header in CORS**

In `backend/app/main.py`, replace the middleware block:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

with:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)
```

- [ ] **Step 4: Add the endpoint**

In `backend/app/api/routers/documentos_router.py`:

1. Replace the first line `from fastapi import APIRouter, Depends, HTTPException, UploadFile` with:

```python
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
```

2. Add these two imports next to the other `app.application.use_cases...` and `app.infrastructure...` imports:

```python
from app.application.use_cases.exportacao_use_cases import ExportarDocumentosUseCase
from app.infrastructure.spreadsheet.documentos_exporter import (
    XLSX_MEDIA_TYPE,
    gerar_planilha_documentos,
)
```

3. Add this route right after the existing `listar_fila_revisao` route:

```python
@router.get("/empresas/{empresa_id}/documentos/exportar")
def exportar_documentos(empresa_id: int, db: Session = Depends(get_db)):
    try:
        exportacao = ExportarDocumentosUseCase(
            SqlAlchemyEmpresaRepository(db),
            SqlAlchemyDocumentoRepository(db),
            SqlAlchemyExtracaoRepository(db),
            SqlAlchemyClassificacaoRepository(db),
            SqlAlchemyContaRepository(db),
        ).executar(empresa_id)
    except EmpresaNaoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    cnpj = "".join(caractere for caractere in exportacao.cnpj_empresa if caractere.isdigit())
    nome_arquivo = f"comprovantes_{cnpj}_{date.today().isoformat()}.xlsx"
    return Response(
        content=gerar_planilha_documentos(exportacao.linhas),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'},
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/integration/test_exportacao_api.py -v`
Expected: 5 passed

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all previously-passing tests still pass (baseline before this phase: 314 passed, 1 skipped), plus the new ones — no regressions

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/routers/documentos_router.py backend/app/main.py backend/tests/integration/test_exportacao_api.py
git commit -m "feat: add GET /empresas/{id}/documentos/exportar xlsx endpoint"
```

---

## Task 4: Frontend API client method

**Files:**
- Modify: `frontend/src/api/client.ts`

**Interfaces:**
- Consumes: `GET /empresas/{empresaId}/documentos/exportar` and its `Content-Disposition: attachment; filename="..."` header (Task 3); the file-level `BASE_URL` constant already defined in `client.ts`.
- Produces (Task 5 relies on this exact name/shape): `api.documentos.exportar(empresaId: number): Promise<{ blob: Blob; nomeArquivo: string }>`.

The shared `request()` helper assumes a JSON body, so this method calls `fetch` directly. It rejects with an `Error` carrying the backend's `detail` on any non-2xx response, like `request()` does.

- [ ] **Step 1: Add the method**

In `frontend/src/api/client.ts`, inside the `documentos` object, right after `corrigirClassificacaoLote`, add:

```typescript
    exportar: async (empresaId: number): Promise<{ blob: Blob; nomeArquivo: string }> => {
      const response = await fetch(`${BASE_URL}/empresas/${empresaId}/documentos/exportar`);
      if (!response.ok) {
        const body = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(body.detail ?? "Erro na requisição");
      }
      const disposicao = response.headers.get("Content-Disposition") ?? "";
      const correspondencia = /filename="([^"]+)"/.exec(disposicao);
      return {
        blob: await response.blob(),
        nomeArquivo: correspondencia ? correspondencia[1] : "comprovantes.xlsx",
      };
    },
```

- [ ] **Step 2: Verify the frontend builds**

Run: `cd frontend && npm run build`
Expected: build succeeds with no TypeScript errors (the new method is unused until Task 5, which is not an error)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat: add api.documentos.exportar client method"
```

---

## Task 5: `ExportarPlanilha` component + wiring

**Files:**
- Create: `frontend/src/components/ExportarPlanilha.tsx`
- Modify: `frontend/src/pages/EmpresasPage.tsx`

**Interfaces:**
- Consumes: `api.documentos.exportar(empresaId)` (Task 4); existing `api.documentos.filaRevisao(empresaId): Promise<ItemFilaRevisao[]>` (Fase 5).
- Produces: `ExportarPlanilha({ empresaId }: { empresaId: number }): JSX.Element`, mounted in `EmpresasPage.tsx` beside "Processar".

Behavior (from the spec): on click, first count the review queue via `filaRevisao`, then download the file, then — only if the queue had items — show `N documento(s) ainda na fila de revisão — as linhas sem conta ficaram em branco na planilha.`. Any failure is shown as an error message. The button is disabled while exporting. There is no automated test (no frontend component test framework in this project); it is verified by `npm run build` here and by the manual pass in Task 6.

- [ ] **Step 1: Create the component**

Create `frontend/src/components/ExportarPlanilha.tsx`:

```tsx
import { useState } from "react";
import { api } from "../api/client";

function baixarArquivo(blob: Blob, nomeArquivo: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = nomeArquivo;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function ExportarPlanilha({ empresaId }: { empresaId: number }) {
  const [exportando, setExportando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  async function handleExportar() {
    setExportando(true);
    setAviso(null);
    setErro(null);
    try {
      const pendentes = await api.documentos.filaRevisao(empresaId);
      const { blob, nomeArquivo } = await api.documentos.exportar(empresaId);
      baixarArquivo(blob, nomeArquivo);
      if (pendentes.length > 0) {
        setAviso(
          `${pendentes.length} documento(s) ainda na fila de revisão — as linhas sem conta ficaram em branco na planilha.`,
        );
      }
    } catch (err) {
      setErro((err as Error).message);
    } finally {
      setExportando(false);
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <button
        onClick={handleExportar}
        disabled={exportando}
        className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white disabled:opacity-50"
      >
        {exportando ? "Exportando..." : "Exportar planilha"}
      </button>
      {aviso && <p className="text-xs text-amber-700">{aviso}</p>}
      {erro && <p className="text-xs text-red-600">{erro}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Wire it into `EmpresasPage.tsx`**

Add the import next to the other component imports (alphabetical order, after `EmpresaList`):

```tsx
import { ExportarPlanilha } from "../components/ExportarPlanilha";
```

Then replace this block in the "Comprovantes" section:

```tsx
          <button
            onClick={handleProcessar}
            disabled={documentos.every((d) => d.status !== "PENDENTE")}
            className="self-start rounded bg-slate-800 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          >
            Processar
          </button>
```

with:

```tsx
          <div className="flex items-start gap-2">
            <button
              onClick={handleProcessar}
              disabled={documentos.every((d) => d.status !== "PENDENTE")}
              className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white disabled:opacity-50"
            >
              Processar
            </button>
            <ExportarPlanilha key={empresaSelecionadaId} empresaId={empresaSelecionadaId} />
          </div>
```

The `key={empresaSelecionadaId}` is intentional (plan refinement 3): it remounts the component when the selected empresa changes, discarding any stale warning, error or in-flight state.

- [ ] **Step 3: Verify the frontend builds**

Run: `cd frontend && npm run build`
Expected: build succeeds with no TypeScript errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ExportarPlanilha.tsx frontend/src/pages/EmpresasPage.tsx
git commit -m "feat: add Exportar planilha button beside Processar"
```

---

## Task 6: Manual end-to-end verification

**Files:** none (verification only; no commits)

Environment notes carried over from Fase 4 and Fase 5: port 8000 is occupied on this machine by an unrelated app ("TickeTess") that cannot be stopped, and port 5173 by another unrelated dev server. Use a temporary setup and revert it afterwards.

- [ ] **Step 1: Run the full automated suites once more**

Run: `cd backend && .venv/Scripts/python -m pytest -q` — Expected: all pass, no regressions (baseline 314 passed, 1 skipped, plus this phase's new tests).
Run: `cd frontend && npm run build` — Expected: succeeds.

- [ ] **Step 2: Start a temporary test environment**

- Backend on port 8001: `cd backend && .venv/Scripts/python -m uvicorn app.main:app --port 8001` (run in the background).
- TEMPORARILY (never commit) change `BASE_URL` in `frontend/src/api/client.ts` to `http://localhost:8001` and add `"http://localhost:5174"` to `allow_origins` in `backend/app/main.py`, then restart the backend so CORS picks it up.
- Frontend on port 5174: `npm --prefix frontend run dev -- --port 5174`.
- In the Fase 5 verification, Ollama could intercept classification; that does not matter here.

- [ ] **Step 3: Create test data via the API**

Create a new empresa (distinct CNPJ), a plano, two analytic contas, one regra (RECEBEDOR CNPJ `11222333000199` → conta 1), then upload and process (a) a PDF `Favorecido: Energisa Distribuidora / CNPJ: 11.222.333/0001-99 / Valor: R$ 150,00` (classified by REGRA) and (b) a PDF with unrecognizable text (ends `CONCLUIDO` without classification, so it stays in the review queue). Also upload a third PDF and DO NOT process it (stays `PENDENTE`).

- [ ] **Step 4: Verify the endpoint output directly**

`curl` the endpoint to a `.xlsx` file, open it with `openpyxl` (backend venv) and confirm: sheet `Documentos`; the 12 headers in order; exactly 2 data rows (the `PENDENTE` document is absent); row for (a) has `Valor` numeric `150`, CNPJ as text, `Conta (código)` `1`, `Origem` `REGRA`; row for (b) has only `Arquivo` and `Tipo` filled and empty conta/origem cells; `Content-Disposition` is `attachment; filename="comprovantes_<cnpj>_<AAAA-MM-DD>.xlsx"`.

- [ ] **Step 5: Verify in the browser**

Open the app, select the test empresa, and confirm:
1. The "Exportar planilha" button sits beside "Processar", in both tabs.
2. Before clicking, in the browser console, wrap `URL.createObjectURL` to stash the blob in `window.__blob`. Click the button: `window.__blob.size > 0`, its `type` is the Excel media type, and the downloaded name (the anchor's `download` attribute, captured by wrapping `HTMLAnchorElement.prototype.click`) is `comprovantes_<cnpj>_<AAAA-MM-DD>.xlsx` — NOT the fallback `comprovantes.xlsx`, which proves the CORS `expose_headers` fix works across origins.
3. The warning `1 documento(s) ainda na fila de revisão — as linhas sem conta ficaram em branco na planilha.` appears under the button (the unclassified document is in the queue).
4. While the export runs the button is disabled and reads "Exportando...".
5. Correct the queued document (Fila de Revisão tab), click export again: no warning appears this time.
6. Switch to another empresa: any previous warning/error disappears (the `key` remount).
7. Stop the backend and click export: a visible error message appears (no silent failure).
8. Regression: "Processar", the two tabs and the existing list/queue behavior still work as before.

- [ ] **Step 6: Restore the environment and report**

Stop the temporary backend and frontend servers, then `git checkout -- backend/app/main.py frontend/src/api/client.ts` (both files are committed by earlier tasks, so this restores the committed versions, INCLUDING the `expose_headers` change from Task 3) and confirm `git status` is clean. Report pass/fail for every item above before the final whole-branch review.
