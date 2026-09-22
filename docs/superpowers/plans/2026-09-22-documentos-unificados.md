# Documentos Unificados (Multi-Comprovante) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a single uploaded PDF contains multiple independent comprovantes (e.g. a 70-page bank export where each page is a separate payment receipt), the system detects this during background processing and creates an independent `Documento` (with its own OCR/extraction/classification) for each one, while a PDF with a single comprovante keeps behaving exactly as it does today.

**Architecture:** OCR now returns text per page instead of one concatenated string. A new pure function groups pages into comprovante segments by reusing the existing Fase 2 extraction as the boundary signal (a page whose extraction has `valor` + a CNPJ/CPF starts a new comprovante). The worker, per uploaded document: if grouping finds exactly one segment, the code path is byte-identical to today (same concatenated text, same single `Documento`); if it finds 2+, the original `Documento` becomes `DIVIDIDO` and each segment becomes a new, fully independent `Documento` (own file, OCR result, extraction, classification) flowing through the exact same downstream pipeline (fila de revisão, correção, exportação) with zero changes to those layers.

**Tech Stack:** Python/FastAPI backend (PyMuPDF/`fitz` for page splitting, already a dependency), React/TypeScript frontend. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-22-documentos-unificados-design.md`

## Global Constraints

- Extratos tabulares (multi-transaction single page) are explicitly out of scope — only page-boundary splitting of PDFs, nothing about parsing tables.
- A document that produces exactly 1 segment must behave **byte-identical** to the current implementation — same `OcrResultado.texto_extraido`, same `Extracao`, same `Classificacao`. This is the single most important correctness requirement in this plan; Task 7 has an explicit regression test for it.
- `MAX_PAGINAS` rises from 20 to exactly 300 (`backend/app/infrastructure/ocr/renderizador_pdf.py`).
- `StatusDocumento` gains `DIVIDIDO`; `Documento` gains a nullable `documento_origem_id` FK to `documentos.id`. No other schema change.
- Lote progress (`LoteProcessamento.documentos_processados`) counts by **originally uploaded file**, never by resulting comprovante — a file that becomes 70 comprovantes still counts as 1 processed document in the lote's progress.
- No new frontend screen, route, or endpoint — only the existing document list changes what it displays for a `DIVIDIDO` document and its children.
- Style: Portuguese domain names, dataclasses, no docstrings unless truly non-obvious (this codebase's modules do have occasional one-line module docstrings explaining *why*, e.g. `lote_worker.py`'s header — follow that pattern where a non-obvious design reason needs recording, not for routine functions).

**Plan refinement of the spec (decided while writing this plan, preserves the spec's intent and its most important constraint above):** the spec's OCR/extraction section says a segment's extraction is "reaproveitada, não recalculada" from the per-page boundary-detection pass. This plan does it differently for correctness: `agrupar_paginas_em_comprovantes` (Task 5) is used **only** to find segment boundaries and returns page-index groups, nothing else. For each segment, the worker (Task 7) concatenates that segment's page texts with the same `"\n".join(...)` used today and calls `extrair_dados_documento` **once**, fresh, on the combined text — this is exactly what happens today for a whole document, which is what makes the 1-segment regression requirement trivially true (concatenate-all-pages-and-extract-once is already today's exact behavior).

---

## Task 1: Schema — `Documento.documento_origem_id` + `StatusDocumento.DIVIDIDO`

**Files:**
- Modify: `backend/app/domain/enums.py`
- Modify: `backend/app/domain/entities.py`
- Modify: `backend/app/infrastructure/db/models.py`
- Modify: `backend/app/infrastructure/repositories/sqlalchemy_documento_repository.py`
- Modify: `backend/app/api/schemas/documento_schemas.py`
- Create: `backend/alembic/versions/0006_documentos_unificados.py`
- Test: `backend/tests/integration/test_fase_documentos_unificados_migration.py`

**Interfaces:**
- Produces: `StatusDocumento.DIVIDIDO` (enum member, value `"DIVIDIDO"`); `Documento.documento_origem_id: int | None = None` (new dataclass field, default `None`, added at the end so no existing positional/keyword construction breaks); `DocumentoModel.documento_origem_id` (nullable FK column, indexed); `DocumentoOut.documento_origem_id: int | None` (API schema field) — Task 7 and Task 8 rely on this exact field name end-to-end (entity → ORM → API → frontend).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_fase_documentos_unificados_migration.py`:

```python
from sqlalchemy import inspect
from sqlalchemy.pool import StaticPool

from app.infrastructure.db.base import Base
from app.infrastructure.db import models  # noqa: F401
from app.infrastructure.db.session import get_engine


def test_documentos_ganha_coluna_documento_origem_id():
    engine = get_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)

    inspetor = inspect(engine)
    colunas = {c["name"] for c in inspetor.get_columns("documentos")}

    assert "documento_origem_id" in colunas


def test_status_documento_aceita_dividido():
    from app.domain.enums import StatusDocumento

    assert StatusDocumento.DIVIDIDO.value == "DIVIDIDO"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/integration/test_fase_documentos_unificados_migration.py -v`
Expected: FAIL — `documento_origem_id` not in columns; `StatusDocumento` has no `DIVIDIDO` attribute

- [ ] **Step 3: Add the enum value**

In `backend/app/domain/enums.py`, replace:

```python
class StatusDocumento(str, Enum):
    PENDENTE = "PENDENTE"
    PROCESSANDO = "PROCESSANDO"
    CONCLUIDO = "CONCLUIDO"
    ERRO = "ERRO"
```

with:

```python
class StatusDocumento(str, Enum):
    PENDENTE = "PENDENTE"
    PROCESSANDO = "PROCESSANDO"
    CONCLUIDO = "CONCLUIDO"
    ERRO = "ERRO"
    DIVIDIDO = "DIVIDIDO"
```

- [ ] **Step 4: Add the entity field**

In `backend/app/domain/entities.py`, find the `Documento` dataclass:

```python
@dataclass
class Documento:
    id: int | None
    empresa_id: int
    nome_arquivo: str
    nome_exibicao: str
    caminho_arquivo: str
    extensao: str
    tamanho_bytes: int
    status: StatusDocumento = StatusDocumento.PENDENTE
    mensagem_erro: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
```

Add `documento_origem_id: int | None = None` as the last field:

```python
@dataclass
class Documento:
    id: int | None
    empresa_id: int
    nome_arquivo: str
    nome_exibicao: str
    caminho_arquivo: str
    extensao: str
    tamanho_bytes: int
    status: StatusDocumento = StatusDocumento.PENDENTE
    mensagem_erro: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    documento_origem_id: int | None = None
```

- [ ] **Step 5: Add the ORM column**

In `backend/app/infrastructure/db/models.py`, find `DocumentoModel` and add a column right after `updated_at`:

```python
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )
    documento_origem_id: Mapped[int | None] = mapped_column(
        ForeignKey("documentos.id"), nullable=True, index=True
    )
```

(This is a self-referencing FK — SQLAlchemy handles this fine with a plain `ForeignKey("documentos.id")` on the same table, same pattern already used by `ContaModel.conta_pai_id` in the same file.)

- [ ] **Step 6: Update the repository mapping**

In `backend/app/infrastructure/repositories/sqlalchemy_documento_repository.py`:

Replace the `_to_entity` function:

```python
def _to_entity(model: DocumentoModel) -> Documento:
    return Documento(
        id=model.id,
        empresa_id=model.empresa_id,
        nome_arquivo=model.nome_arquivo,
        nome_exibicao=model.nome_exibicao,
        caminho_arquivo=model.caminho_arquivo,
        extensao=model.extensao,
        tamanho_bytes=model.tamanho_bytes,
        status=StatusDocumento(model.status),
        mensagem_erro=model.mensagem_erro,
        created_at=model.created_at,
        updated_at=model.updated_at,
        documento_origem_id=model.documento_origem_id,
    )
```

