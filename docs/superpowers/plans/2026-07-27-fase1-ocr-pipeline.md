# Fase 1 — Upload + Pipeline de OCR — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user upload multiple payment-receipt files (PDF/PNG/JPG) for a company, process them in parallel (native PDF text extraction, falling back to PaddleOCR, falling back to Tesseract), track batch progress with cancel support, and view the extracted raw text per document — no structured field extraction yet (that's Fase 2).

**Architecture:** Extends the existing Fase 0 Clean Architecture (`domain` / `application` / `infrastructure` / `api`). New application-layer ports (`ArmazenamentoArquivos`, `OcrEngine`) keep the use cases free of direct infrastructure imports — a gap the Fase 0 final review flagged and fixed for the spreadsheet parser; this plan applies that port pattern from the start. The OCR pipeline is a plain, picklable module-level function so it can run inside a `ProcessPoolExecutor` (CPU-bound work, separate processes). A FastAPI `BackgroundTasks` job drives the batch: submits each pending document to the process pool, updates the batch's progress row after each result, and stops submitting new work once the batch is marked cancelled.

**Tech Stack:** Python (existing FastAPI/SQLAlchemy/Alembic backend), `pypdf` (native PDF text), `PyMuPDF` / `fitz` (render PDF pages to images, no external Poppler binary needed on Windows), `pytesseract` + `Pillow` (Tesseract OCR — requires the Tesseract binary installed separately and on PATH), `paddleocr` + `paddlepaddle` (PaddleOCR — CPU wheel). React/TypeScript frontend (existing Vite scaffold).

## Global Constraints

- No paid services anywhere in this phase.
- No authentication in this phase.
- Runs locally on Windows via terminal, no Docker.
- SQLite now, all schema choices must stay portable to PostgreSQL.
- Uploaded file extensions limited to `.pdf`, `.png`, `.jpg`, `.jpeg`; max 20MB per file.
- The physical filename on disk must never derive from the user-supplied filename (path-traversal safety) — a generated timestamp+uuid name is used instead; the original name is kept only as a display label (`nome_exibicao`).
- Every use case that references a parent entity (empresa, lote) must validate that parent exists before writing — apply this symmetrically to every write path that touches it, not just the first one built (lesson from the Fase 0 review cycle: a validation added to a "create" path was initially missed on the sibling "update"/"process" path).
- Integration test DB fixtures must go through the same `get_engine()` used by the app (see `backend/app/infrastructure/db/session.py`, which sets `PRAGMA foreign_keys=ON` for SQLite) rather than building ad hoc `create_engine()` calls, so tests exercise the same FK behavior as production.

---

## File Structure

```
backend/
  app/
    core/
      exceptions.py                          # MODIFY: add new exceptions
    domain/
      enums.py                                # MODIFY: add StatusDocumento, MetodoOcr, StatusLote
      entities.py                             # MODIFY: add Documento, OcrResultado, LoteProcessamento
    application/
      ports.py                                # CREATE: ArmazenamentoArquivos, OcrEngine ABCs
      dto.py                                  # MODIFY: add upload/lote DTOs
      repositories.py                         # MODIFY: add 3 new repository ABCs
      use_cases/
        documento_use_cases.py                # CREATE
        lote_use_cases.py                     # CREATE
    infrastructure/
      db/
        models.py                             # MODIFY: real columns + LoteProcessamentoModel
      repositories/
        sqlalchemy_documento_repository.py    # CREATE
        sqlalchemy_ocr_resultado_repository.py # CREATE
        sqlalchemy_lote_processamento_repository.py # CREATE
      storage/
        __init__.py                           # CREATE
        file_storage.py                       # CREATE
      ocr/
        __init__.py                           # CREATE
        pdf_nativo.py                         # CREATE
        renderizador_pdf.py                   # CREATE
        tesseract_engine.py                   # CREATE
        paddle_engine.py                      # CREATE
        pipeline.py                           # CREATE
    api/
      schemas/
        documento_schemas.py                  # CREATE
        lote_schemas.py                       # CREATE
      routers/
        documentos_router.py                  # CREATE
        lotes_router.py                       # CREATE
      deps.py                                 # MODIFY: add storage_root config accessor if needed
      main.py                                 # MODIFY: register new routers
  alembic/versions/
    0002_fase1_ocr_pipeline.py                # CREATE
  tests/
    unit/
      test_documento_domain.py                # (optional, folded into use case tests)
      test_file_storage.py                    # CREATE
      test_pdf_nativo.py                      # CREATE
      test_renderizador_pdf.py                # CREATE
      test_ocr_pipeline.py                    # CREATE
      test_documento_use_cases.py             # CREATE
      test_lote_use_cases.py                  # CREATE
    integration/
      test_documentos_api.py                  # CREATE
      test_lotes_api.py                       # CREATE
      fixtures/
        comprovante_texto.pdf                 # CREATE (generated by a helper script/test setup, see Task 7)
frontend/
  src/
    types/
      documento.ts                            # CREATE
    api/
      client.ts                               # MODIFY: add documentos/lotes namespaces
    components/
      DocumentoDropzone.tsx                   # CREATE
      DocumentoList.tsx                       # CREATE
      ProgressoLote.tsx                       # CREATE
    pages/
      EmpresasPage.tsx                        # MODIFY: add documento upload/processing section
```

---

### Task 1: Database schema — real columns for `documentos`/`ocr_resultados`, new `lotes_processamento` table

**Files:**
- Modify: `backend/app/infrastructure/db/models.py`
- Create: `backend/alembic/versions/0002_fase1_ocr_pipeline.py`
- Test: `backend/tests/integration/test_fase1_migration.py`

**Interfaces:**
- Produces: `DocumentoModel`, `OcrResultadoModel` (replacing the Fase 0 stub versions with real columns), `LoteProcessamentoModel` (new) in `app.infrastructure.db.models`.

- [ ] **Step 1: Write the failing test**

`backend/tests/integration/test_fase1_migration.py`:
```python
from sqlalchemy import create_engine, inspect
from alembic import command
from alembic.config import Config


def test_migration_adds_fase1_columns_and_table(tmp_path):
    db_path = tmp_path / "test_fase1_migration.db"
    db_url = f"sqlite:///{db_path}"

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(db_url)
    inspector = inspect(engine)

    documento_cols = {c["name"] for c in inspector.get_columns("documentos")}
    assert documento_cols == {
        "id", "empresa_id", "nome_arquivo", "nome_exibicao", "caminho_arquivo",
        "extensao", "tamanho_bytes", "status", "mensagem_erro", "created_at", "updated_at",
    }

    ocr_cols = {c["name"] for c in inspector.get_columns("ocr_resultados")}
    assert ocr_cols == {
        "id", "documento_id", "texto_extraido", "metodo", "tempo_processamento_ms", "created_at",
    }

    assert "lotes_processamento" in inspector.get_table_names()
    lote_cols = {c["name"] for c in inspector.get_columns("lotes_processamento")}
    assert lote_cols == {
        "id", "empresa_id", "total_documentos", "documentos_processados", "status",
        "created_at", "concluido_em",
    }

    # downgrade must be symmetric
    command.downgrade(alembic_cfg, "0001")
    inspector = inspect(engine)
    documento_cols = {c["name"] for c in inspector.get_columns("documentos")}
    assert documento_cols == {"id", "empresa_id", "created_at"}
    assert "lotes_processamento" not in inspector.get_table_names()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/integration/test_fase1_migration.py -v`