Replace `criar`:

```python
    def criar(self, documento: Documento) -> Documento:
        model = DocumentoModel(
            empresa_id=documento.empresa_id,
            nome_arquivo=documento.nome_arquivo,
            nome_exibicao=documento.nome_exibicao,
            caminho_arquivo=documento.caminho_arquivo,
            extensao=documento.extensao,
            tamanho_bytes=documento.tamanho_bytes,
            status=documento.status.value,
            mensagem_erro=documento.mensagem_erro,
            documento_origem_id=documento.documento_origem_id,
        )
        self._session.add(model)
        self._session.flush()
        return _to_entity(model)
```

`atualizar` and the rest of the file are unchanged — a `Documento` is never expected to change its `documento_origem_id` after creation, so `atualizar` (which already only touches `status`/`mensagem_erro`/`nome_exibicao`) doesn't need it.

- [ ] **Step 7: Add the API schema field**

In `backend/app/api/schemas/documento_schemas.py`, add to `DocumentoOut`:

```python
class DocumentoOut(BaseModel):
    id: int
    empresa_id: int
    nome_arquivo: str
    nome_exibicao: str
    extensao: str
    tamanho_bytes: int
    status: StatusDocumento
    mensagem_erro: str | None
    created_at: datetime
    updated_at: datetime
    documento_origem_id: int | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 8: Write the migration**

Create `backend/alembic/versions/0006_documentos_unificados.py`:

```python
"""documentos unificados: documento_origem_id em documentos

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("documentos") as batch_op:
        batch_op.add_column(sa.Column("documento_origem_id", sa.Integer, nullable=True))
        batch_op.create_foreign_key(
            "fk_documentos_documento_origem_id", "documentos", ["documento_origem_id"], ["id"]
        )
    op.create_index(
        "ix_documentos_documento_origem_id", "documentos", ["documento_origem_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_documentos_documento_origem_id", table_name="documentos")
    with op.batch_alter_table("documentos") as batch_op:
        batch_op.drop_constraint("fk_documentos_documento_origem_id", type_="foreignkey")
        batch_op.drop_column("documento_origem_id")
```

(`batch_alter_table` is required for SQLite, which cannot `ALTER TABLE ADD COLUMN ... REFERENCES` directly in older modes — this matches how SQLite-safe column additions are conventionally done with Alembic. **Validated by actually running `alembic upgrade head` / `downgrade 0005` / `upgrade head` again against a real copy of the dev database before this plan was committed** — the FK must be added via a separately-named `create_foreign_key` call, not inline in `sa.Column(...)`, because SQLite batch mode requires every constraint it recreates to have an explicit name; an inline unnamed `sa.ForeignKey(...)` raises `ValueError: Constraint must have a name` when the batch operation flushes. If the project's existing migrations 0002-0005 used a different SQLite-safe pattern, check one of them first — none of them currently add a column to an existing table, so there is no established precedent to match.)

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/integration/test_fase_documentos_unificados_migration.py -v`
Expected: 2 passed

- [ ] **Step 10: Fix a pre-existing test that asserts an exact column set at migration "head"**

**Validated while writing this plan — this is a real, necessary fix, not optional.** `backend/tests/integration/test_fase1_migration.py::test_migration_adds_fase1_columns_and_table` runs the full migration chain to `"head"` and asserts the `documentos` table has *exactly* this column set (no new columns allowed): `{"id", "empresa_id", "nome_arquivo", "nome_exibicao", "caminho_arquivo", "extensao", "tamanho_bytes", "status", "mensagem_erro", "created_at", "updated_at"}`. This phase is the first one to ever add a column to `documentos` after Fase 1, so this brittleness was never triggered before. Add `"documento_origem_id"` to that expected set:

In `backend/tests/integration/test_fase1_migration.py`, replace:

```python
    assert documento_cols == {
        "id", "empresa_id", "nome_arquivo", "nome_exibicao", "caminho_arquivo",
        "extensao", "tamanho_bytes", "status", "mensagem_erro", "created_at", "updated_at",
    }
```

with:

```python
    assert documento_cols == {
        "id", "empresa_id", "nome_arquivo", "nome_exibicao", "caminho_arquivo",
        "extensao", "tamanho_bytes", "status", "mensagem_erro", "created_at", "updated_at",
        "documento_origem_id",
    }
```

(The test's own downgrade assertion at the bottom, `command.downgrade(alembic_cfg, "0001")` down to `{"id", "empresa_id", "created_at"}`, is unaffected — migration 0006 downgrades no further than 0005, and this test's downgrade path goes all the way to 0001, past where 0006 even applies.)

- [ ] **Step 11: Run the full backend suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all previously-passing tests still pass (baseline before this phase, on `master` at the point this branch forked: 341 passed, 1 skipped), plus the 2 new tests from Step 1 = 343 passed, 1 skipped. **Validated exactly this way while writing this plan** — confirmed 343 passed/1 skipped after both the schema changes and the `test_fase1_migration.py` fix above.

- [ ] **Step 12: Commit**

```bash
git add backend/app/domain/enums.py backend/app/domain/entities.py backend/app/infrastructure/db/models.py backend/app/infrastructure/repositories/sqlalchemy_documento_repository.py backend/app/api/schemas/documento_schemas.py backend/alembic/versions/0006_documentos_unificados.py backend/tests/integration/test_fase_documentos_unificados_migration.py backend/tests/integration/test_fase1_migration.py
git commit -m "feat: add documento_origem_id and StatusDocumento.DIVIDIDO for multi-comprovante support"
```

---

## Task 2: Raise `MAX_PAGINAS` to 300

**Files:**
- Modify: `backend/app/infrastructure/ocr/renderizador_pdf.py`
- Test: `backend/tests/unit/test_renderizador_pdf.py` (existing file — the existing tests already use the `MAX_PAGINAS` constant, so they automatically adapt to the new value; this task only needs to update the constant and its comment)

**Interfaces:**
- Produces: `MAX_PAGINAS = 300` (was `20`) — no other symbol changes.

- [ ] **Step 1: Confirm the existing tests already parametrize on the constant**

Read `backend/tests/unit/test_renderizador_pdf.py` — `test_recusa_pdf_acima_do_limite_de_paginas`, `test_renderiza_pdf_exatamente_no_limite_de_paginas`, and `test_pipeline_converte_pdf_gigante_em_erro_do_documento` all build test PDFs using `MAX_PAGINAS` from the module, not a hardcoded number. No test file changes needed for this task — raising the constant automatically makes these tests build 300/305-page test PDFs instead of 20/25-page ones, still exercising the same logic. (Building a 305-page blank-page test PDF with `fitz` is fast — each page is empty, this does not meaningfully slow the test.)

- [ ] **Step 2: Run the existing tests to confirm current baseline**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_renderizador_pdf.py -v`
Expected: 4 passed (current behavior, limit still 20)

- [ ] **Step 3: Raise the limit**

In `backend/app/infrastructure/ocr/renderizador_pdf.py`, replace:

```python
# Comprovantes de pagamento praticamente nunca passam de duas páginas. O limite
# existe para que um PDF gigante (acidental ou malicioso) não renderize
# centenas de bitmaps e estoure a memória do worker.
MAX_PAGINAS = 20
```

with:

```python
# Um comprovante avulso quase sempre tem 1-2 páginas, mas um "documento
# unificado" (Fase Documentos Unificados) pode ser um lote inteiro de
# comprovantes de um mês num único PDF. O limite existe para que um PDF
# gigante (acidental ou malicioso) não renderize milhares de bitmaps e
# estoure a memória do worker — 300 páginas cobre um lote mensal real com
# folga.
MAX_PAGINAS = 300
```

- [ ] **Step 4: Run tests to verify they still pass with the new limit**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_renderizador_pdf.py -v`
Expected: 4 passed (same tests, now exercising 300/305-page PDFs)

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: no regressions

- [ ] **Step 6: Commit**

```bash
git add backend/app/infrastructure/ocr/renderizador_pdf.py
git commit -m "feat: raise MAX_PAGINAS from 20 to 300 for multi-comprovante PDFs"
```

---

## Task 3: `extrair_texto_nativo` returns per-page text

**Files:**
- Modify: `backend/app/infrastructure/ocr/pdf_nativo.py`
- Test: `backend/tests/unit/test_pdf_nativo.py` (create if it doesn't already exist — check first; if it exists, add to it instead of creating a duplicate)

**Interfaces:**
- Produces: `extrair_texto_nativo(conteudo_pdf: bytes) -> list[str] | None` (was `str | None`) — Task 4 consumes this exact new return type.

- [ ] **Step 1: Check whether a test file already exists**

Run: `ls backend/tests/unit/test_pdf_nativo.py 2>&1 || echo "does not exist"`

If it exists, read it first and add the new tests below to it, preserving any existing tests (updating their assertions to the new list-based return type, since the old `str | None` contract no longer exists — there should be no other consumers of `extrair_texto_nativo` besides `processar_documento`, which Task 4 updates in the same PR).

- [ ] **Step 2: Write the failing tests**

Create (or add to) `backend/tests/unit/test_pdf_nativo.py`:

```python
import fitz

from app.infrastructure.ocr.pdf_nativo import extrair_texto_nativo


def _pdf_com_paginas(*textos: str) -> bytes:
    documento = fitz.open()
    for texto in textos:
        pagina = documento.new_page()
        pagina.insert_text((72, 72), texto)
    conteudo = documento.tobytes()
    documento.close()
    return conteudo


def test_devolve_uma_entrada_por_pagina():
    conteudo = _pdf_com_paginas("PRIMEIRA PAGINA TEXTO SUFICIENTE", "SEGUNDA PAGINA TEXTO SUFICIENTE")

    resultado = extrair_texto_nativo(conteudo)

    assert resultado is not None
    assert len(resultado) == 2
    assert "PRIMEIRA PAGINA" in resultado[0]
    assert "SEGUNDA PAGINA" in resultado[1]


def test_pdf_sem_texto_suficiente_devolve_none():
    documento = fitz.open()
    documento.new_page()
    conteudo = documento.tobytes()
    documento.close()

    assert extrair_texto_nativo(conteudo) is None


def test_limiar_minimo_e_avaliado_sobre_o_total_nao_por_pagina():
    # Uma página curta (poucas letras) não deve, sozinha, derrubar o
    # documento inteiro para OCR se o total combinado já é suficiente.
    conteudo = _pdf_com_paginas("AB", "TEXTO SUFICIENTEMENTE LONGO NA SEGUNDA PAGINA PARA PASSAR DO LIMIAR")

    resultado = extrair_texto_nativo(conteudo)

    assert resultado is not None
    assert len(resultado) == 2
    assert resultado[0] == "AB"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_pdf_nativo.py -v`
Expected: FAIL — current `extrair_texto_nativo` returns `str | None`, not a list, so `len(resultado) == 2` / indexing assertions fail

- [ ] **Step 4: Write the implementation**

Replace the full content of `backend/app/infrastructure/ocr/pdf_nativo.py`:

```python
import io

from pypdf import PdfReader

TAMANHO_MINIMO_TEXTO = 20


def extrair_texto_nativo(conteudo_pdf: bytes) -> list[str] | None:
    leitor = PdfReader(io.BytesIO(conteudo_pdf))
    textos_por_pagina = [pagina.extract_text() or "" for pagina in leitor.pages]
    total = sum(len(texto) for texto in textos_por_pagina)
    if total < TAMANHO_MINIMO_TEXTO:
        return None
    return textos_por_pagina
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_pdf_nativo.py -v`
Expected: 3 passed (plus any pre-existing tests in the same file, if it already existed)

- [ ] **Step 6: Commit**

```bash
git add backend/app/infrastructure/ocr/pdf_nativo.py backend/tests/unit/test_pdf_nativo.py
git commit -m "feat: extrair_texto_nativo returns per-page text instead of concatenated string"
```

Note: this commit alone breaks `backend/app/infrastructure/ocr/pipeline.py` (its caller) — that is expected and fixed in Task 4, which must land before the full suite is green again. Do not run the full suite as a gate for this task; Task 4's Step 6 (full suite) is the first point after this change where the whole suite is expected to pass again.

---

## Task 4: `processar_documento` returns per-page OCR results

**Files:**
- Modify: `backend/app/infrastructure/ocr/pipeline.py`
- Modify: `backend/tests/unit/test_ocr_pipeline.py` (existing file — every test currently asserts `resultado.texto`, all need updating)
- Modify: `backend/tests/unit/test_renderizador_pdf.py:49-57` (`test_pipeline_converte_pdf_gigante_em_erro_do_documento` reads `resultado.erro`, unaffected — no change needed there, listed here only so the implementer knows to check it, not to edit it)

**Interfaces:**
- Consumes: `extrair_texto_nativo(conteudo_pdf) -> list[str] | None` (Task 3).
- Produces: `ResultadoPipelineOcr.textos_por_pagina: list[str]` (was `texto: str`) — Task 7 (`lote_worker.py`) consumes this exact field name.

**CRITICAL:** this is a breaking rename of a field used by every test in `test_ocr_pipeline.py` and by `lote_worker.py` (Task 7). Grep for every remaining reference before committing:

```bash
grep -rn "\.texto\b" backend/app/infrastructure/ocr/ backend/tests/unit/test_ocr_pipeline.py
```

Every hit inside these files must become `.textos_por_pagina` (or be a genuinely different attribute — read each hit before changing it). `lote_worker.py` is intentionally left with the old `.texto` reference until Task 7 — that is fine, it is fixed there, not here.

- [ ] **Step 1: Update the existing tests first (still failing at this point, that's expected)**

Replace the full content of `backend/tests/unit/test_ocr_pipeline.py`:

```python
from unittest.mock import patch

import fitz

from app.domain.enums import MetodoOcr
from app.infrastructure.ocr.pipeline import processar_documento


def _pdf_com_texto(texto: str) -> bytes:
    documento = fitz.open()
    pagina = documento.new_page()
    pagina.insert_text((72, 72), texto)
    conteudo = documento.tobytes()
    documento.close()
    return conteudo


def _pdf_vazio() -> bytes:
    documento = fitz.open()
    documento.new_page()
    conteudo = documento.tobytes()
    documento.close()
    return conteudo


def test_pdf_com_texto_usa_extracao_nativa():
    conteudo = _pdf_com_texto("COMPROVANTE TESTE 123456789012345")

    resultado = processar_documento(conteudo, ".pdf")

    assert resultado.metodo == MetodoOcr.PDF_NATIVO
    assert len(resultado.textos_por_pagina) == 1
    assert "COMPROVANTE" in resultado.textos_por_pagina[0]
    assert resultado.erro is None


def test_pdf_escaneado_usa_paddleocr_quando_disponivel():
    conteudo = _pdf_vazio()

    with patch("app.infrastructure.ocr.pipeline.renderizar_paginas_pdf", return_value=[b"fake-imagem"]), \
         patch("app.infrastructure.ocr.paddle_engine.PaddleOcrEngine") as MockPaddle:
        MockPaddle.return_value.extrair_texto.return_value = "texto via paddle"

        resultado = processar_documento(conteudo, ".pdf")

    assert resultado.metodo == MetodoOcr.PADDLEOCR
    assert resultado.textos_por_pagina == ["texto via paddle"]
    assert resultado.erro is None


def test_pdf_escaneado_cai_para_tesseract_quando_paddle_falha():
    conteudo = _pdf_vazio()

    with patch("app.infrastructure.ocr.pipeline.renderizar_paginas_pdf", return_value=[b"fake-imagem"]), \
         patch("app.infrastructure.ocr.paddle_engine.PaddleOcrEngine", side_effect=RuntimeError("sem modelo")), \
         patch("app.infrastructure.ocr.tesseract_engine.TesseractOcrEngine") as MockTesseract:
        MockTesseract.return_value.extrair_texto.return_value = "texto via tesseract"

        resultado = processar_documento(conteudo, ".pdf")

    assert resultado.metodo == MetodoOcr.TESSERACT
    assert resultado.textos_por_pagina == ["texto via tesseract"]
    assert resultado.erro is None


def test_imagem_direta_pula_extracao_nativa_e_vai_para_ocr():
    conteudo = b"fake-imagem-bytes"

    with patch("app.infrastructure.ocr.paddle_engine.PaddleOcrEngine") as MockPaddle:
        MockPaddle.return_value.extrair_texto.return_value = "texto de imagem"

        resultado = processar_documento(conteudo, ".png")

    assert resultado.metodo == MetodoOcr.PADDLEOCR
    assert resultado.textos_por_pagina == ["texto de imagem"]


def test_pdf_com_multiplas_paginas_de_texto_nativo_preserva_cada_pagina():
    conteudo = fitz.open()
    for texto in ("PAGINA UM COMPROVANTE", "PAGINA DOIS COMPROVANTE"):
        pagina = conteudo.new_page()
        pagina.insert_text((72, 72), texto)
    conteudo_bytes = conteudo.tobytes()
    conteudo.close()

    resultado = processar_documento(conteudo_bytes, ".pdf")

    assert resultado.metodo == MetodoOcr.PDF_NATIVO
    assert len(resultado.textos_por_pagina) == 2
    assert "PAGINA UM" in resultado.textos_por_pagina[0]
    assert "PAGINA DOIS" in resultado.textos_por_pagina[1]


def test_pdf_escaneado_com_multiplas_paginas_preserva_cada_pagina():
    conteudo = _pdf_vazio()

    with patch(
        "app.infrastructure.ocr.pipeline.renderizar_paginas_pdf",
        return_value=[b"fake-imagem-1", b"fake-imagem-2"],
    ), patch("app.infrastructure.ocr.paddle_engine.PaddleOcrEngine") as MockPaddle:
        MockPaddle.return_value.extrair_texto.side_effect = ["texto pagina 1", "texto pagina 2"]

        resultado = processar_documento(conteudo, ".pdf")

    assert resultado.metodo == MetodoOcr.PADDLEOCR
    assert resultado.textos_por_pagina == ["texto pagina 1", "texto pagina 2"]


def test_ambos_engines_falham_retorna_resultado_com_erro():
    conteudo = _pdf_vazio()

    with patch("app.infrastructure.ocr.pipeline.renderizar_paginas_pdf", return_value=[b"fake-imagem"]), \
         patch("app.infrastructure.ocr.paddle_engine.PaddleOcrEngine", side_effect=RuntimeError("sem modelo")), \
         patch("app.infrastructure.ocr.tesseract_engine.TesseractOcrEngine", side_effect=RuntimeError("sem binario")):
        resultado = processar_documento(conteudo, ".pdf")

    assert resultado.erro is not None
    assert resultado.textos_por_pagina == []


def test_pdf_malformado_na_extracao_nativa_nao_propaga_excecao():
    conteudo = b"not a real pdf"

    resultado = processar_documento(conteudo, ".pdf")

    assert resultado.erro is not None
    assert resultado.textos_por_pagina == []
    assert resultado.metodo == MetodoOcr.TESSERACT


def test_falha_ao_renderizar_paginas_pdf_nao_propaga_excecao():
    conteudo = _pdf_vazio()

    with patch(
        "app.infrastructure.ocr.pipeline.renderizar_paginas_pdf",
        side_effect=RuntimeError("falha ao renderizar pagina"),
    ):
        resultado = processar_documento(conteudo, ".pdf")

    assert resultado.erro is not None
    assert resultado.textos_por_pagina == []
    assert resultado.metodo == MetodoOcr.TESSERACT
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_ocr_pipeline.py -v`
Expected: FAIL — `ResultadoPipelineOcr` has no `textos_por_pagina` attribute yet

- [ ] **Step 3: Write the implementation**

Replace the full content of `backend/app/infrastructure/ocr/pipeline.py`:

```python
import time
from dataclasses import dataclass

from app.domain.enums import MetodoOcr
from app.infrastructure.ocr.pdf_nativo import extrair_texto_nativo
from app.infrastructure.ocr.renderizador_pdf import renderizar_paginas_pdf


@dataclass
class ResultadoPipelineOcr:
    textos_por_pagina: list[str]
    metodo: MetodoOcr
    tempo_processamento_ms: int
    erro: str | None = None


def _executar_engine_em_imagens(engine, imagens: list[bytes]) -> list[str]:
    return [engine.extrair_texto(imagem) for imagem in imagens]


def processar_documento(conteudo: bytes, extensao: str) -> ResultadoPipelineOcr:
    inicio = time.monotonic()

    if extensao == ".pdf":
        try:
            textos_nativos = extrair_texto_nativo(conteudo)
            if textos_nativos is not None:
                tempo_ms = int((time.monotonic() - inicio) * 1000)
                return ResultadoPipelineOcr(
                    textos_por_pagina=textos_nativos,
                    metodo=MetodoOcr.PDF_NATIVO,
                    tempo_processamento_ms=tempo_ms,
                )
            imagens = renderizar_paginas_pdf(conteudo)
        except Exception as exc:
            tempo_ms = int((time.monotonic() - inicio) * 1000)
            return ResultadoPipelineOcr(
                textos_por_pagina=[],
                metodo=MetodoOcr.TESSERACT,
                tempo_processamento_ms=tempo_ms,
                erro=f"Falha ao processar PDF: {exc}",
            )
    else:
        imagens = [conteudo]

    erro_paddle: str | None = None
    try:
        from app.infrastructure.ocr.paddle_engine import PaddleOcrEngine

        textos = _executar_engine_em_imagens(PaddleOcrEngine(), imagens)
        if any(texto.strip() for texto in textos):
            tempo_ms = int((time.monotonic() - inicio) * 1000)
            return ResultadoPipelineOcr(
                textos_por_pagina=textos, metodo=MetodoOcr.PADDLEOCR,
                tempo_processamento_ms=tempo_ms,
            )
        erro_paddle = "PaddleOCR não reconheceu texto."
    except Exception as exc:
        erro_paddle = str(exc)

    try:
        from app.infrastructure.ocr.tesseract_engine import TesseractOcrEngine

        textos = _executar_engine_em_imagens(TesseractOcrEngine(), imagens)
        tempo_ms = int((time.monotonic() - inicio) * 1000)
        if any(texto.strip() for texto in textos):
            return ResultadoPipelineOcr(
                textos_por_pagina=textos, metodo=MetodoOcr.TESSERACT,
                tempo_processamento_ms=tempo_ms,
            )
        return ResultadoPipelineOcr(
            textos_por_pagina=[], metodo=MetodoOcr.TESSERACT, tempo_processamento_ms=tempo_ms,
            erro=f"Nenhum engine de OCR reconheceu texto (PaddleOCR: {erro_paddle}).",
        )
    except Exception as exc:
        tempo_ms = int((time.monotonic() - inicio) * 1000)
        return ResultadoPipelineOcr(
            textos_por_pagina=[], metodo=MetodoOcr.TESSERACT, tempo_processamento_ms=tempo_ms,
            erro=f"PaddleOCR: {erro_paddle}; Tesseract: {exc}",
        )
```

**Validated while writing this plan**: this exact file content was applied and run — 9/9 tests in `test_ocr_pipeline.py` pass, and running the full suite afterward confirms failures are confined to exactly the worker-dependent integration tests listed in Step 6 below (11 failures, all in `test_documentos_api.py`, `test_exportacao_api.py`, `test_fila_revisao_api.py`, `test_lotes_api.py` — every one fixed by Task 7).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_ocr_pipeline.py -v`
Expected: 9 passed

- [ ] **Step 5: Confirm no remaining `.texto` references outside `lote_worker.py`**

Run: `grep -rn "\.texto\b" backend/app/infrastructure/ocr/ backend/tests/unit/test_ocr_pipeline.py`
Expected: no output (or only unrelated matches like `.texto_extraido`, which is a different, unrelated attribute on `OcrResultado` — read each hit to confirm before treating "no output" as the only acceptable result)

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: FAIL only in tests that exercise `lote_worker.py` end-to-end (it still reads `resultado_pipeline.texto`, which no longer exists) — this is the expected, documented breakage fixed by Task 7. **Validated while writing this plan** — the exact failure set was:
```
FAILED tests/integration/test_documentos_api.py::test_resultado_com_classificacao_apos_conta_deletada
FAILED tests/integration/test_exportacao_api.py::test_documento_processado_e_classificado_aparece_com_todos_os_dados
FAILED tests/integration/test_fila_revisao_api.py::test_fila_revisao_inclui_documento_concluido_sem_classificacao
FAILED tests/integration/test_lotes_api.py::test_processar_lote_ate_concluir
FAILED tests/integration/test_lotes_api.py::test_segunda_chamada_de_processar_nao_reprocessa_documentos_ja_reivindicados
FAILED tests/integration/test_lotes_api.py::test_cancelar_lote_ja_concluido_retorna_409
FAILED tests/integration/test_lotes_api.py::test_worker_para_de_submeter_apos_cancelamento
FAILED tests/integration/test_lotes_api.py::test_novo_lote_pode_ser_iniciado_apos_lote_anterior_falhar
FAILED tests/integration/test_lotes_api.py::test_processar_lote_extrai_dados_do_documento
FAILED tests/integration/test_lotes_api.py::test_processar_lote_classifica_documento_por_regra
FAILED tests/integration/test_lotes_api.py::test_processar_lote_classifica_por_fuzzy_usando_documento_anterior_do_mesmo_lote
11 failed, 335 passed, 1 skipped
```
If your run produces a different failure set, stop and investigate before proceeding — something else changed.

- [ ] **Step 7: Commit**

```bash
git add backend/app/infrastructure/ocr/pipeline.py backend/tests/unit/test_ocr_pipeline.py
git commit -m "feat: processar_documento returns per-page OCR results (textos_por_pagina)"
```

---

## Task 5: `agrupar_paginas_em_comprovantes` — boundary detection

**Files:**
- Create: `backend/app/infrastructure/extracao/agrupamento.py`
- Test: `backend/tests/unit/test_agrupamento.py`

**Interfaces:**
- Consumes: `extrair_dados_documento(texto: str) -> DadosExtraidos` (already exists, `backend/app/infrastructure/extracao/pipeline.py`, unchanged — `DadosExtraidos.valor: Decimal | None`, `.pagador_documento: str | None`, `.recebedor_documento: str | None`).
- Produces: `agrupar_paginas_em_comprovantes(textos_por_pagina: list[str]) -> list[list[int]]` — Task 7 consumes this exact name/signature. Each inner list is the 0-based page indices belonging to one comprovante segment, in ascending order; the outer list is in document order. This function does **not** return extraction data — Task 7 re-runs `extrair_dados_documento` on each segment's combined text (see this plan's Global Constraints "Plan refinement" note).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_agrupamento.py`:

```python
from app.infrastructure.extracao.agrupamento import agrupar_paginas_em_comprovantes

_COMPLETA = "Favorecido: Empresa Teste\nCNPJ: 11.222.333/0001-99\nValor: R$ 100,00"
_INCOMPLETA = "Texto solto sem CNPJ nem valor reconhecivel."


def test_uma_pagina_um_segmento():
    assert agrupar_paginas_em_comprovantes([_COMPLETA]) == [[0]]


def test_duas_paginas_ambas_completas_dois_segmentos():
    assert agrupar_paginas_em_comprovantes([_COMPLETA, _COMPLETA]) == [[0], [1]]


def test_segunda_pagina_incompleta_e_continuacao_da_primeira():
    assert agrupar_paginas_em_comprovantes([_COMPLETA, _INCOMPLETA]) == [[0, 1]]


def test_primeira_pagina_incompleta_ainda_inicia_o_primeiro_segmento():
    assert agrupar_paginas_em_comprovantes([_INCOMPLETA]) == [[0]]


def test_primeira_incompleta_segunda_completa_terceira_incompleta():
    # Página 0 sempre inicia o segmento 1 (mesmo sem extração completa).
    # Página 1, completa, inicia um novo segmento (2). Página 2, incompleta,
    # é continuação do segmento 2.
    resultado = agrupar_paginas_em_comprovantes([_INCOMPLETA, _COMPLETA, _INCOMPLETA])
    assert resultado == [[0], [1, 2]]


def test_lista_vazia_devolve_lista_vazia():
    assert agrupar_paginas_em_comprovantes([]) == []


def test_muitas_paginas_completas_seguidas_um_segmento_por_pagina():
    textos = [_COMPLETA] * 5
    resultado = agrupar_paginas_em_comprovantes(textos)
    assert resultado == [[0], [1], [2], [3], [4]]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_agrupamento.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.infrastructure.extracao.agrupamento'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/infrastructure/extracao/agrupamento.py`:

```python
from app.infrastructure.extracao.pipeline import extrair_dados_documento


def _pagina_inicia_novo_comprovante(texto: str) -> bool:
    dados = extrair_dados_documento(texto)
    tem_documento_fiscal = dados.pagador_documento is not None or dados.recebedor_documento is not None
    return dados.valor is not None and tem_documento_fiscal


def agrupar_paginas_em_comprovantes(textos_por_pagina: list[str]) -> list[list[int]]:
    if not textos_por_pagina:
        return []

    segmentos: list[list[int]] = []
    segmento_atual: list[int] = [0]

    for indice in range(1, len(textos_por_pagina)):
        if _pagina_inicia_novo_comprovante(textos_por_pagina[indice]):
            segmentos.append(segmento_atual)
            segmento_atual = [indice]
        else:
            segmento_atual.append(indice)

    segmentos.append(segmento_atual)
    return segmentos
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_agrupamento.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/extracao/agrupamento.py backend/tests/unit/test_agrupamento.py
git commit -m "feat: add agrupar_paginas_em_comprovantes for multi-comprovante boundary detection"
```

---

## Task 6: `recortar_paginas_pdf` — physical page splitting

**Files:**
- Create: `backend/app/infrastructure/ocr/recorte_pdf.py`
- Test: `backend/tests/unit/test_recorte_pdf.py`

**Interfaces:**
- Produces: `recortar_paginas_pdf(conteudo_pdf: bytes, indices_paginas: list[int]) -> bytes` — Task 7 consumes this exact name/signature. `indices_paginas` are 0-based page indices (matching `agrupar_paginas_em_comprovantes`'s output), not required to be contiguous although in practice they always will be (a segment from Task 5 is always a contiguous run).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_recorte_pdf.py`:

```python
import fitz

from app.infrastructure.ocr.recorte_pdf import recortar_paginas_pdf


def _pdf_com_paginas(*textos: str) -> bytes:
    documento = fitz.open()
    for texto in textos:
        pagina = documento.new_page()
        pagina.insert_text((72, 72), texto)
    conteudo = documento.tobytes()
    documento.close()
    return conteudo


def test_recorta_um_subconjunto_de_paginas_contiguo():
    original = _pdf_com_paginas("PAGINA UM", "PAGINA DOIS", "PAGINA TRES")

    recorte = recortar_paginas_pdf(original, [1, 2])

    resultado = fitz.open(stream=recorte, filetype="pdf")
    try:
        assert resultado.page_count == 2
        assert "PAGINA DOIS" in resultado[0].get_text()
        assert "PAGINA TRES" in resultado[1].get_text()
    finally:
        resultado.close()


def test_recorta_uma_unica_pagina():
    original = _pdf_com_paginas("PAGINA UM", "PAGINA DOIS")

    recorte = recortar_paginas_pdf(original, [0])

    resultado = fitz.open(stream=recorte, filetype="pdf")
    try:
        assert resultado.page_count == 1
        assert "PAGINA UM" in resultado[0].get_text()
    finally:
        resultado.close()


def test_recorte_preserva_ordem_dos_indices():
    original = _pdf_com_paginas("PAGINA UM", "PAGINA DOIS", "PAGINA TRES")

    recorte = recortar_paginas_pdf(original, [2, 0])

    resultado = fitz.open(stream=recorte, filetype="pdf")
    try:
        assert resultado.page_count == 2
        assert "PAGINA TRES" in resultado[0].get_text()
        assert "PAGINA UM" in resultado[1].get_text()
    finally:
        resultado.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_recorte_pdf.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.infrastructure.ocr.recorte_pdf'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/infrastructure/ocr/recorte_pdf.py`:

```python
import fitz


def recortar_paginas_pdf(conteudo_pdf: bytes, indices_paginas: list[int]) -> bytes:
    origem = fitz.open(stream=conteudo_pdf, filetype="pdf")
    try:
        novo = fitz.open()
        try:
            for indice in indices_paginas:
                novo.insert_pdf(origem, from_page=indice, to_page=indice)
            return novo.tobytes()
        finally:
            novo.close()
    finally:
        origem.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_recorte_pdf.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/ocr/recorte_pdf.py backend/tests/unit/test_recorte_pdf.py
git commit -m "feat: add recortar_paginas_pdf for physical page splitting"
```

---

## Task 7: Worker integration — the core of this feature

**Files:**
- Modify: `backend/app/infrastructure/workers/lote_worker.py`
- Test: `backend/tests/integration/test_lote_worker_documentos_unificados.py`

**Interfaces:**
- Consumes: `processar_documento(conteudo, extensao) -> ResultadoPipelineOcr` with `.textos_por_pagina` (Task 4); `agrupar_paginas_em_comprovantes(textos_por_pagina) -> list[list[int]]` (Task 5); `recortar_paginas_pdf(conteudo_pdf, indices_paginas) -> bytes` (Task 6); `Documento.documento_origem_id`, `StatusDocumento.DIVIDIDO` (Task 1); `ArmazenamentoArquivos.salvar(empresa_id, nome_original, conteudo) -> tuple[str, str, str]` (existing, `backend/app/application/ports.py`, unchanged); `classificar_documento(extracao, regras, contas_disponiveis, historico_fuzzy)` (existing, `backend/app/infrastructure/classificacao/pipeline.py`, unchanged).
- Produces: no new public symbols — this task changes `processar_lote_em_background`'s internal behavior only. Nothing downstream (API, frontend) needs new interfaces because every comprovante child is a plain `Documento` flowing through already-existing endpoints.

This is the task with the most risk of a subtle regression. Read `backend/app/infrastructure/workers/lote_worker.py` in full before starting — the brief below gives you the exact two loops to change and the exact replacement code, but you need to see the surrounding context (imports, `_resetar_documentos_processando_para_pendente`, the cancellation check, the final lote-status block) to place the changes correctly; none of that surrounding code changes.

- [ ] **Step 1: Write the failing integration test**

Create `backend/tests/integration/test_lote_worker_documentos_unificados.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/integration/test_lote_worker_documentos_unificados.py -v`
Expected: FAIL — the worker still reads `resultado_pipeline.texto` (removed in Task 4) and never sets `DIVIDIDO`/`documento_origem_id`

- [ ] **Step 3: Rewrite the worker's second loop**

In `backend/app/infrastructure/workers/lote_worker.py`:

1. Add these imports near the top, alongside the existing `app.infrastructure...` imports:

```python
from app.infrastructure.extracao.agrupamento import agrupar_paginas_em_comprovantes
from app.infrastructure.ocr.recorte_pdf import recortar_paginas_pdf
```

2. In the **first** loop (the submission loop, currently lines ~157-176), the content bytes read from storage need to be kept for later (Task 7 needs them again to cut pages out of the original PDF). Replace:

```python
            futuros_por_documento = {}
            empresa_id_lote: int | None = None
            for documento_id in documento_ids:
                # O cancelamento chega por outra sessão (a da request HTTP). Sem
                # expirar a identity map, `session.get` devolveria a cópia em
                # cache do lote e o worker nunca enxergaria o CANCELADO.
                session.expire_all()
                lote_atual = lote_repo.obter_por_id(lote_id)
                if lote_atual is None or lote_atual.status == StatusLote.CANCELADO:
                    break
                documento = documento_repo.obter_por_id(documento_id)
                if documento is None:
                    logger.warning(
                        "Documento %s não encontrado; ignorado no lote %s.",
                        documento_id, lote_id,
                    )
                    continue
                if empresa_id_lote is None:
                    empresa_id_lote = documento.empresa_id
                conteudo = storage.ler(documento.caminho_arquivo)
                futuro = pool.submit(processar_documento, conteudo, documento.extensao)
                futuros_por_documento[documento_id] = futuro
```

with:

```python
            futuros_por_documento = {}
            conteudo_por_documento: dict[int, bytes] = {}
            empresa_id_lote: int | None = None
            for documento_id in documento_ids:
                # O cancelamento chega por outra sessão (a da request HTTP). Sem
                # expirar a identity map, `session.get` devolveria a cópia em
                # cache do lote e o worker nunca enxergaria o CANCELADO.
                session.expire_all()
                lote_atual = lote_repo.obter_por_id(lote_id)
                if lote_atual is None or lote_atual.status == StatusLote.CANCELADO:
                    break
                documento = documento_repo.obter_por_id(documento_id)
                if documento is None:
                    logger.warning(
                        "Documento %s não encontrado; ignorado no lote %s.",
                        documento_id, lote_id,
                    )
                    continue
                if empresa_id_lote is None:
                    empresa_id_lote = documento.empresa_id
                conteudo = storage.ler(documento.caminho_arquivo)
                # Guardado para o recorte de páginas de um documento unificado
                # (segunda etapa, depois que o OCR devolver o resultado) — sem
                # isto teríamos que reler o arquivo do disco outra vez.
                conteudo_por_documento[documento_id] = conteudo
                futuro = pool.submit(processar_documento, conteudo, documento.extensao)
                futuros_por_documento[documento_id] = futuro
```

3. Replace the whole body of the **second** loop's success branch (currently the `else:` block starting at `documento.status = StatusDocumento.CONCLUIDO` through the end of the `if resultado_classificacao is not None:` block, right before `documento_repo.atualizar(documento)`). The failing branch (`if resultado_pipeline.erro:`) is unchanged. Replace:

```python
                if resultado_pipeline.erro:
                    documento.status = StatusDocumento.ERRO
                    documento.mensagem_erro = resultado_pipeline.erro
                else:
                    documento.status = StatusDocumento.CONCLUIDO
                    resultado_repo.criar(
                        OcrResultado(
                            id=None, documento_id=documento_id,
                            texto_extraido=resultado_pipeline.texto,
                            metodo=resultado_pipeline.metodo,
                            tempo_processamento_ms=resultado_pipeline.tempo_processamento_ms,
                        )
                    )
                    dados = extrair_dados_documento(resultado_pipeline.texto)
                    extracao_criada = extracao_repo.criar(
                        Extracao(
                            id=None, documento_id=documento_id,
                            pagador_nome=dados.pagador_nome,
                            pagador_documento=dados.pagador_documento,
                            recebedor_nome=dados.recebedor_nome,
                            recebedor_documento=dados.recebedor_documento,
                            valor=dados.valor,
                            data_pagamento=dados.data_pagamento,
                            tipo_documento=dados.tipo_documento,
                            banco_nome=dados.banco_nome,
                        )
                    )

                    resultado_classificacao = classificar_documento(
                        extracao_criada, regras, contas_disponiveis, historico_fuzzy
                    )
                    if resultado_classificacao is not None:
                        nova_classificacao = classificacao_repo.criar(
                            Classificacao(
                                id=None,
                                empresa_id=documento.empresa_id,
                                documento_id=documento_id,
                                conta_id=resultado_classificacao.conta_id,
                                origem=resultado_classificacao.origem,
                                regra_id=resultado_classificacao.regra_id,
                                score_similaridade=resultado_classificacao.score_similaridade,
                            )
                        )
                        nome_para_historico = (
                            extracao_criada.recebedor_nome or extracao_criada.pagador_nome
                        )
                        if nome_para_historico is not None:
                            historico_fuzzy.append(
                                (
                                    nome_para_historico,
                                    resultado_classificacao.conta_id,
                                    nova_classificacao.created_at,
                                )
                            )
                documento_repo.atualizar(documento)
```

with:

```python
                if resultado_pipeline.erro:
                    documento.status = StatusDocumento.ERRO
                    documento.mensagem_erro = resultado_pipeline.erro
                    documento_repo.atualizar(documento)
                else:
                    segmentos = agrupar_paginas_em_comprovantes(resultado_pipeline.textos_por_pagina)

                    if len(segmentos) <= 1:
                        # Caminho idêntico ao comportamento anterior a esta
                        # funcionalidade: junta todas as páginas (mesmo join
                        # já usado por extrair_texto_nativo) e extrai uma vez.
                        texto_completo = "\n".join(resultado_pipeline.textos_por_pagina)
                        documento.status = StatusDocumento.CONCLUIDO
                        documento_repo.atualizar(documento)
                        _processar_comprovante(
                            documento=documento,
                            texto=texto_completo,
                            metodo=resultado_pipeline.metodo,
                            tempo_processamento_ms=resultado_pipeline.tempo_processamento_ms,
                            resultado_repo=resultado_repo,
                            extracao_repo=extracao_repo,
                            classificacao_repo=classificacao_repo,
                            regras=regras,
                            contas_disponiveis=contas_disponiveis,
                            historico_fuzzy=historico_fuzzy,
                        )
                    else:
                        documento.status = StatusDocumento.DIVIDIDO
                        documento_repo.atualizar(documento)
                        conteudo_original = conteudo_por_documento.get(documento_id)
                        for segmento in segmentos:
                            pagina_inicio, pagina_fim = segmento[0] + 1, segmento[-1] + 1
                            sufixo = (
                                f" — pág. {pagina_inicio}"
                                if pagina_inicio == pagina_fim
                                else f" — pág. {pagina_inicio}-{pagina_fim}"
                            )
                            nome_exibicao_filho = f"{documento.nome_exibicao}{sufixo}"
                            bytes_recortados = recortar_paginas_pdf(conteudo_original, segmento)
                            # Passa o nome ORIGINAL (sem o sufixo "— pág. N")
                            # para a validação de extensão — o sufixo tem um
                            # ponto em "pág.", que faria Path(...).suffix
                            # devolver algo como ". 1-2" em vez de ".pdf" e
                            # rejeitar o arquivo. O nome físico gravado em
                            # disco é sempre gerado pelo storage (timestamp +
                            # uuid), então isto não afeta o nome exibido.
                            nome_fisico, caminho_relativo, extensao_filho = storage.salvar(
                                documento.empresa_id, documento.nome_exibicao, bytes_recortados
                            )
                            filho = documento_repo.criar(
                                Documento(
                                    id=None,
                                    empresa_id=documento.empresa_id,
                                    nome_arquivo=nome_fisico,
                                    nome_exibicao=nome_exibicao_filho,
                                    caminho_arquivo=caminho_relativo,
                                    extensao=extensao_filho,
                                    tamanho_bytes=len(bytes_recortados),
                                    status=StatusDocumento.CONCLUIDO,
                                    documento_origem_id=documento.id,
                                )
                            )
                            texto_segmento = "\n".join(
                                resultado_pipeline.textos_por_pagina[i] for i in segmento
                            )
                            _processar_comprovante(
                                documento=filho,
                                texto=texto_segmento,
                                metodo=resultado_pipeline.metodo,
                                tempo_processamento_ms=resultado_pipeline.tempo_processamento_ms,
                                resultado_repo=resultado_repo,
                                extracao_repo=extracao_repo,
                                classificacao_repo=classificacao_repo,
                                regras=regras,
                                contas_disponiveis=contas_disponiveis,
                                historico_fuzzy=historico_fuzzy,
                            )
```

4. Add the extracted helper function `_processar_comprovante` right after `_listar_contas_analiticas` (before `_marcar_lote_como_falhou`), so both the 1-segment and N-segment paths call the exact same code for "grava OCR + extração + classificação de um comprovante" — this is what guarantees the regression requirement (same function, same order of operations, for both paths):

```python
def _processar_comprovante(
    documento,
    texto: str,
    metodo,
    tempo_processamento_ms: int,
    resultado_repo,
    extracao_repo,
    classificacao_repo,
    regras: list,
    contas_disponiveis: list,
    historico_fuzzy: list[tuple[str, int, datetime]],
) -> None:
    """Grava OcrResultado + Extracao + Classificacao de um comprovante.

    Compartilhado pelo caminho de 1 segmento (documento original) e pelo
    caminho de 2+ segmentos (cada filho) — é o que garante que os dois
    caminhos produzem exatamente o mesmo resultado para o mesmo texto.
    """
    resultado_repo.criar(
        OcrResultado(
            id=None, documento_id=documento.id,
            texto_extraido=texto,
            metodo=metodo,
            tempo_processamento_ms=tempo_processamento_ms,
        )
    )
    dados = extrair_dados_documento(texto)
    extracao_criada = extracao_repo.criar(
        Extracao(
            id=None, documento_id=documento.id,
            pagador_nome=dados.pagador_nome,
            pagador_documento=dados.pagador_documento,
            recebedor_nome=dados.recebedor_nome,
            recebedor_documento=dados.recebedor_documento,
            valor=dados.valor,
            data_pagamento=dados.data_pagamento,
            tipo_documento=dados.tipo_documento,
            banco_nome=dados.banco_nome,
        )
    )

    resultado_classificacao = classificar_documento(
        extracao_criada, regras, contas_disponiveis, historico_fuzzy
    )
    if resultado_classificacao is not None:
        nova_classificacao = classificacao_repo.criar(
            Classificacao(
                id=None,
                empresa_id=documento.empresa_id,
                documento_id=documento.id,
                conta_id=resultado_classificacao.conta_id,
                origem=resultado_classificacao.origem,
                regra_id=resultado_classificacao.regra_id,
                score_similaridade=resultado_classificacao.score_similaridade,
            )
        )
        nome_para_historico = extracao_criada.recebedor_nome or extracao_criada.pagador_nome
        if nome_para_historico is not None:
            historico_fuzzy.append(
                (nome_para_historico, resultado_classificacao.conta_id, nova_classificacao.created_at)
            )
```

5. Add `Documento` to the existing entity import line near the top of the file:

```python
from app.domain.entities import Classificacao, Documento, Extracao, OcrResultado
```

(was `from app.domain.entities import Classificacao, Extracao, OcrResultado`)

- [ ] **Step 4: Run the new test to verify it passes**

Run: `cd backend && .venv/Scripts/python -m pytest tests/integration/test_lote_worker_documentos_unificados.py -v`
Expected: 4 passed

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all tests pass, including `test_lotes_api.py` and every other test that exercises the worker (these were the tests Task 4 documented as expected-broken until this task) — no regressions anywhere

- [ ] **Step 6: Commit**

```bash
git add backend/app/infrastructure/workers/lote_worker.py backend/tests/integration/test_lote_worker_documentos_unificados.py
git commit -m "feat: split multi-comprovante PDFs into independent Documentos in the worker"
```

---

## Task 8: Frontend — `DIVIDIDO` status and child document display

**Files:**
- Modify: `frontend/src/types/documento.ts`
- Modify: `frontend/src/components/DocumentoList.tsx`

**Interfaces:**
- Consumes: `Documento.documento_origem_id: number | null` (API field from Task 1, already flows through the existing `api.documentos.list` response — no client method changes needed).
- Produces: no new exports — this task only changes what's rendered for existing data.

- [ ] **Step 1: Add the type and field**

In `frontend/src/types/documento.ts`, update:

```typescript
export type StatusDocumento = "PENDENTE" | "PROCESSANDO" | "CONCLUIDO" | "ERRO";
```

to:

```typescript
export type StatusDocumento = "PENDENTE" | "PROCESSANDO" | "CONCLUIDO" | "ERRO" | "DIVIDIDO";
```

And add `documento_origem_id: number | null;` to the `Documento` interface:

```typescript
export interface Documento {
  id: number;
  empresa_id: number;
  nome_arquivo: string;
  nome_exibicao: string;
  extensao: string;
  tamanho_bytes: number;
  status: StatusDocumento;
  mensagem_erro: string | null;
  created_at: string;
  updated_at: string;
  documento_origem_id: number | null;
}
```

- [ ] **Step 2: Update `DocumentoList.tsx`**

Read the current file first (`frontend/src/components/DocumentoList.tsx`) — Fase 5/6 already modified it, so confirm the exact current content before editing rather than assuming line numbers from an earlier phase.

Add a color for `DIVIDIDO` to `corStatus`:

```tsx
function corStatus(status: Documento["status"]): string {
  switch (status) {
    case "CONCLUIDO":
      return "text-green-700";
    case "ERRO":
      return "text-red-700";
    case "PROCESSANDO":
      return "text-amber-700";
    case "DIVIDIDO":
      return "text-blue-700";
    default:
      return "text-slate-500";
  }
}
```

In the list rendering, add a "N comprovante(s)" note next to a `DIVIDIDO` document's status, computed from the already-loaded `documentos` list (no new API call). Find the `<li>` that renders each `documento` row (the block containing `corStatus(documento.status)` and the "Ver texto" button), and add a sibling span right after the status span:

```tsx
              <span className={corStatus(documento.status)}>{documento.status}</span>
              {documento.status === "DIVIDIDO" && (
                <span className="text-xs text-slate-500">
                  ({documentos.filter((d) => d.documento_origem_id === documento.id).length} comprovante(s))
                </span>
              )}
```

The existing `{documento.status === "CONCLUIDO" && (...)}` condition that shows the "Ver texto" button already excludes `DIVIDIDO` (it's an equality check against `"CONCLUIDO"`, not a negated check) — no change needed there.

- [ ] **Step 3: Verify the frontend builds**

Run: `cd frontend && npm run build`
Expected: build succeeds with no TypeScript errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/documento.ts frontend/src/components/DocumentoList.tsx
git commit -m "feat: show DIVIDIDO status and child comprovante count in document list"
```

---

## Task 9: Manual end-to-end verification

**Files:** none (verification only; no commits)

Environment notes carried over from every prior phase: port 8000 may be occupied by an unrelated app on this machine; use a temporary alternate-port setup and revert it afterwards (never commit the temporary `BASE_URL`/CORS edits).

- [ ] **Step 1: Run the full automated suites once more**

Run: `cd backend && .venv/Scripts/python -m pytest -q` — expect all pass, no regressions.
Run: `cd frontend && npm run build` — expect success.

- [ ] **Step 2: Start a temporary test environment**

Same pattern as every prior phase's manual verification: backend on an alternate port (e.g. 8001), frontend on an alternate port (e.g. 5174) with `BASE_URL` in `frontend/src/api/client.ts` and `allow_origins` in `backend/app/main.py` temporarily pointed at each other, reverted at the end via `git checkout --`.

- [ ] **Step 3: Upload the real 70-page file**

Create a test empresa, plano, at least one analytic conta and one regra (so at least some comprovantes classify by REGRA, making the result easy to spot-check). Upload the user's real file (path referenced earlier in this session: `\\server\Tesserato Contabilidade\EMPRESAS\O MELHOR ATACAREJO LTDA\Documentos Diversos\2026\08-2026\Matriz\COMPROVANTES DE PAGAMENTOS DE BOLETOS MATRIZ (2).pdf` — copy it into the scratchpad directory first via PowerShell, the same way it was done earlier in this session, since the Bash tool cannot reach UNC paths directly). Process the lote and wait for completion — this is a real 70-page OCR+extraction+classification run, expect it to take some time.

- [ ] **Step 4: Verify the results**

- The original uploaded document shows `status=DIVIDIDO` with a "(≈70 comprovante(s))" note in the UI.
- The document list shows ~70 new child documents, each named with a `— pág. N` (or `— pág. N-M`) suffix.
- Spot-check 3-4 children's `GET /documentos/{id}/resultado`: confirm `valor`/`pagador_documento`/`recebedor_documento` match what a human reading that specific page of the original PDF would see (cross-check against the `fitz` text extraction already done earlier in this session for pages 1, 2, 68, 69, 70).
- Confirm the lote's progress bar showed "1 de N arquivos" during processing (N = however many files were in that upload batch, not ~70).
- Open "Fila de Revisão" — confirm the `DIVIDIDO` parent document does NOT appear there, only its children (and only the children that are unclassified or FUZZY, per the existing Fase 5 behavior, unchanged).
- Export the planilha (Fase 6 feature) for this empresa — confirm the `DIVIDIDO` parent is absent from the exported rows (its `status` is not `CONCLUIDO`, so the existing export filter already excludes it with no code change) and the children are present.

- [ ] **Step 5: Restore the environment and report**

Revert the temporary `BASE_URL`/CORS edits (`git checkout -- backend/app/main.py frontend/src/api/client.ts`), confirm `git status` is clean relative to this plan's own commits, stop the temporary servers, and report pass/fail for every item above before the final whole-branch review.