Expected: FAIL (columns don't exist yet — the Fase 0 stub schema is still `id, empresa_id, created_at`).

- [ ] **Step 3: Update models.py — replace the Fase 0 stub `DocumentoModel`/`OcrResultadoModel`, add `LoteProcessamentoModel`**

In `backend/app/infrastructure/db/models.py`, replace the existing `DocumentoModel` class (currently `id`, `empresa_id`, `created_at`) with:

```python
class DocumentoModel(Base):
    __tablename__ = "documentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(
        ForeignKey("empresas.id"), nullable=False, index=True
    )
    nome_arquivo: Mapped[str] = mapped_column(String(255), nullable=False)
    nome_exibicao: Mapped[str] = mapped_column(String(255), nullable=False)
    caminho_arquivo: Mapped[str] = mapped_column(String(500), nullable=False)
    extensao: Mapped[str] = mapped_column(String(10), nullable=False)
    tamanho_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDENTE")
    mensagem_erro: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )
```

Replace the existing `OcrResultadoModel` (currently `id`, `empresa_id`, `created_at`) with:

```python
class OcrResultadoModel(Base):
    __tablename__ = "ocr_resultados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    documento_id: Mapped[int] = mapped_column(
        ForeignKey("documentos.id"), nullable=False, unique=True
    )
    texto_extraido: Mapped[str] = mapped_column(Text, nullable=False)
    metodo: Mapped[str] = mapped_column(String(20), nullable=False)
    tempo_processamento_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
```

Add a new `LoteProcessamentoModel` (place it near `DocumentoModel`):

```python
class LoteProcessamentoModel(Base):
    __tablename__ = "lotes_processamento"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
    total_documentos: Mapped[int] = mapped_column(Integer, nullable=False)
    documentos_processados: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="EM_ANDAMENTO")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

Add `Text` to the top-of-file import: `from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text`.

- [ ] **Step 4: Write the migration**

`backend/alembic/versions/0002_fase1_ocr_pipeline.py`:
```python
"""fase1 ocr pipeline: real documentos/ocr_resultados columns + lotes_processamento

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("documentos")
    op.create_table(
        "documentos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("nome_arquivo", sa.String(255), nullable=False),
        sa.Column("nome_exibicao", sa.String(255), nullable=False),
        sa.Column("caminho_arquivo", sa.String(500), nullable=False),
        sa.Column("extensao", sa.String(10), nullable=False),
        sa.Column("tamanho_bytes", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDENTE"),
        sa.Column("mensagem_erro", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_documentos_empresa_id", "documentos", ["empresa_id"])

    op.drop_table("ocr_resultados")
    op.create_table(
        "ocr_resultados",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "documento_id", sa.Integer, sa.ForeignKey("documentos.id"),
            nullable=False, unique=True,
        ),
        sa.Column("texto_extraido", sa.Text, nullable=False),
        sa.Column("metodo", sa.String(20), nullable=False),
        sa.Column("tempo_processamento_ms", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "lotes_processamento",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("total_documentos", sa.Integer, nullable=False),
        sa.Column(
            "documentos_processados", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="EM_ANDAMENTO"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("concluido_em", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("lotes_processamento")
    op.drop_table("ocr_resultados")
    op.drop_index("ix_documentos_empresa_id", table_name="documentos")
    op.drop_table("documentos")

    op.create_table(
        "documentos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "ocr_resultados",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
```

Note: dropping and recreating `documentos`/`ocr_resultados` (rather than `alter_column`) is safe here because no real data has ever been written to these stub tables in any deployed environment — they've only ever held `id`/`empresa_id`/`created_at` placeholders since Fase 0. Confirm this assumption by checking `git log --all --oneline -- backend/alembic/versions/` shows only `0001` before this task; if that's no longer true when you run this, stop and use `alter_column`/`add_column` instead of drop/recreate.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/integration/test_fase1_migration.py -v`
Expected: PASS

- [ ] **Step 6: Run the full existing suite to confirm no regressions**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all tests pass (the Fase 0 stub-table test, `test_schema_migration.py`, should still pass since it only asserts the table NAMES exist, not their old stub columns — verify this by reading that test before proceeding; if it asserts stub columns, it needs no change since `test_migration_creates_all_tables` in that file only checks `get_table_names()`).

- [ ] **Step 7: Commit**

```bash
git add backend/app/infrastructure/db/models.py backend/alembic/versions/0002_fase1_ocr_pipeline.py backend/tests/integration/test_fase1_migration.py
git commit -m "feat: add real documentos/ocr_resultados columns and lotes_processamento table"
```

---

### Task 2: Domain entities and enums for Documento, OcrResultado, LoteProcessamento

**Files:**
- Modify: `backend/app/domain/enums.py`
- Modify: `backend/app/domain/entities.py`
- Test: `backend/tests/unit/test_documento_domain.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `StatusDocumento`, `MetodoOcr`, `StatusLote` enums. `Documento`, `OcrResultado`, `LoteProcessamento` dataclasses.

- [ ] **Step 1: Write the failing test**

`backend/tests/unit/test_documento_domain.py`:
```python
from app.domain.entities import Documento, LoteProcessamento, OcrResultado
from app.domain.enums import MetodoOcr, StatusDocumento, StatusLote


def test_documento_default_status_is_pendente():
    documento = Documento(
        id=None, empresa_id=1, nome_arquivo="20260727_ab12cd34.pdf",
        nome_exibicao="comprovante.pdf", caminho_arquivo="empresa_1/documentos/x.pdf",
        extensao=".pdf", tamanho_bytes=1024,
    )
    assert documento.status == StatusDocumento.PENDENTE
    assert documento.mensagem_erro is None


def test_ocr_resultado_holds_metodo_e_texto():
    resultado = OcrResultado(
        id=None, documento_id=1, texto_extraido="Texto do comprovante",
        metodo=MetodoOcr.PDF_NATIVO, tempo_processamento_ms=42,
    )
    assert resultado.metodo == MetodoOcr.PDF_NATIVO


def test_lote_processamento_default_status_e_zero_processados():
    lote = LoteProcessamento(id=None, empresa_id=1, total_documentos=5)
    assert lote.status == StatusLote.EM_ANDAMENTO
    assert lote.documentos_processados == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_documento_domain.py -v`
Expected: FAIL with `ImportError` (names don't exist yet).

- [ ] **Step 3: Add enums**

Append to `backend/app/domain/enums.py`:
```python
class StatusDocumento(str, Enum):
    PENDENTE = "PENDENTE"
    PROCESSANDO = "PROCESSANDO"
    CONCLUIDO = "CONCLUIDO"
    ERRO = "ERRO"


class MetodoOcr(str, Enum):
    PDF_NATIVO = "PDF_NATIVO"
    PADDLEOCR = "PADDLEOCR"
    TESSERACT = "TESSERACT"


class StatusLote(str, Enum):
    EM_ANDAMENTO = "EM_ANDAMENTO"
    CONCLUIDO = "CONCLUIDO"
    CANCELADO = "CANCELADO"
```

- [ ] **Step 4: Add entities**

Append to `backend/app/domain/entities.py` (add `MetodoOcr, StatusDocumento, StatusLote` to the existing `from app.domain.enums import NaturezaConta` import line, making it `from app.domain.enums import MetodoOcr, NaturezaConta, StatusDocumento, StatusLote`):

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


@dataclass
class OcrResultado:
    id: int | None
    documento_id: int
    texto_extraido: str
    metodo: MetodoOcr
    tempo_processamento_ms: int
    created_at: datetime | None = None


@dataclass
class LoteProcessamento:
    id: int | None
    empresa_id: int
    total_documentos: int
    documentos_processados: int = 0
    status: StatusLote = StatusLote.EM_ANDAMENTO
    created_at: datetime | None = None
    concluido_em: datetime | None = None
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/unit/test_documento_domain.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/enums.py backend/app/domain/entities.py backend/tests/unit/test_documento_domain.py
git commit -m "feat: add Documento/OcrResultado/LoteProcessamento domain entities"
```

---

### Task 3: Repository interfaces, ports, and fakes

**Files:**
- Create: `backend/app/application/ports.py`
- Modify: `backend/app/application/repositories.py`
- Modify: `backend/app/core/exceptions.py`
- Modify: `backend/tests/fakes.py`

**Interfaces:**
- Consumes: `Documento`, `OcrResultado`, `LoteProcessamento` (Task 2).
- Produces: abstract `DocumentoRepository`, `OcrResultadoRepository`, `LoteProcessamentoRepository` in `app.application.repositories`. Abstract `ArmazenamentoArquivos`, `OcrEngine` in `app.application.ports`. New exceptions `ArquivoInvalido`, `DocumentoNaoEncontrado`, `LoteNaoEncontrado` in `app.core.exceptions`. Fakes `FakeDocumentoRepository`, `FakeOcrResultadoRepository`, `FakeLoteProcessamentoRepository`, `FakeArmazenamentoArquivos` in `tests.fakes`.

- [ ] **Step 1: Add new exceptions**

Append to `backend/app/core/exceptions.py`:
```python
class ArquivoInvalido(DomainError):
    def __init__(self, motivo: str):
        super().__init__(motivo)


class DocumentoNaoEncontrado(DomainError):
    def __init__(self, documento_id: int):
        super().__init__(f"Documento {documento_id} não encontrado.")


class LoteNaoEncontrado(DomainError):
    def __init__(self, lote_id: int):
        super().__init__(f"Lote de processamento {lote_id} não encontrado.")
```

- [ ] **Step 2: Write ports.py**

`backend/app/application/ports.py`:
```python
from abc import ABC, abstractmethod


class ArmazenamentoArquivos(ABC):
    @abstractmethod
    def salvar(
        self, empresa_id: int, nome_original: str, conteudo: bytes
    ) -> tuple[str, str, str]:
        """Retorna (nome_fisico, caminho_relativo, extensao)."""

    @abstractmethod
    def ler(self, caminho_relativo: str) -> bytes: ...


class OcrEngine(ABC):
    @abstractmethod
    def extrair_texto(self, imagem_bytes: bytes) -> str: ...
```

- [ ] **Step 3: Append repository interfaces**

Append to `backend/app/application/repositories.py` (add `Documento, LoteProcessamento, OcrResultado` to the existing `from app.domain.entities import ...` import line):

```python
class DocumentoRepository(ABC):
    @abstractmethod
    def criar(self, documento: Documento) -> Documento: ...

    @abstractmethod
    def obter_por_id(self, documento_id: int) -> Documento | None: ...

    @abstractmethod
    def listar_por_empresa(self, empresa_id: int) -> list[Documento]: ...

    @abstractmethod
    def listar_pendentes_por_empresa(self, empresa_id: int) -> list[Documento]: ...

    @abstractmethod
    def atualizar(self, documento: Documento) -> Documento: ...


class OcrResultadoRepository(ABC):
    @abstractmethod
    def criar(self, resultado: OcrResultado) -> OcrResultado: ...

    @abstractmethod
    def obter_por_documento_id(self, documento_id: int) -> OcrResultado | None: ...


class LoteProcessamentoRepository(ABC):
    @abstractmethod
    def criar(self, lote: LoteProcessamento) -> LoteProcessamento: ...

    @abstractmethod
    def obter_por_id(self, lote_id: int) -> LoteProcessamento | None: ...

    @abstractmethod
    def atualizar(self, lote: LoteProcessamento) -> LoteProcessamento: ...
```

- [ ] **Step 4: Append fakes**

Append to `backend/tests/fakes.py` (add `Documento, LoteProcessamento, OcrResultado` and `StatusDocumento` to the existing imports: `from app.domain.entities import Conta, Documento, Empresa, LoteProcessamento, OcrResultado, PlanoContas` and `from app.domain.enums import StatusDocumento`; also add `from app.application.ports import ArmazenamentoArquivos` and `from app.application.repositories import DocumentoRepository, LoteProcessamentoRepository, OcrResultadoRepository`):

```python
class FakeDocumentoRepository(DocumentoRepository):
    def __init__(self):
        self._items: dict[int, Documento] = {}
        self._next_id = 1

    def criar(self, documento: Documento) -> Documento:
        documento.id = self._next_id
        self._items[self._next_id] = documento
        self._next_id += 1
        return documento

    def obter_por_id(self, documento_id: int) -> Documento | None:
        return self._items.get(documento_id)

    def listar_por_empresa(self, empresa_id: int) -> list[Documento]:
        return [d for d in self._items.values() if d.empresa_id == empresa_id]

    def listar_pendentes_por_empresa(self, empresa_id: int) -> list[Documento]:
        return [
            d for d in self._items.values()
            if d.empresa_id == empresa_id and d.status == StatusDocumento.PENDENTE
        ]

    def atualizar(self, documento: Documento) -> Documento:
        self._items[documento.id] = documento
        return documento


class FakeOcrResultadoRepository(OcrResultadoRepository):
    def __init__(self):
        self._items: dict[int, OcrResultado] = {}
        self._next_id = 1

    def criar(self, resultado: OcrResultado) -> OcrResultado:
        resultado.id = self._next_id
        self._items[self._next_id] = resultado
        self._next_id += 1
        return resultado

    def obter_por_documento_id(self, documento_id: int) -> OcrResultado | None:
        return next((r for r in self._items.values() if r.documento_id == documento_id), None)


class FakeLoteProcessamentoRepository(LoteProcessamentoRepository):
    def __init__(self):
        self._items: dict[int, LoteProcessamento] = {}
        self._next_id = 1

    def criar(self, lote: LoteProcessamento) -> LoteProcessamento:
        lote.id = self._next_id
        self._items[self._next_id] = lote
        self._next_id += 1
        return lote

    def obter_por_id(self, lote_id: int) -> LoteProcessamento | None:
        return self._items.get(lote_id)

    def atualizar(self, lote: LoteProcessamento) -> LoteProcessamento:
        self._items[lote.id] = lote
        return lote


class FakeArmazenamentoArquivos(ArmazenamentoArquivos):
    def __init__(self):
        self._arquivos: dict[str, bytes] = {}
        self._contador = 0

    def salvar(self, empresa_id: int, nome_original: str, conteudo: bytes) -> tuple[str, str, str]:
        self._contador += 1
        extensao = "." + nome_original.rsplit(".", 1)[-1].lower()
        nome_fisico = f"fake_{self._contador}{extensao}"
        caminho_relativo = f"empresa_{empresa_id}/documentos/{nome_fisico}"
        self._arquivos[caminho_relativo] = conteudo
        return nome_fisico, caminho_relativo, extensao

    def ler(self, caminho_relativo: str) -> bytes:
        return self._arquivos[caminho_relativo]
```

- [ ] **Step 5: Verify the fakes satisfy the abstract interfaces**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -c "from tests.fakes import FakeDocumentoRepository, FakeOcrResultadoRepository, FakeLoteProcessamentoRepository, FakeArmazenamentoArquivos; FakeDocumentoRepository(); FakeOcrResultadoRepository(); FakeLoteProcessamentoRepository(); FakeArmazenamentoArquivos(); print('ok')"`
Expected: prints `ok`.

- [ ] **Step 6: Run the full suite to confirm no regressions**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/application/ports.py backend/app/application/repositories.py backend/app/core/exceptions.py backend/tests/fakes.py
git commit -m "feat: add Fase 1 repository interfaces, ports, exceptions, and fakes"
```

---

### Task 4: File storage service

**Files:**
- Create: `backend/app/infrastructure/storage/__init__.py`
- Create: `backend/app/infrastructure/storage/file_storage.py`
- Test: `backend/tests/unit/test_file_storage.py`

**Interfaces:**
- Consumes: `ArmazenamentoArquivos` (Task 3), `ArquivoInvalido` (Task 3).
- Produces: `EXTENSOES_PERMITIDAS: set[str]`, `TAMANHO_MAXIMO_BYTES: int`, `validar_extensao_e_tamanho(nome_original: str, tamanho_bytes: int) -> str` (returns lowercase extension, raises `ArquivoInvalido`). `LocalFileStorageService(storage_root: Path)` implementing `ArmazenamentoArquivos.salvar/ler`.

- [ ] **Step 1: Write the failing test**

`backend/tests/unit/test_file_storage.py`:
```python
import pytest

from app.core.exceptions import ArquivoInvalido
from app.infrastructure.storage.file_storage import (
    LocalFileStorageService,
    validar_extensao_e_tamanho,
)


def test_validar_extensao_permitida():
    assert validar_extensao_e_tamanho("comprovante.PDF", 1000) == ".pdf"


def test_validar_extensao_nao_permitida_falha():
    with pytest.raises(ArquivoInvalido, match="não permitida"):
        validar_extensao_e_tamanho("virus.exe", 1000)


def test_validar_tamanho_excedido_falha():
    with pytest.raises(ArquivoInvalido, match="tamanho máximo"):
        validar_extensao_e_tamanho("comprovante.pdf", 21 * 1024 * 1024)


def test_salvar_gera_nome_fisico_diferente_do_original_e_grava_arquivo(tmp_path):
    storage = LocalFileStorageService(tmp_path)

    nome_fisico, caminho_relativo, extensao = storage.salvar(
        empresa_id=1, nome_original="../../etc/passwd.pdf", conteudo=b"conteudo-teste"
    )

    assert extensao == ".pdf"
    assert nome_fisico != "../../etc/passwd.pdf"
    assert ".." not in caminho_relativo
    caminho_absoluto = tmp_path / caminho_relativo
    assert caminho_absoluto.exists()
    assert caminho_absoluto.read_bytes() == b"conteudo-teste"


def test_salvar_com_arquivo_invalido_nao_grava_nada(tmp_path):
    storage = LocalFileStorageService(tmp_path)

    with pytest.raises(ArquivoInvalido):
        storage.salvar(empresa_id=1, nome_original="malware.exe", conteudo=b"x")

    assert list(tmp_path.rglob("*")) == []


def test_ler_retorna_conteudo_salvo(tmp_path):
    storage = LocalFileStorageService(tmp_path)
    _, caminho_relativo, _ = storage.salvar(1, "a.pdf", b"olá")

    assert storage.ler(caminho_relativo) == b"olá"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_file_storage.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write file_storage.py**

`backend/app/infrastructure/storage/file_storage.py`:
```python
import uuid
from datetime import datetime
from pathlib import Path

from app.application.ports import ArmazenamentoArquivos
from app.core.exceptions import ArquivoInvalido

EXTENSOES_PERMITIDAS = {".pdf", ".png", ".jpg", ".jpeg"}
TAMANHO_MAXIMO_BYTES = 20 * 1024 * 1024


def validar_extensao_e_tamanho(nome_original: str, tamanho_bytes: int) -> str:
    extensao = Path(nome_original).suffix.lower()
    if extensao not in EXTENSOES_PERMITIDAS:
        permitidas = ", ".join(sorted(EXTENSOES_PERMITIDAS))
        raise ArquivoInvalido(
            f"Extensão '{extensao or '(sem extensão)'}' não permitida. Use: {permitidas}"
        )
    if tamanho_bytes > TAMANHO_MAXIMO_BYTES:
        limite_mb = TAMANHO_MAXIMO_BYTES // (1024 * 1024)
        raise ArquivoInvalido(f"Arquivo excede o tamanho máximo de {limite_mb}MB.")
    return extensao


class LocalFileStorageService(ArmazenamentoArquivos):
    def __init__(self, storage_root: Path):
        self._storage_root = Path(storage_root)

    def salvar(
        self, empresa_id: int, nome_original: str, conteudo: bytes
    ) -> tuple[str, str, str]:
        extensao = validar_extensao_e_tamanho(nome_original, len(conteudo))
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        nome_fisico = f"{timestamp}_{uuid.uuid4().hex[:8]}{extensao}"

        pasta_empresa = self._storage_root / f"empresa_{empresa_id}" / "documentos"
        pasta_empresa.mkdir(parents=True, exist_ok=True)

        caminho_absoluto = pasta_empresa / nome_fisico
        caminho_absoluto.write_bytes(conteudo)

        caminho_relativo = f"empresa_{empresa_id}/documentos/{nome_fisico}"
        return nome_fisico, caminho_relativo, extensao

    def ler(self, caminho_relativo: str) -> bytes:
        return (self._storage_root / caminho_relativo).read_bytes()
```

`backend/app/infrastructure/storage/__init__.py`: empty file.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/unit/test_file_storage.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/storage backend/tests/unit/test_file_storage.py
git commit -m "feat: add local file storage service with extension/size validation"
```

---

### Task 5: SQLAlchemy repositories for Documento, OcrResultado, LoteProcessamento

**Files:**
- Create: `backend/app/infrastructure/repositories/sqlalchemy_documento_repository.py`
- Create: `backend/app/infrastructure/repositories/sqlalchemy_ocr_resultado_repository.py`
- Create: `backend/app/infrastructure/repositories/sqlalchemy_lote_processamento_repository.py`
- Test: `backend/tests/integration/test_sqlalchemy_fase1_repositories.py`

**Interfaces:**
- Consumes: `DocumentoRepository`, `OcrResultadoRepository`, `LoteProcessamentoRepository` (Task 3), `DocumentoModel`, `OcrResultadoModel`, `LoteProcessamentoModel` (Task 1), the existing `db_session` pytest fixture from `backend/tests/conftest.py` (Fase 0 — reuse it, do not create a new ad hoc engine).
- Produces: `SqlAlchemyDocumentoRepository(session)`, `SqlAlchemyOcrResultadoRepository(session)`, `SqlAlchemyLoteProcessamentoRepository(session)`.

- [ ] **Step 1: Write the failing test**

`backend/tests/integration/test_sqlalchemy_fase1_repositories.py`:
```python
from app.domain.entities import Documento, LoteProcessamento, OcrResultado
from app.domain.enums import MetodoOcr, StatusDocumento, StatusLote
from app.infrastructure.repositories.sqlalchemy_documento_repository import (
    SqlAlchemyDocumentoRepository,
)
from app.infrastructure.repositories.sqlalchemy_lote_processamento_repository import (
    SqlAlchemyLoteProcessamentoRepository,
)
from app.infrastructure.repositories.sqlalchemy_ocr_resultado_repository import (
    SqlAlchemyOcrResultadoRepository,
)
from app.infrastructure.repositories.sqlalchemy_empresa_repository import (
    SqlAlchemyEmpresaRepository,
)
from app.domain.entities import Empresa


def _criar_empresa(db_session):
    repo = SqlAlchemyEmpresaRepository(db_session)
    empresa = repo.criar(
        Empresa(id=None, razao_social="Tesserato", nome_fantasia=None, cnpj="12345678000199")
    )
    db_session.commit()
    return empresa


def test_criar_listar_e_atualizar_documento(db_session):
    empresa = _criar_empresa(db_session)
    repo = SqlAlchemyDocumentoRepository(db_session)

    documento = repo.criar(
        Documento(
            id=None, empresa_id=empresa.id, nome_arquivo="20260727_abcd1234.pdf",
            nome_exibicao="comprovante.pdf", caminho_arquivo=f"empresa_{empresa.id}/documentos/x.pdf",
            extensao=".pdf", tamanho_bytes=1024,
        )
    )
    db_session.commit()

    pendentes = repo.listar_pendentes_por_empresa(empresa.id)
    assert len(pendentes) == 1

    documento.status = StatusDocumento.CONCLUIDO
    repo.atualizar(documento)
    db_session.commit()

    assert repo.listar_pendentes_por_empresa(empresa.id) == []
    assert len(repo.listar_por_empresa(empresa.id)) == 1


def test_criar_e_obter_ocr_resultado(db_session):
    empresa = _criar_empresa(db_session)
    doc_repo = SqlAlchemyDocumentoRepository(db_session)
    documento = doc_repo.criar(
        Documento(
            id=None, empresa_id=empresa.id, nome_arquivo="a.pdf", nome_exibicao="a.pdf",
            caminho_arquivo="x/a.pdf", extensao=".pdf", tamanho_bytes=10,
        )
    )
    db_session.commit()

    resultado_repo = SqlAlchemyOcrResultadoRepository(db_session)
    resultado_repo.criar(
        OcrResultado(
            id=None, documento_id=documento.id, texto_extraido="texto",
            metodo=MetodoOcr.PDF_NATIVO, tempo_processamento_ms=10,
        )
    )
    db_session.commit()

    encontrado = resultado_repo.obter_por_documento_id(documento.id)
    assert encontrado.texto_extraido == "texto"


def test_criar_e_atualizar_lote(db_session):
    empresa = _criar_empresa(db_session)
    repo = SqlAlchemyLoteProcessamentoRepository(db_session)

    lote = repo.criar(LoteProcessamento(id=None, empresa_id=empresa.id, total_documentos=3))
    db_session.commit()
    assert lote.status == StatusLote.EM_ANDAMENTO

    lote.documentos_processados = 3
    lote.status = StatusLote.CONCLUIDO
    repo.atualizar(lote)
    db_session.commit()

    atualizado = repo.obter_por_id(lote.id)
    assert atualizado.documentos_processados == 3
    assert atualizado.status == StatusLote.CONCLUIDO
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/integration/test_sqlalchemy_fase1_repositories.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write sqlalchemy_documento_repository.py**

`backend/app/infrastructure/repositories/sqlalchemy_documento_repository.py`:
```python
from sqlalchemy.orm import Session

from app.application.repositories import DocumentoRepository
from app.domain.entities import Documento
from app.domain.enums import StatusDocumento
from app.infrastructure.db.models import DocumentoModel


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
    )


class SqlAlchemyDocumentoRepository(DocumentoRepository):
    def __init__(self, session: Session):
        self._session = session

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
        )
        self._session.add(model)
        self._session.flush()
        return _to_entity(model)

    def obter_por_id(self, documento_id: int) -> Documento | None:
        model = self._session.get(DocumentoModel, documento_id)
        return _to_entity(model) if model else None

    def listar_por_empresa(self, empresa_id: int) -> list[Documento]:
        models = self._session.query(DocumentoModel).filter_by(empresa_id=empresa_id).all()
        return [_to_entity(m) for m in models]

    def listar_pendentes_por_empresa(self, empresa_id: int) -> list[Documento]:
        models = (
            self._session.query(DocumentoModel)
            .filter_by(empresa_id=empresa_id, status=StatusDocumento.PENDENTE.value)
            .all()
        )
        return [_to_entity(m) for m in models]

    def atualizar(self, documento: Documento) -> Documento:
        model = self._session.get(DocumentoModel, documento.id)
        model.status = documento.status.value
        model.mensagem_erro = documento.mensagem_erro
        model.nome_exibicao = documento.nome_exibicao
        self._session.flush()
        return _to_entity(model)
```

- [ ] **Step 4: Write sqlalchemy_ocr_resultado_repository.py**

`backend/app/infrastructure/repositories/sqlalchemy_ocr_resultado_repository.py`:
```python
from sqlalchemy.orm import Session

from app.application.repositories import OcrResultadoRepository
from app.domain.entities import OcrResultado
from app.domain.enums import MetodoOcr
from app.infrastructure.db.models import OcrResultadoModel


def _to_entity(model: OcrResultadoModel) -> OcrResultado:
    return OcrResultado(
        id=model.id,
        documento_id=model.documento_id,
        texto_extraido=model.texto_extraido,
        metodo=MetodoOcr(model.metodo),
        tempo_processamento_ms=model.tempo_processamento_ms,
        created_at=model.created_at,
    )


class SqlAlchemyOcrResultadoRepository(OcrResultadoRepository):
    def __init__(self, session: Session):
        self._session = session

    def criar(self, resultado: OcrResultado) -> OcrResultado:
        model = OcrResultadoModel(
            documento_id=resultado.documento_id,
            texto_extraido=resultado.texto_extraido,
            metodo=resultado.metodo.value,
            tempo_processamento_ms=resultado.tempo_processamento_ms,
        )
        self._session.add(model)
        self._session.flush()
        return _to_entity(model)

    def obter_por_documento_id(self, documento_id: int) -> OcrResultado | None:
        model = (
            self._session.query(OcrResultadoModel)
            .filter_by(documento_id=documento_id)
            .first()
        )
        return _to_entity(model) if model else None
```

- [ ] **Step 5: Write sqlalchemy_lote_processamento_repository.py**

`backend/app/infrastructure/repositories/sqlalchemy_lote_processamento_repository.py`:
```python
from sqlalchemy.orm import Session

from app.application.repositories import LoteProcessamentoRepository
from app.domain.entities import LoteProcessamento
from app.domain.enums import StatusLote
from app.infrastructure.db.models import LoteProcessamentoModel


def _to_entity(model: LoteProcessamentoModel) -> LoteProcessamento:
    return LoteProcessamento(
        id=model.id,
        empresa_id=model.empresa_id,
        total_documentos=model.total_documentos,
        documentos_processados=model.documentos_processados,
        status=StatusLote(model.status),
        created_at=model.created_at,
        concluido_em=model.concluido_em,
    )


class SqlAlchemyLoteProcessamentoRepository(LoteProcessamentoRepository):
    def __init__(self, session: Session):
        self._session = session

    def criar(self, lote: LoteProcessamento) -> LoteProcessamento:
        model = LoteProcessamentoModel(
            empresa_id=lote.empresa_id,
            total_documentos=lote.total_documentos,
            documentos_processados=lote.documentos_processados,
            status=lote.status.value,
        )
        self._session.add(model)
        self._session.flush()
        return _to_entity(model)

    def obter_por_id(self, lote_id: int) -> LoteProcessamento | None:
        model = self._session.get(LoteProcessamentoModel, lote_id)
        return _to_entity(model) if model else None

    def atualizar(self, lote: LoteProcessamento) -> LoteProcessamento:
        model = self._session.get(LoteProcessamentoModel, lote.id)
        model.documentos_processados = lote.documentos_processados
        model.status = lote.status.value
        model.concluido_em = lote.concluido_em
        self._session.flush()
        return _to_entity(model)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/integration/test_sqlalchemy_fase1_repositories.py -v`
Expected: PASS (3 passed)

- [ ] **Step 7: Run the full suite**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/infrastructure/repositories/sqlalchemy_documento_repository.py backend/app/infrastructure/repositories/sqlalchemy_ocr_resultado_repository.py backend/app/infrastructure/repositories/sqlalchemy_lote_processamento_repository.py backend/tests/integration/test_sqlalchemy_fase1_repositories.py
git commit -m "feat: add SQLAlchemy repositories for Documento/OcrResultado/LoteProcessamento"
```

---

### Task 6: Upload use case + Documento REST endpoints (upload, list, resultado)

**Files:**
- Modify: `backend/app/application/dto.py`
- Create: `backend/app/application/use_cases/documento_use_cases.py`
- Create: `backend/app/api/schemas/documento_schemas.py`
- Create: `backend/app/api/routers/documentos_router.py`
- Modify: `backend/app/api/deps.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/unit/test_documento_use_cases.py`
- Test: `backend/tests/integration/test_documentos_api.py`

**Interfaces:**
- Consumes: `DocumentoRepository` (Task 3), `ArmazenamentoArquivos` (Task 3), `EmpresaRepository` (Fase 0), `EmpresaNaoEncontrada`, `ArquivoInvalido`, `DocumentoNaoEncontrado` (Task 3), `OcrResultadoRepository` (Task 3).
- Produces: `ArquivoUploadDTO(nome_original: str, conteudo: bytes)`, `ResultadoUploadDTO(documento: Documento | None, nome_original: str, erro: str | None)` in `app.application.dto`. `UploadarDocumentosUseCase(documento_repo, empresa_repo, storage).executar(empresa_id, arquivos: list[ArquivoUploadDTO]) -> list[ResultadoUploadDTO]`, `ListarDocumentosUseCase(repo).executar(empresa_id) -> list[Documento]`, `ObterResultadoUseCase(documento_repo, resultado_repo).executar(documento_id) -> tuple[Documento, OcrResultado | None]`. Router mounted covering `/empresas/{empresa_id}/documentos` and `/documentos/{documento_id}/resultado`.

- [ ] **Step 1: Add DTOs**

Append to `backend/app/application/dto.py` (add `Documento` to the existing `from app.domain.entities import ...` import if one exists, otherwise add `from app.domain.entities import Documento` near the top):
```python
@dataclass
class ArquivoUploadDTO:
    nome_original: str
    conteudo: bytes


@dataclass
class ResultadoUploadDTO:
    documento: Documento | None
    nome_original: str
    erro: str | None
```

- [ ] **Step 2: Write the failing unit test**

`backend/tests/unit/test_documento_use_cases.py`:
```python
import pytest

from app.application.dto import ArquivoUploadDTO
from app.application.use_cases.documento_use_cases import (
    ListarDocumentosUseCase,
    ObterResultadoUseCase,
    UploadarDocumentosUseCase,
)
from app.core.exceptions import DocumentoNaoEncontrado, EmpresaNaoEncontrada
from app.domain.entities import Empresa
from tests.fakes import (
    FakeArmazenamentoArquivos,
    FakeDocumentoRepository,
    FakeEmpresaRepository,
    FakeOcrResultadoRepository,
)


def _empresa(repo):
    return repo.criar(Empresa(id=None, razao_social="A", nome_fantasia=None, cnpj="11111111000191"))


def test_upload_cria_documentos_para_arquivos_validos():
    empresa_repo = FakeEmpresaRepository()
    empresa = _empresa(empresa_repo)
    documento_repo = FakeDocumentoRepository()
    storage = FakeArmazenamentoArquivos()

    resultados = UploadarDocumentosUseCase(documento_repo, empresa_repo, storage).executar(
        empresa.id, [ArquivoUploadDTO(nome_original="comprovante.pdf", conteudo=b"conteudo")]
    )

    assert len(resultados) == 1
    assert resultados[0].erro is None
    assert resultados[0].documento.nome_exibicao == "comprovante.pdf"
    assert resultados[0].documento.status.value == "PENDENTE"


def test_upload_com_extensao_invalida_reporta_erro_sem_criar_documento():
    empresa_repo = FakeEmpresaRepository()
    empresa = _empresa(empresa_repo)
    documento_repo = FakeDocumentoRepository()
    storage = FakeArmazenamentoArquivos()

    resultados = UploadarDocumentosUseCase(documento_repo, empresa_repo, storage).executar(
        empresa.id, [ArquivoUploadDTO(nome_original="virus.exe", conteudo=b"x")]
    )

    assert resultados[0].documento is None
    assert resultados[0].erro is not None
    assert documento_repo.listar_por_empresa(empresa.id) == []


def test_upload_para_empresa_inexistente_falha():
    documento_repo = FakeDocumentoRepository()
    storage = FakeArmazenamentoArquivos()
    empresa_repo = FakeEmpresaRepository()

    with pytest.raises(EmpresaNaoEncontrada):
        UploadarDocumentosUseCase(documento_repo, empresa_repo, storage).executar(
            999, [ArquivoUploadDTO(nome_original="a.pdf", conteudo=b"x")]
        )


def test_listar_documentos_por_empresa():
    empresa_repo = FakeEmpresaRepository()
    empresa = _empresa(empresa_repo)
    documento_repo = FakeDocumentoRepository()
    storage = FakeArmazenamentoArquivos()
    UploadarDocumentosUseCase(documento_repo, empresa_repo, storage).executar(
        empresa.id, [ArquivoUploadDTO(nome_original="a.pdf", conteudo=b"x")]
    )

    documentos = ListarDocumentosUseCase(documento_repo).executar(empresa.id)

    assert len(documentos) == 1


def test_obter_resultado_documento_inexistente_falha():
    documento_repo = FakeDocumentoRepository()
    resultado_repo = FakeOcrResultadoRepository()

    with pytest.raises(DocumentoNaoEncontrado):
        ObterResultadoUseCase(documento_repo, resultado_repo).executar(999)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_documento_use_cases.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Write documento_use_cases.py**

`backend/app/application/use_cases/documento_use_cases.py`:
```python
from app.application.dto import ArquivoUploadDTO, ResultadoUploadDTO
from app.application.ports import ArmazenamentoArquivos
from app.application.repositories import (
    DocumentoRepository,
    EmpresaRepository,
    OcrResultadoRepository,
)
from app.core.exceptions import ArquivoInvalido, DocumentoNaoEncontrado, EmpresaNaoEncontrada
from app.domain.entities import Documento, OcrResultado


class UploadarDocumentosUseCase:
    def __init__(
        self,
        documento_repo: DocumentoRepository,
        empresa_repo: EmpresaRepository,
        storage: ArmazenamentoArquivos,
    ):
        self._documento_repo = documento_repo
        self._empresa_repo = empresa_repo
        self._storage = storage

    def executar(
        self, empresa_id: int, arquivos: list[ArquivoUploadDTO]
    ) -> list[ResultadoUploadDTO]:
        if self._empresa_repo.obter_por_id(empresa_id) is None:
            raise EmpresaNaoEncontrada(empresa_id)

        resultados: list[ResultadoUploadDTO] = []
        for arquivo in arquivos:
            try:
                nome_fisico, caminho_relativo, extensao = self._storage.salvar(
                    empresa_id, arquivo.nome_original, arquivo.conteudo
                )
            except ArquivoInvalido as exc:
                resultados.append(
                    ResultadoUploadDTO(documento=None, nome_original=arquivo.nome_original, erro=str(exc))
                )
                continue

            documento = Documento(
                id=None,
                empresa_id=empresa_id,
                nome_arquivo=nome_fisico,
                nome_exibicao=arquivo.nome_original,
                caminho_arquivo=caminho_relativo,
                extensao=extensao,
                tamanho_bytes=len(arquivo.conteudo),
            )
            criado = self._documento_repo.criar(documento)
            resultados.append(
                ResultadoUploadDTO(documento=criado, nome_original=arquivo.nome_original, erro=None)
            )
        return resultados


class ListarDocumentosUseCase:
    def __init__(self, repo: DocumentoRepository):
        self._repo = repo

    def executar(self, empresa_id: int) -> list[Documento]:
        return self._repo.listar_por_empresa(empresa_id)


class ObterResultadoUseCase:
    def __init__(self, documento_repo: DocumentoRepository, resultado_repo: OcrResultadoRepository):
        self._documento_repo = documento_repo
        self._resultado_repo = resultado_repo

    def executar(self, documento_id: int) -> tuple[Documento, OcrResultado | None]:
        documento = self._documento_repo.obter_por_id(documento_id)
        if documento is None:
            raise DocumentoNaoEncontrado(documento_id)
        resultado = self._resultado_repo.obter_por_documento_id(documento_id)
        return documento, resultado
```

`backend/app/application/use_cases/__init__.py` already exists from Fase 0.

- [ ] **Step 5: Run unit test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/unit/test_documento_use_cases.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: Write documento_schemas.py**

`backend/app/api/schemas/documento_schemas.py`:
```python
from datetime import datetime

from pydantic import BaseModel

from app.domain.enums import MetodoOcr, StatusDocumento


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

    model_config = {"from_attributes": True}


class UploadItemOut(BaseModel):
    nome_original: str
    documento: DocumentoOut | None
    erro: str | None


class OcrResultadoOut(BaseModel):
    texto_extraido: str
    metodo: MetodoOcr
    tempo_processamento_ms: int


class DocumentoResultadoOut(BaseModel):
    documento: DocumentoOut
    resultado: OcrResultadoOut | None
```

- [ ] **Step 7: Add STORAGE_ROOT to config and a get_storage dependency**

Add to `backend/app/core/config.py`'s `Settings` class (inside the class body, alongside `database_url`):
```python
    storage_root: str = "./storage"
```

Append to `backend/app/api/deps.py`:
```python
from pathlib import Path

from app.core.config import settings
from app.infrastructure.storage.file_storage import LocalFileStorageService


def get_storage() -> LocalFileStorageService:
    return LocalFileStorageService(Path(settings.storage_root))
```

- [ ] **Step 8: Write the failing integration test**

`backend/tests/integration/test_documentos_api.py`:
```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db, get_storage
from app.infrastructure.db.base import Base
from app.infrastructure.db import models  # noqa: F401
from app.infrastructure.storage.file_storage import LocalFileStorageService
from app.main import app


@pytest.fixture
def client(tmp_path):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine)

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
```

- [ ] **Step 9: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/integration/test_documentos_api.py -v`
Expected: FAIL (404 — router not registered yet).

- [ ] **Step 10: Write documentos_router.py**

`backend/app/api/routers/documentos_router.py`:
```python
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_storage
from app.api.schemas.documento_schemas import (
    DocumentoResultadoOut,
    OcrResultadoOut,
    UploadItemOut,
)
from app.application.dto import ArquivoUploadDTO
from app.application.use_cases.documento_use_cases import (
    ListarDocumentosUseCase,
    ObterResultadoUseCase,
    UploadarDocumentosUseCase,
)
from app.core.exceptions import DocumentoNaoEncontrado, EmpresaNaoEncontrada
from app.infrastructure.repositories.sqlalchemy_documento_repository import (
    SqlAlchemyDocumentoRepository,
)
from app.infrastructure.repositories.sqlalchemy_empresa_repository import (
    SqlAlchemyEmpresaRepository,
)
from app.infrastructure.repositories.sqlalchemy_ocr_resultado_repository import (
    SqlAlchemyOcrResultadoRepository,
)
from app.infrastructure.storage.file_storage import LocalFileStorageService

router = APIRouter(tags=["documentos"])


@router.post(
    "/empresas/{empresa_id}/documentos", response_model=list[UploadItemOut], status_code=201
)
async def upload_documentos(
    empresa_id: int,
    arquivos: list[UploadFile],
    db: Session = Depends(get_db),
    storage: LocalFileStorageService = Depends(get_storage),
):
    documento_repo = SqlAlchemyDocumentoRepository(db)
    empresa_repo = SqlAlchemyEmpresaRepository(db)
    dtos = [
        ArquivoUploadDTO(nome_original=arquivo.filename or "arquivo", conteudo=await arquivo.read())
        for arquivo in arquivos
    ]
    try:
        return UploadarDocumentosUseCase(documento_repo, empresa_repo, storage).executar(
            empresa_id, dtos
        )
    except EmpresaNaoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/empresas/{empresa_id}/documentos")
def listar_documentos(empresa_id: int, db: Session = Depends(get_db)):
    repo = SqlAlchemyDocumentoRepository(db)
    return ListarDocumentosUseCase(repo).executar(empresa_id)


@router.get("/documentos/{documento_id}/resultado", response_model=DocumentoResultadoOut)
def obter_resultado(documento_id: int, db: Session = Depends(get_db)):
    documento_repo = SqlAlchemyDocumentoRepository(db)
    resultado_repo = SqlAlchemyOcrResultadoRepository(db)
    try:
        documento, resultado = ObterResultadoUseCase(documento_repo, resultado_repo).executar(
            documento_id
        )
    except DocumentoNaoEncontrado as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    resultado_out = (
        OcrResultadoOut(
            texto_extraido=resultado.texto_extraido,
            metodo=resultado.metodo,
            tempo_processamento_ms=resultado.tempo_processamento_ms,
        )
        if resultado
        else None
    )
    return DocumentoResultadoOut(documento=documento, resultado=resultado_out)
```

Note: `GET /empresas/{empresa_id}/documentos`'s response is typed loosely (no `response_model`) here because FastAPI/Pydantic will otherwise try to serialize domain `Documento` dataclasses directly; add `response_model=list[DocumentoOut]` and confirm it still passes — if Pydantic can't coerce the dataclass directly, wrap the return with `[DocumentoOut.model_validate(d, from_attributes=True) for d in ...]` in the route function instead. Verify against the actual test run in Step 9/11, don't guess which is needed.

- [ ] **Step 11: Register the router in main.py**

Add to `backend/app/main.py`'s imports and `include_router` calls:
```python
from app.api.routers.documentos_router import router as documentos_router
```
and
```python
app.include_router(documentos_router)
```

- [ ] **Step 12: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/integration/test_documentos_api.py -v`
Expected: PASS (4 passed). If the list endpoint fails to serialize, apply the fix noted in Step 10 and re-run.

- [ ] **Step 13: Run the full suite**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all pass.

- [ ] **Step 14: Commit**

```bash
git add backend/app/application/dto.py backend/app/application/use_cases/documento_use_cases.py backend/app/api backend/app/main.py backend/app/core/config.py backend/tests/unit/test_documento_use_cases.py backend/tests/integration/test_documentos_api.py
git commit -m "feat: add document upload/list/resultado use cases and REST endpoints"
```

---

### Task 7: PDF native text extraction

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/app/infrastructure/ocr/__init__.py`
- Create: `backend/app/infrastructure/ocr/pdf_nativo.py`
- Test: `backend/tests/unit/test_pdf_nativo.py`

**Interfaces:**
- Produces: `TAMANHO_MINIMO_TEXTO: int`, `extrair_texto_nativo(conteudo_pdf: bytes) -> str | None` (returns `None` if the PDF has no meaningfully-searchable text, meaning it's likely scanned).

- [ ] **Step 1: Add pypdf and PyMuPDF to requirements**

Append to `backend/requirements.txt`:
```
pypdf==5.0.1
pymupdf==1.24.11
```

Install: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/pip install pypdf==5.0.1 pymupdf==1.24.11`

- [ ] **Step 2: Write the failing test**

`backend/tests/unit/test_pdf_nativo.py`:
```python
import fitz  # PyMuPDF, used here only to build test fixtures

from app.infrastructure.ocr.pdf_nativo import extrair_texto_nativo


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


def test_extrai_texto_de_pdf_com_texto_pesquisavel():
    conteudo = _pdf_com_texto("COMPROVANTE DE PAGAMENTO - VALOR R$ 150,00")

    texto = extrair_texto_nativo(conteudo)

    assert texto is not None
    assert "COMPROVANTE" in texto


def test_retorna_none_para_pdf_sem_texto_pesquisavel():
    conteudo = _pdf_vazio()

    texto = extrair_texto_nativo(conteudo)

    assert texto is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_pdf_nativo.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Write pdf_nativo.py**

`backend/app/infrastructure/ocr/pdf_nativo.py`:
```python
import io

from pypdf import PdfReader

TAMANHO_MINIMO_TEXTO = 20


def extrair_texto_nativo(conteudo_pdf: bytes) -> str | None:
    leitor = PdfReader(io.BytesIO(conteudo_pdf))
    texto = "\n".join(pagina.extract_text() or "" for pagina in leitor.pages).strip()
    if len(texto) < TAMANHO_MINIMO_TEXTO:
        return None
    return texto
```

`backend/app/infrastructure/ocr/__init__.py`: empty file.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/unit/test_pdf_nativo.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/app/infrastructure/ocr backend/tests/unit/test_pdf_nativo.py
git commit -m "feat: add native PDF text extraction (pypdf)"
```

---

### Task 8: PDF page rendering (for scanned PDFs headed to OCR)

**Files:**
- Create: `backend/app/infrastructure/ocr/renderizador_pdf.py`
- Test: `backend/tests/unit/test_renderizador_pdf.py`

**Interfaces:**
- Consumes: `fitz` (PyMuPDF, already installed in Task 7).
- Produces: `renderizar_paginas_pdf(conteudo_pdf: bytes, dpi: int = 200) -> list[bytes]` (PNG bytes per page).

- [ ] **Step 1: Write the failing test**

`backend/tests/unit/test_renderizador_pdf.py`:
```python
import io

import fitz
from PIL import Image

from app.infrastructure.ocr.renderizador_pdf import renderizar_paginas_pdf


def _pdf_com_n_paginas(n: int) -> bytes:
    documento = fitz.open()
    for _ in range(n):
        documento.new_page()
    conteudo = documento.tobytes()
    documento.close()
    return conteudo


def test_renderiza_uma_imagem_por_pagina():
    conteudo = _pdf_com_n_paginas(2)

    imagens = renderizar_paginas_pdf(conteudo)

    assert len(imagens) == 2
    for imagem_bytes in imagens:
        imagem = Image.open(io.BytesIO(imagem_bytes))
        assert imagem.format == "PNG"
        assert imagem.width > 0 and imagem.height > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_renderizador_pdf.py -v`
Expected: FAIL with `ModuleNotFoundError`. (`Pillow` is already a transitive dependency of `pymupdf`/other libs, but add it explicitly for clarity — append `pillow==10.4.0` to `backend/requirements.txt` and run `.venv/Scripts/pip install pillow==10.4.0` if `import PIL` fails.)

- [ ] **Step 3: Write renderizador_pdf.py**

`backend/app/infrastructure/ocr/renderizador_pdf.py`:
```python
import fitz


def renderizar_paginas_pdf(conteudo_pdf: bytes, dpi: int = 200) -> list[bytes]:
    documento = fitz.open(stream=conteudo_pdf, filetype="pdf")
    zoom = dpi / 72
    matriz = fitz.Matrix(zoom, zoom)
    imagens = [pagina.get_pixmap(matrix=matriz).tobytes("png") for pagina in documento]
    documento.close()
    return imagens
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/unit/test_renderizador_pdf.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/ocr/renderizador_pdf.py backend/tests/unit/test_renderizador_pdf.py backend/requirements.txt
git commit -m "feat: add PDF page-to-image rendering for OCR"
```

---

### Task 9: Tesseract OCR engine

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/app/infrastructure/ocr/tesseract_engine.py`
- Test: `backend/tests/unit/test_tesseract_engine.py`

**Interfaces:**
- Consumes: `OcrEngine` (Task 3).
- Produces: `TesseractIndisponivel` exception. `TesseractOcrEngine()` implementing `OcrEngine.extrair_texto(imagem_bytes: bytes) -> str`.

**Prerequisite (documented, not automated by this task):** the Tesseract binary must be installed separately and on `PATH` for this engine to actually run — e.g. via the official Windows installer (UB Mannheim build) or `winget install --id UB-Mannheim.TesseractOCR`. This task's tests must not require the binary to be present (they skip cleanly if it's missing), since CI/dev machines may not have it installed yet.

- [ ] **Step 1: Add pytesseract to requirements**

Append to `backend/requirements.txt`:
```
pytesseract==0.3.13
```

Install: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/pip install pytesseract==0.3.13`

- [ ] **Step 2: Write the failing test (skips cleanly if Tesseract binary isn't installed)**

`backend/tests/unit/test_tesseract_engine.py`:
```python
import io
import shutil

import pytest
from PIL import Image, ImageDraw

from app.infrastructure.ocr.tesseract_engine import TesseractIndisponivel, TesseractOcrEngine

pytestmark = pytest.mark.skipif(
    shutil.which("tesseract") is None,
    reason="Tesseract binary not installed on this machine",
)


def _imagem_com_texto(texto: str) -> bytes:
    imagem = Image.new("RGB", (400, 100), color="white")
    desenho = ImageDraw.Draw(imagem)
    desenho.text((10, 40), texto, fill="black")
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    return buffer.getvalue()


def test_extrai_texto_de_imagem():
    engine = TesseractOcrEngine()
    imagem_bytes = _imagem_com_texto("TESTE OCR")

    texto = engine.extrair_texto(imagem_bytes)

    assert "TESTE" in texto.upper() or "OCR" in texto.upper()


def test_engine_indisponivel_levanta_excecao(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)

    with pytest.raises(TesseractIndisponivel):
        TesseractOcrEngine()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_tesseract_engine.py -v`
Expected: FAIL with `ModuleNotFoundError` (both tests error before the skip logic can apply, since the module itself doesn't exist yet).

- [ ] **Step 4: Write tesseract_engine.py**

`backend/app/infrastructure/ocr/tesseract_engine.py`:
```python
import io
import shutil

import pytesseract
from PIL import Image

from app.application.ports import OcrEngine
from app.core.exceptions import DomainError


class TesseractIndisponivel(DomainError):
    def __init__(self):
        super().__init__("Executável 'tesseract' não encontrado no PATH.")


class TesseractOcrEngine(OcrEngine):
    def __init__(self):
        if shutil.which("tesseract") is None:
            raise TesseractIndisponivel()

    def extrair_texto(self, imagem_bytes: bytes) -> str:
        imagem = Image.open(io.BytesIO(imagem_bytes))
        return pytesseract.image_to_string(imagem, lang="por").strip()
```

- [ ] **Step 5: Run test to verify it passes (or skips)**

Run: `.venv/Scripts/python -m pytest tests/unit/test_tesseract_engine.py -v`
Expected: if Tesseract is installed, PASS (2 passed); if not, `test_extrai_texto_de_imagem` is SKIPPED and `test_engine_indisponivel_levanta_excecao` PASSES (this second test doesn't need the real binary — it monkeypatches `shutil.which` to simulate absence, so it must pass unconditionally).

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/app/infrastructure/ocr/tesseract_engine.py backend/tests/unit/test_tesseract_engine.py
git commit -m "feat: add Tesseract OCR engine with graceful unavailability handling"
```

---

### Task 10: PaddleOCR engine

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/app/infrastructure/ocr/paddle_engine.py`
- Test: `backend/tests/unit/test_paddle_engine.py`

**Interfaces:**
- Consumes: `OcrEngine` (Task 3).
- Produces: `PaddleOcrEngine()` implementing `OcrEngine.extrair_texto(imagem_bytes: bytes) -> str`.

**Note on install weight:** `paddleocr`/`paddlepaddle` are large downloads (100s of MB) and the first `PaddleOCR(...)` instantiation downloads detection/recognition models from the network on first use. This task's automated tests must not depend on that succeeding (they skip cleanly if the import fails), but a real end-to-end check happens in the final task's manual verification.

- [ ] **Step 1: Add paddleocr to requirements**

Append to `backend/requirements.txt`:
```
paddlepaddle==2.6.2
paddleocr==2.9.1
```

Install: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/pip install paddlepaddle==2.6.2 paddleocr==2.9.1`

If this install fails on the current machine (e.g. no matching wheel for the installed Python version), note the failure in your task report but continue — the test in Step 2 is written to skip cleanly via `pytest.importorskip`, so the rest of this plan is not blocked by PaddleOCR being uninstallable in this particular environment. Do not spend more than one troubleshooting attempt on it (e.g. trying a different pinned version); if it doesn't install cleanly, report `DONE_WITH_CONCERNS` and move on.

- [ ] **Step 2: Write the failing test (skips cleanly if paddleocr isn't importable)**

`backend/tests/unit/test_paddle_engine.py`:
```python
import io

import pytest
from PIL import Image, ImageDraw

pytest.importorskip("paddleocr")

from app.infrastructure.ocr.paddle_engine import PaddleOcrEngine  # noqa: E402


def _imagem_com_texto(texto: str) -> bytes:
    imagem = Image.new("RGB", (400, 100), color="white")
    desenho = ImageDraw.Draw(imagem)
    desenho.text((10, 40), texto, fill="black")
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    return buffer.getvalue()


def test_extrai_texto_de_imagem():
    engine = PaddleOcrEngine()
    imagem_bytes = _imagem_com_texto("TESTE OCR")

    texto = engine.extrair_texto(imagem_bytes)

    assert isinstance(texto, str)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_paddle_engine.py -v`
Expected: FAIL with `ModuleNotFoundError` for `app.infrastructure.ocr.paddle_engine` (or SKIPPED if `paddleocr` itself isn't installed — either is acceptable evidence the test file is wired correctly at this stage; if skipped, still proceed to Step 4 and re-check in Step 5).

- [ ] **Step 4: Write paddle_engine.py**

`backend/app/infrastructure/ocr/paddle_engine.py`:
```python
import io

import numpy as np
from PIL import Image

from app.application.ports import OcrEngine


class PaddleOcrEngine(OcrEngine):
    def __init__(self):
        from paddleocr import PaddleOCR

        self._ocr = PaddleOCR(use_angle_cls=True, lang="pt", show_log=False)

    def extrair_texto(self, imagem_bytes: bytes) -> str:
        imagem = Image.open(io.BytesIO(imagem_bytes)).convert("RGB")
        resultado = self._ocr.ocr(np.array(imagem), cls=True)

        linhas = []
        for bloco in resultado or []:
            for _caixa, (texto, _confianca) in bloco:
                linhas.append(texto)
        return "\n".join(linhas).strip()
```

- [ ] **Step 5: Run test to verify it passes (or skips)**

Run: `.venv/Scripts/python -m pytest tests/unit/test_paddle_engine.py -v`
Expected: PASS if `paddleocr` installed successfully and can download its models; SKIPPED (via `importorskip`) if the package itself isn't importable. Either outcome is acceptable for this task — do not treat a SKIP as a failure to fix.

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/app/infrastructure/ocr/paddle_engine.py backend/tests/unit/test_paddle_engine.py
git commit -m "feat: add PaddleOCR engine"
```

---

### Task 11: OCR pipeline orchestrator (native → PaddleOCR → Tesseract)

**Files:**
- Create: `backend/app/infrastructure/ocr/pipeline.py`
- Test: `backend/tests/unit/test_ocr_pipeline.py`

**Interfaces:**
- Consumes: `extrair_texto_nativo` (Task 7), `renderizar_paginas_pdf` (Task 8), `MetodoOcr` (Task 2).
- Produces: `ResultadoPipelineOcr(texto: str, metodo: MetodoOcr, tempo_processamento_ms: int, erro: str | None = None)` dataclass. `processar_documento(conteudo: bytes, extensao: str) -> ResultadoPipelineOcr` — a plain, picklable module-level function (required so `ProcessPoolExecutor` can call it from a worker process in Task 12).

- [ ] **Step 1: Write the failing test**

`backend/tests/unit/test_ocr_pipeline.py`:
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
    assert "COMPROVANTE" in resultado.texto
    assert resultado.erro is None


def test_pdf_escaneado_usa_paddleocr_quando_disponivel():
    conteudo = _pdf_vazio()

    with patch("app.infrastructure.ocr.pipeline.renderizar_paginas_pdf", return_value=[b"fake-imagem"]), \
         patch("app.infrastructure.ocr.paddle_engine.PaddleOcrEngine") as MockPaddle:
        MockPaddle.return_value.extrair_texto.return_value = "texto via paddle"

        resultado = processar_documento(conteudo, ".pdf")

    assert resultado.metodo == MetodoOcr.PADDLEOCR
    assert resultado.texto == "texto via paddle"
    assert resultado.erro is None


def test_pdf_escaneado_cai_para_tesseract_quando_paddle_falha():
    conteudo = _pdf_vazio()

    with patch("app.infrastructure.ocr.pipeline.renderizar_paginas_pdf", return_value=[b"fake-imagem"]), \
         patch("app.infrastructure.ocr.paddle_engine.PaddleOcrEngine", side_effect=RuntimeError("sem modelo")), \
         patch("app.infrastructure.ocr.tesseract_engine.TesseractOcrEngine") as MockTesseract:
        MockTesseract.return_value.extrair_texto.return_value = "texto via tesseract"

        resultado = processar_documento(conteudo, ".pdf")

    assert resultado.metodo == MetodoOcr.TESSERACT
    assert resultado.texto == "texto via tesseract"
    assert resultado.erro is None


def test_imagem_direta_pula_extracao_nativa_e_vai_para_ocr():
    conteudo = b"fake-imagem-bytes"

    with patch("app.infrastructure.ocr.paddle_engine.PaddleOcrEngine") as MockPaddle:
        MockPaddle.return_value.extrair_texto.return_value = "texto de imagem"

        resultado = processar_documento(conteudo, ".png")

    assert resultado.metodo == MetodoOcr.PADDLEOCR
    assert resultado.texto == "texto de imagem"


def test_ambos_engines_falham_retorna_resultado_com_erro():
    conteudo = _pdf_vazio()

    with patch("app.infrastructure.ocr.pipeline.renderizar_paginas_pdf", return_value=[b"fake-imagem"]), \
         patch("app.infrastructure.ocr.paddle_engine.PaddleOcrEngine", side_effect=RuntimeError("sem modelo")), \
         patch("app.infrastructure.ocr.tesseract_engine.TesseractOcrEngine", side_effect=RuntimeError("sem binario")):
        resultado = processar_documento(conteudo, ".pdf")

    assert resultado.erro is not None
    assert resultado.texto == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_ocr_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write pipeline.py**

`backend/app/infrastructure/ocr/pipeline.py`:
```python
import time
from dataclasses import dataclass

from app.domain.enums import MetodoOcr
from app.infrastructure.ocr.pdf_nativo import extrair_texto_nativo
from app.infrastructure.ocr.renderizador_pdf import renderizar_paginas_pdf


@dataclass
class ResultadoPipelineOcr:
    texto: str
    metodo: MetodoOcr
    tempo_processamento_ms: int
    erro: str | None = None


def _executar_engine_em_imagens(engine, imagens: list[bytes]) -> str:
    return "\n".join(engine.extrair_texto(imagem) for imagem in imagens).strip()


def processar_documento(conteudo: bytes, extensao: str) -> ResultadoPipelineOcr:
    inicio = time.monotonic()

    if extensao == ".pdf":
        texto_nativo = extrair_texto_nativo(conteudo)
        if texto_nativo is not None:
            tempo_ms = int((time.monotonic() - inicio) * 1000)
            return ResultadoPipelineOcr(
                texto=texto_nativo, metodo=MetodoOcr.PDF_NATIVO, tempo_processamento_ms=tempo_ms
            )
        imagens = renderizar_paginas_pdf(conteudo)
    else:
        imagens = [conteudo]

    erro_paddle: str | None = None
    try:
        from app.infrastructure.ocr.paddle_engine import PaddleOcrEngine

        texto = _executar_engine_em_imagens(PaddleOcrEngine(), imagens)
        if texto:
            tempo_ms = int((time.monotonic() - inicio) * 1000)
            return ResultadoPipelineOcr(
                texto=texto, metodo=MetodoOcr.PADDLEOCR, tempo_processamento_ms=tempo_ms
            )
        erro_paddle = "PaddleOCR não reconheceu texto."
    except Exception as exc:
        erro_paddle = str(exc)

    try:
        from app.infrastructure.ocr.tesseract_engine import TesseractOcrEngine

        texto = _executar_engine_em_imagens(TesseractOcrEngine(), imagens)
        tempo_ms = int((time.monotonic() - inicio) * 1000)
        if texto:
            return ResultadoPipelineOcr(
                texto=texto, metodo=MetodoOcr.TESSERACT, tempo_processamento_ms=tempo_ms
            )
        return ResultadoPipelineOcr(
            texto="", metodo=MetodoOcr.TESSERACT, tempo_processamento_ms=tempo_ms,
            erro=f"Nenhum engine de OCR reconheceu texto (PaddleOCR: {erro_paddle}).",
        )
    except Exception as exc:
        tempo_ms = int((time.monotonic() - inicio) * 1000)
        return ResultadoPipelineOcr(
            texto="", metodo=MetodoOcr.TESSERACT, tempo_processamento_ms=tempo_ms,
            erro=f"PaddleOCR: {erro_paddle}; Tesseract: {exc}",
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/unit/test_ocr_pipeline.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/ocr/pipeline.py backend/tests/unit/test_ocr_pipeline.py
git commit -m "feat: add OCR pipeline orchestrator (native -> PaddleOCR -> Tesseract)"
```

---

### Task 12: Lote use cases (iniciar processamento, status, cancelar) + background worker

**Files:**
- Create: `backend/app/application/use_cases/lote_use_cases.py`
- Modify: `backend/app/application/dto.py`
- Test: `backend/tests/unit/test_lote_use_cases.py`

**Interfaces:**
- Consumes: `LoteProcessamentoRepository`, `DocumentoRepository`, `OcrResultadoRepository`, `EmpresaRepository` (existing/Task 3), `LoteNaoEncontrado`, `EmpresaNaoEncontrada` (Task 3), `processar_documento` (Task 11).
- Produces: `IniciarProcessamentoUseCase(documento_repo, lote_repo, empresa_repo).executar(empresa_id) -> LoteProcessamento` (creates the batch row; does NOT run OCR itself — see note below). `ObterStatusLoteUseCase(repo).executar(lote_id) -> LoteProcessamento`. `CancelarLoteUseCase(repo).executar(lote_id) -> LoteProcessamento`. `processar_lote_em_background(lote_id: int, documento_ids: list[int], storage_root: str) -> None` — the function driving actual OCR execution across a `ProcessPoolExecutor`, called from the API layer as a FastAPI `BackgroundTask` in Task 13 (kept in this task's file since it's tightly coupled to the use cases it calls, but it builds its own DB session rather than depending on FastAPI's request-scoped one, since it runs after the HTTP response returns).

**Design note on why `IniciarProcessamentoUseCase` doesn't run OCR inline:** creating the `LoteProcessamento` row (fast, synchronous) is what the API needs to return `lote_id` to the caller immediately for polling; the actual OCR work happens in `processar_lote_em_background`, dispatched as a FastAPI background task by the router in Task 13. This split is why `IniciarProcessamentoUseCase` and `processar_lote_em_background` are separate: the former is a normal request-scoped use case (testable with fakes), the latter manages its own session lifecycle and a process pool (tested at the integration level in Task 13, not unit-tested with fakes, since `ProcessPoolExecutor` needs real picklable functions).

- [ ] **Step 1: Add DTOs if needed**

No new DTOs required for this task — `IniciarProcessamentoUseCase.executar` takes a plain `empresa_id: int`.

- [ ] **Step 2: Write the failing test**

`backend/tests/unit/test_lote_use_cases.py`:
```python
import pytest

from app.application.use_cases.lote_use_cases import (
    CancelarLoteUseCase,
    IniciarProcessamentoUseCase,
    ObterStatusLoteUseCase,
)
from app.core.exceptions import EmpresaNaoEncontrada, LoteNaoEncontrado
from app.domain.entities import Documento, Empresa
from app.domain.enums import StatusLote
from tests.fakes import FakeDocumentoRepository, FakeEmpresaRepository, FakeLoteProcessamentoRepository


def _empresa(repo):
    return repo.criar(Empresa(id=None, razao_social="A", nome_fantasia=None, cnpj="11111111000191"))


def _documento_pendente(repo, empresa_id):
    return repo.criar(
        Documento(
            id=None, empresa_id=empresa_id, nome_arquivo="a.pdf", nome_exibicao="a.pdf",
            caminho_arquivo="x/a.pdf", extensao=".pdf", tamanho_bytes=10,
        )
    )


def test_iniciar_processamento_cria_lote_com_total_de_documentos_pendentes():
    empresa_repo = FakeEmpresaRepository()
    empresa = _empresa(empresa_repo)
    documento_repo = FakeDocumentoRepository()
    _documento_pendente(documento_repo, empresa.id)
    _documento_pendente(documento_repo, empresa.id)
    lote_repo = FakeLoteProcessamentoRepository()

    lote = IniciarProcessamentoUseCase(documento_repo, lote_repo, empresa_repo).executar(empresa.id)

    assert lote.total_documentos == 2
    assert lote.status == StatusLote.EM_ANDAMENTO


def test_iniciar_processamento_empresa_inexistente_falha():
    documento_repo = FakeDocumentoRepository()
    lote_repo = FakeLoteProcessamentoRepository()
    empresa_repo = FakeEmpresaRepository()

    with pytest.raises(EmpresaNaoEncontrada):
        IniciarProcessamentoUseCase(documento_repo, lote_repo, empresa_repo).executar(999)


def test_obter_status_lote_inexistente_falha():
    lote_repo = FakeLoteProcessamentoRepository()

    with pytest.raises(LoteNaoEncontrado):
        ObterStatusLoteUseCase(lote_repo).executar(999)


def test_cancelar_lote_muda_status_para_cancelado():
    empresa_repo = FakeEmpresaRepository()
    empresa = _empresa(empresa_repo)
    documento_repo = FakeDocumentoRepository()
    _documento_pendente(documento_repo, empresa.id)
    lote_repo = FakeLoteProcessamentoRepository()
    lote = IniciarProcessamentoUseCase(documento_repo, lote_repo, empresa_repo).executar(empresa.id)

    cancelado = CancelarLoteUseCase(lote_repo).executar(lote.id)

    assert cancelado.status == StatusLote.CANCELADO
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_lote_use_cases.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Write lote_use_cases.py**

`backend/app/application/use_cases/lote_use_cases.py`:
```python
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from app.application.repositories import (
    DocumentoRepository,
    EmpresaRepository,
    LoteProcessamentoRepository,
    OcrResultadoRepository,
)
from app.core.exceptions import EmpresaNaoEncontrada, LoteNaoEncontrado
from app.domain.entities import LoteProcessamento, OcrResultado
from app.domain.enums import StatusDocumento, StatusLote
from app.infrastructure.ocr.pipeline import processar_documento


class IniciarProcessamentoUseCase:
    def __init__(
        self,
        documento_repo: DocumentoRepository,
        lote_repo: LoteProcessamentoRepository,
        empresa_repo: EmpresaRepository,
    ):
        self._documento_repo = documento_repo
        self._lote_repo = lote_repo
        self._empresa_repo = empresa_repo

    def executar(self, empresa_id: int) -> LoteProcessamento:
        if self._empresa_repo.obter_por_id(empresa_id) is None:
            raise EmpresaNaoEncontrada(empresa_id)

        pendentes = self._documento_repo.listar_pendentes_por_empresa(empresa_id)
        lote = LoteProcessamento(id=None, empresa_id=empresa_id, total_documentos=len(pendentes))
        return self._lote_repo.criar(lote)


class ObterStatusLoteUseCase:
    def __init__(self, repo: LoteProcessamentoRepository):
        self._repo = repo

    def executar(self, lote_id: int) -> LoteProcessamento:
        lote = self._repo.obter_por_id(lote_id)
        if lote is None:
            raise LoteNaoEncontrado(lote_id)
        return lote


class CancelarLoteUseCase:
    def __init__(self, repo: LoteProcessamentoRepository):
        self._repo = repo

    def executar(self, lote_id: int) -> LoteProcessamento:
        lote = ObterStatusLoteUseCase(self._repo).executar(lote_id)
        lote.status = StatusLote.CANCELADO
        return self._repo.atualizar(lote)


def processar_lote_em_background(lote_id: int, documento_ids: list[int], storage_root: str) -> None:
    """Runs after the HTTP response returns. Builds its own DB session and file
    storage instance since it's no longer inside a request scope. Submits each
    document's OCR work to a process pool, updating progress after each result,
    and stops submitting new work once the batch is marked CANCELADO."""
    from app.infrastructure.db.session import SessionLocal
    from app.infrastructure.repositories.sqlalchemy_documento_repository import (
        SqlAlchemyDocumentoRepository,
    )
    from app.infrastructure.repositories.sqlalchemy_lote_processamento_repository import (
        SqlAlchemyLoteProcessamentoRepository,
    )
    from app.infrastructure.repositories.sqlalchemy_ocr_resultado_repository import (
        SqlAlchemyOcrResultadoRepository,
    )
    from app.infrastructure.storage.file_storage import LocalFileStorageService

    session = SessionLocal()
    try:
        documento_repo = SqlAlchemyDocumentoRepository(session)
        resultado_repo = SqlAlchemyOcrResultadoRepository(session)
        lote_repo = SqlAlchemyLoteProcessamentoRepository(session)
        storage = LocalFileStorageService(Path(storage_root))

        with ProcessPoolExecutor() as pool:
            futuros = {}
            for documento_id in documento_ids:
                lote_atual = lote_repo.obter_por_id(lote_id)
                if lote_atual is None or lote_atual.status == StatusLote.CANCELADO:
                    break
                documento = documento_repo.obter_por_id(documento_id)
                conteudo = storage.ler(documento.caminho_arquivo)
                futuro = pool.submit(processar_documento, conteudo, documento.extensao)
                futuros[futuro] = documento_id

            for futuro in as_completed(futuros):
                documento_id = futuros[futuro]
                documento = documento_repo.obter_por_id(documento_id)
                resultado_pipeline = futuro.result()

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
                documento_repo.atualizar(documento)

                lote_atual = lote_repo.obter_por_id(lote_id)
                lote_atual.documentos_processados += 1
                lote_repo.atualizar(lote_atual)
                session.commit()

        lote_final = lote_repo.obter_por_id(lote_id)
        if lote_final.status != StatusLote.CANCELADO:
            lote_final.status = StatusLote.CONCLUIDO
            lote_final.concluido_em = datetime.now(timezone.utc)
            lote_repo.atualizar(lote_final)
            session.commit()
    finally:
        session.close()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/unit/test_lote_use_cases.py -v`
Expected: PASS (4 passed) — note `processar_lote_em_background` is not exercised by this unit test (it needs real DB/storage/process-pool wiring); it's covered by the integration test in Task 13.

- [ ] **Step 6: Run the full suite**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/application/use_cases/lote_use_cases.py backend/tests/unit/test_lote_use_cases.py
git commit -m "feat: add lote (batch) use cases and background OCR worker"
```

---

### Task 13: Lote REST endpoints (processar, status, cancelar)

**Files:**
- Create: `backend/app/api/schemas/lote_schemas.py`
- Create: `backend/app/api/routers/lotes_router.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/integration/test_lotes_api.py`

**Interfaces:**
- Consumes: `IniciarProcessamentoUseCase`, `ObterStatusLoteUseCase`, `CancelarLoteUseCase`, `processar_lote_em_background` (Task 12).
- Produces: `POST /empresas/{empresa_id}/documentos/processar` (returns `LoteOut` with `id`), `GET /lotes/{lote_id}` (returns `LoteOut`), `POST /lotes/{lote_id}/cancelar` (returns `LoteOut`).

- [ ] **Step 1: Write lote_schemas.py**

`backend/app/api/schemas/lote_schemas.py`:
```python
from datetime import datetime

from pydantic import BaseModel

from app.domain.enums import StatusLote


class LoteOut(BaseModel):
    id: int
    empresa_id: int
    total_documentos: int
    documentos_processados: int
    status: StatusLote
    created_at: datetime
    concluido_em: datetime | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Write the failing integration test**

`backend/tests/integration/test_lotes_api.py`:
```python
import time

import fitz
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db, get_storage
from app.infrastructure.db.base import Base
from app.infrastructure.db import models  # noqa: F401
from app.infrastructure.storage.file_storage import LocalFileStorageService
from app.main import app


def _pdf_com_texto(texto: str) -> bytes:
    documento = fitz.open()
    pagina = documento.new_page()
    pagina.insert_text((72, 72), texto)
    conteudo = documento.tobytes()
    documento.close()
    return conteudo


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine)

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
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def empresa_id(client):
    response = client.post(
        "/empresas", json={"razao_social": "Tesserato", "nome_fantasia": None, "cnpj": "12345678000199"}
    )
    return response.json()["id"]


def test_processar_lote_ate_concluir(client, empresa_id):
    conteudo = _pdf_com_texto("COMPROVANTE TESTE INTEGRACAO 12345678901234567890")
    client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("comprovante.pdf", conteudo, "application/pdf")},
    )

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


def test_cancelar_lote(client, empresa_id):
    conteudo = _pdf_com_texto("COMPROVANTE OUTRO TESTE 12345678901234567890")
    client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("comprovante.pdf", conteudo, "application/pdf")},
    )
    lote_id = client.post(f"/empresas/{empresa_id}/documentos/processar").json()["id"]

    response = client.post(f"/lotes/{lote_id}/cancelar")
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELADO"


def test_obter_status_lote_inexistente_retorna_404(client):
    response = client.get("/lotes/999")
    assert response.status_code == 404
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/integration/test_lotes_api.py -v`
Expected: FAIL (404s — routes don't exist yet).

- [ ] **Step 4: Write lotes_router.py**

`backend/app/api/routers/lotes_router.py`:
```python
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.schemas.lote_schemas import LoteOut
from app.application.use_cases.lote_use_cases import (
    CancelarLoteUseCase,
    IniciarProcessamentoUseCase,
    ObterStatusLoteUseCase,
    processar_lote_em_background,
)
from app.core.config import settings
from app.core.exceptions import EmpresaNaoEncontrada, LoteNaoEncontrado
from app.infrastructure.repositories.sqlalchemy_documento_repository import (
    SqlAlchemyDocumentoRepository,
)
from app.infrastructure.repositories.sqlalchemy_empresa_repository import (
    SqlAlchemyEmpresaRepository,
)
from app.infrastructure.repositories.sqlalchemy_lote_processamento_repository import (
    SqlAlchemyLoteProcessamentoRepository,
)

router = APIRouter(tags=["lotes"])


@router.post(
    "/empresas/{empresa_id}/documentos/processar", response_model=LoteOut, status_code=201
)
def processar_documentos(
    empresa_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    documento_repo = SqlAlchemyDocumentoRepository(db)
    lote_repo = SqlAlchemyLoteProcessamentoRepository(db)
    empresa_repo = SqlAlchemyEmpresaRepository(db)
    try:
        lote = IniciarProcessamentoUseCase(documento_repo, lote_repo, empresa_repo).executar(
            empresa_id
        )
    except EmpresaNaoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    documento_ids = [d.id for d in documento_repo.listar_pendentes_por_empresa(empresa_id)]
    db.commit()

    if documento_ids:
        background_tasks.add_task(
            processar_lote_em_background, lote.id, documento_ids, settings.storage_root
        )
    return lote


@router.get("/lotes/{lote_id}", response_model=LoteOut)
def obter_status_lote(lote_id: int, db: Session = Depends(get_db)):
    repo = SqlAlchemyLoteProcessamentoRepository(db)
    try:
        return ObterStatusLoteUseCase(repo).executar(lote_id)
    except LoteNaoEncontrado as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/lotes/{lote_id}/cancelar", response_model=LoteOut)
def cancelar_lote(lote_id: int, db: Session = Depends(get_db)):
    repo = SqlAlchemyLoteProcessamentoRepository(db)
    try:
        return CancelarLoteUseCase(repo).executar(lote_id)
    except LoteNaoEncontrado as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

Note the endpoint captures `documento_ids` and commits *before* scheduling the background task — this is required because `background_tasks.add_task` runs after the response is sent, by which point the request-scoped `db` session (and its `get_db` generator) will already be closed; the background function opens its own fresh session (see Task 12).

- [ ] **Step 5: Register the router in main.py**

Add to `backend/app/main.py`:
```python
from app.api.routers.lotes_router import router as lotes_router
```
and
```python
app.include_router(lotes_router)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/integration/test_lotes_api.py -v`
Expected: PASS (4 passed). The polling test (`test_processar_lote_ate_concluir`) may take a few seconds since it waits for a real `ProcessPoolExecutor` to spin up and run the PDF-native-text path (fast — no real OCR engine needed for this fixture since it has genuine embedded text). If it times out, increase the retry loop count/sleep in the test rather than the pipeline itself.

- [ ] **Step 7: Run the full suite**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/schemas/lote_schemas.py backend/app/api/routers/lotes_router.py backend/app/main.py backend/tests/integration/test_lotes_api.py
git commit -m "feat: add lote processing REST endpoints (processar, status, cancelar)"
```

---

### Task 14: Frontend types and API client additions

**Files:**
- Create: `frontend/src/types/documento.ts`
- Modify: `frontend/src/api/client.ts`

**Interfaces:**
- Produces: `Documento`, `OcrResultadoDetalhe`, `DocumentoResultado`, `Lote`, `UploadItemResultado` TS interfaces. `api.documentos.upload(empresaId, files)`, `api.documentos.list(empresaId)`, `api.documentos.resultado(documentoId)`, `api.lotes.processar(empresaId)`, `api.lotes.status(loteId)`, `api.lotes.cancelar(loteId)`.

- [ ] **Step 1: Write documento.ts**

`frontend/src/types/documento.ts`:
```ts
export type StatusDocumento = "PENDENTE" | "PROCESSANDO" | "CONCLUIDO" | "ERRO";
export type MetodoOcr = "PDF_NATIVO" | "PADDLEOCR" | "TESSERACT";
export type StatusLote = "EM_ANDAMENTO" | "CONCLUIDO" | "CANCELADO";

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
}

export interface UploadItemResultado {
  nome_original: string;
  documento: Documento | null;
  erro: string | null;
}

export interface OcrResultadoDetalhe {
  texto_extraido: string;
  metodo: MetodoOcr;
  tempo_processamento_ms: number;
}

export interface DocumentoResultado {
  documento: Documento;
  resultado: OcrResultadoDetalhe | null;
}

export interface Lote {
  id: number;
  empresa_id: number;
  total_documentos: number;
  documentos_processados: number;
  status: StatusLote;
  created_at: string;
  concluido_em: string | null;
}
```

- [ ] **Step 2: Append to client.ts**

Add to `frontend/src/api/client.ts`: an import line `import type { Documento, DocumentoResultado, Lote, UploadItemResultado } from "../types/documento";` near the top, and extend the `api` object (add these keys alongside the existing `empresas`, `planosContas`, `contas`):

```ts
  documentos: {
    upload: (empresaId: number, arquivos: File[]) => {
      const formData = new FormData();
      arquivos.forEach((arquivo) => formData.append("arquivos", arquivo));
      return request<UploadItemResultado[]>(`/empresas/${empresaId}/documentos`, {
        method: "POST",
        body: formData,
      });
    },
    list: (empresaId: number) => request<Documento[]>(`/empresas/${empresaId}/documentos`),
    resultado: (documentoId: number) =>
      request<DocumentoResultado>(`/documentos/${documentoId}/resultado`),
  },
  lotes: {
    processar: (empresaId: number) =>
      request<Lote>(`/empresas/${empresaId}/documentos/processar`, { method: "POST" }),
    status: (loteId: number) => request<Lote>(`/lotes/${loteId}`),
    cancelar: (loteId: number) =>
      request<Lote>(`/lotes/${loteId}/cancelar`, { method: "POST" }),
  },
```

- [ ] **Step 3: Verify no type errors**

Run: `cd "D:/DEV/Teste Lançamentos/frontend" && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/documento.ts frontend/src/api/client.ts
git commit -m "feat: add frontend types and API client for documento/lote upload+processing"
```

---

### Task 15: Frontend upload/processing UI + end-to-end verification

**Files:**
- Create: `frontend/src/components/DocumentoDropzone.tsx`
- Create: `frontend/src/components/DocumentoList.tsx`
- Create: `frontend/src/components/ProgressoLote.tsx`
- Modify: `frontend/src/pages/EmpresasPage.tsx`

**Interfaces:**
- Consumes: `api.documentos.*`, `api.lotes.*` (Task 14), `Documento`, `Lote`, `UploadItemResultado` (Task 14).
- Produces: `DocumentoDropzone({ empresaId, onUploaded })`, `DocumentoList({ documentos })`, `ProgressoLote({ lote, onCancelar })` — the Fase 1 additions wired into `EmpresasPage`.

- [ ] **Step 1: Write DocumentoDropzone.tsx**

`frontend/src/components/DocumentoDropzone.tsx`:
```tsx
import { useRef, useState } from "react";
import { api } from "../api/client";
import type { Documento } from "../types/documento";

export function DocumentoDropzone({
  empresaId,
  onUploaded,
}: {
  empresaId: number;
  onUploaded: (documentos: Documento[]) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [arrastando, setArrastando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function enviarArquivos(arquivos: FileList | File[]) {
    setErro(null);
    try {
      const resultados = await api.documentos.upload(empresaId, Array.from(arquivos));
      const documentosCriados = resultados
        .filter((r) => r.documento !== null)
        .map((r) => r.documento as Documento);
      const erros = resultados.filter((r) => r.erro !== null);
      if (erros.length > 0) {
        setErro(erros.map((e) => `${e.nome_original}: ${e.erro}`).join("; "));
      }
      if (documentosCriados.length > 0) {
        onUploaded(documentosCriados);
      }
    } catch (err) {
      setErro((err as Error).message);
    }
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setArrastando(true);
      }}
      onDragLeave={() => setArrastando(false)}
      onDrop={(e) => {
        e.preventDefault();
        setArrastando(false);
        if (e.dataTransfer.files.length > 0) enviarArquivos(e.dataTransfer.files);
      }}
      onClick={() => inputRef.current?.click()}
      className={`cursor-pointer rounded border-2 border-dashed p-8 text-center text-sm ${
        arrastando ? "border-slate-500 bg-slate-100" : "border-slate-300 text-slate-500"
      }`}
    >
      Arraste comprovantes aqui (PDF/PNG/JPG) ou clique para selecionar
      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".pdf,.png,.jpg,.jpeg"
        className="hidden"
        onChange={(e) => {
          if (e.target.files && e.target.files.length > 0) enviarArquivos(e.target.files);
          e.target.value = "";
        }}
      />
      {erro && <p className="mt-2 text-red-600">{erro}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Write DocumentoList.tsx**

`frontend/src/components/DocumentoList.tsx`:
```tsx
import { useState } from "react";
import { api } from "../api/client";
import type { Documento, DocumentoResultado } from "../types/documento";

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

export function DocumentoList({ documentos }: { documentos: Documento[] }) {
  const [resultadoAberto, setResultadoAberto] = useState<DocumentoResultado | null>(null);

  async function verResultado(documentoId: number) {
    const resultado = await api.documentos.resultado(documentoId);
    setResultadoAberto(resultado);
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

- [ ] **Step 3: Write ProgressoLote.tsx**

`frontend/src/components/ProgressoLote.tsx`:
```tsx
import type { Lote } from "../types/documento";

export function ProgressoLote({
  lote,
  onCancelar,
}: {
  lote: Lote;
  onCancelar: () => void;
}) {
  const percentual =
    lote.total_documentos === 0
      ? 100
      : Math.round((lote.documentos_processados / lote.total_documentos) * 100);

  return (
    <div className="flex flex-col gap-2 rounded border border-slate-200 p-3">
      <div className="flex items-center justify-between text-sm">
        <span>
          {lote.documentos_processados} de {lote.total_documentos} processados —{" "}
          {lote.status}
        </span>
        {lote.status === "EM_ANDAMENTO" && (
          <button onClick={onCancelar} className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-700">
            Cancelar
          </button>
        )}
      </div>
      <div className="h-2 w-full rounded bg-slate-200">
        <div
          className="h-2 rounded bg-slate-700 transition-all"
          style={{ width: `${percentual}%` }}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Wire into EmpresasPage.tsx**

Add these imports to `frontend/src/pages/EmpresasPage.tsx`:
```tsx
import { useEffect, useRef, useState } from "react";
import { DocumentoDropzone } from "../components/DocumentoDropzone";
import { DocumentoList } from "../components/DocumentoList";
import { ProgressoLote } from "../components/ProgressoLote";
import type { Documento, Lote } from "../types/documento";
```

(Merge the `useEffect, useState` imports with the existing `import { useEffect, useState } from "react";` line — add `useRef` to it.)

Add this state and effect inside the `EmpresasPage` component function, alongside the existing state declarations:
```tsx
  const [documentos, setDocumentos] = useState<Documento[]>([]);
  const [lote, setLote] = useState<Lote | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (empresaSelecionadaId === null) {
      setDocumentos([]);
      return;
    }
    api.documentos.list(empresaSelecionadaId).then(setDocumentos);
  }, [empresaSelecionadaId]);

  useEffect(() => {
    if (lote === null || lote.status !== "EM_ANDAMENTO") {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
      return;
    }
    pollingRef.current = setInterval(async () => {
      const atualizado = await api.lotes.status(lote.id);
      setLote(atualizado);
      if (atualizado.status !== "EM_ANDAMENTO" && empresaSelecionadaId !== null) {
        const documentosAtualizados = await api.documentos.list(empresaSelecionadaId);
        setDocumentos(documentosAtualizados);
      }
    }, 2000);
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [lote, empresaSelecionadaId]);

  async function handleProcessar() {
    if (empresaSelecionadaId === null) return;
    const novoLote = await api.lotes.processar(empresaSelecionadaId);
    setLote(novoLote);
  }

  async function handleCancelarLote() {
    if (lote === null) return;
    const cancelado = await api.lotes.cancelar(lote.id);
    setLote(cancelado);
  }
```

Add this section to the JSX, after the existing empresa-selected section (right after the closing `</section>` of the "Planos de Contas" block, still inside the `{empresaSelecionadaId !== null && (...)}` conditional — check the current structure of the file and place it as a sibling to the existing sections, before the file's final closing tags):
```tsx
      {empresaSelecionadaId !== null && (
        <section className="flex flex-col gap-3 border-t border-slate-200 pt-4">
          <h2 className="text-sm font-semibold text-slate-700">Comprovantes</h2>
          <DocumentoDropzone
            empresaId={empresaSelecionadaId}
            onUploaded={(novos) => setDocumentos((atual) => [...atual, ...novos])}
          />
          <button
            onClick={handleProcessar}
            disabled={documentos.every((d) => d.status !== "PENDENTE")}
            className="self-start rounded bg-slate-800 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          >
            Processar
          </button>
          {lote && <ProgressoLote lote={lote} onCancelar={handleCancelarLote} />}
          <DocumentoList documentos={documentos} />
        </section>
      )}
```

- [ ] **Step 5: Verify types and build**

Run: `cd "D:/DEV/Teste Lançamentos/frontend" && npx tsc --noEmit && npm run build`
Expected: both succeed.

- [ ] **Step 6: Run the full backend suite once more**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest -v`
Expected: all pass. This is the complete Fase 1 backend + frontend.

- [ ] **Step 7: Commit**

```bash
git add frontend/src
git commit -m "feat: add document upload/processing UI wired into EmpresasPage"
```

- [ ] **Step 8: Manual end-to-end verification (performed by the controller with browser tooling, not by an implementer subagent without one)**

With the backend running (`uvicorn app.main:app --reload` from `backend/`, after `alembic upgrade head`) and frontend running (`npm run dev` from `frontend/`):
1. Open `http://localhost:5173`, select or create an empresa.
2. Drag-and-drop (or click to select) a real PDF comprovante — confirm it appears in the document list with status `PENDENTE`.
3. Click "Processar" — confirm a progress bar appears and updates via polling (`X de Y processados`).
4. Once `CONCLUIDO`, click "Ver texto" on the processed document and confirm the extracted text renders, along with which method was used (`PDF_NATIVO`, `PADDLEOCR`, or `TESSERACT`).
5. Repeat with a scanned/image-only PDF or a plain image (PNG/JPG) to exercise the OCR fallback path — confirm the method shown is `PADDLEOCR` (or `TESSERACT` if PaddleOCR wasn't installable in this environment, per Task 10's note) rather than `PDF_NATIVO`.
6. Test cancel: upload several documents, click "Processar", then quickly click "Cancelar" — confirm the batch stops accepting new documents (status becomes `CANCELADO`; any documents already mid-flight when cancelled still complete, per the design's stated cancellation semantics — this is expected, not a bug).

If PaddleOCR failed to install in Task 10 (noted as an acceptable `DONE_WITH_CONCERNS` outcome there) and Tesseract also isn't installed, OCR-requiring documents will fail with a clear `ERRO` status and message — confirm this failure is clean (visible error message, not a silent hang or crash) rather than blocking on getting both engines working before merging this phase.

---

## Post-Plan Notes

- Fase 1 is complete when all 15 tasks are committed and the manual end-to-end verification in Task 15 Step 8 passes (allowing for the documented PaddleOCR-install caveat).
- If PaddleOCR could not be installed in this environment, note that explicitly in the final report — the architecture still supports it (nothing needs to change later, just `pip install` succeeding on a machine with compatible wheels), and Tesseract-only operation is an acceptable interim state per the design spec's engine-fallback intent.
- The next spec (`Fase 2 — Extração + Normalização de dados`) should be brainstormed separately, following `superpowers:brainstorming`, and will consume `ocr_resultados.texto_extraido` as its input, plus update `documentos.nome_exibicao` to the "Tipo - Data" format once those fields are extracted.
