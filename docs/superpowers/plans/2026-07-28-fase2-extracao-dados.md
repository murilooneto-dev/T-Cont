# Fase 2 — Extração + Normalização de Dados — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically extract a small set of structured fields (payer/payee name and CPF/CNPJ, amount, payment date, document type, bank) from each document's OCR text, using deterministic regex/heuristics (no AI), storing `NULL` for anything not found and never inventing data.

**Architecture:** Extends the existing Clean Architecture. Each field extractor is a pure function (`str -> value | None`) living in `app/infrastructure/extracao/`, aggregated by one pipeline function. The pipeline runs inside the existing Fase 1 OCR background worker (`processar_lote_em_background` in `app/infrastructure/workers/lote_worker.py`), right after a document's OCR succeeds and before it's marked `CONCLUIDO`, persisting an `Extracao` row via a new repository. The existing `GET /documentos/{id}/resultado` endpoint is extended to include the extracted fields, serializing `NULL` as `"NÃO IDENTIFICADO"`.

**Tech Stack:** Python (existing FastAPI/SQLAlchemy/Alembic backend), stdlib `re`/`decimal`/`datetime` only — no new dependencies. React/TypeScript frontend (existing Vite scaffold).

## Global Constraints

- No paid services anywhere in this phase.
- No authentication in this phase.
- Runs locally on Windows via terminal, no Docker.
- SQLite now, schema portable to PostgreSQL.
- No AI/LLM in this phase — extraction is 100% deterministic regex/heuristics.
- A field that cannot be found in the text must be persisted as `NULL`, never a guessed value. `NULL` is translated to the display string `"NÃO IDENTIFICADO"` only at the API/frontend layer, never written to the database.
- Scope for this phase: `pagador_nome`, `pagador_documento`, `recebedor_nome`, `recebedor_documento`, `valor`, `data_pagamento`, `tipo_documento`, `banco_nome`. Agência, conta, número de autenticação, observações, and fornecedor-name unification (Fase 3/4) are explicitly out of scope.
- CPF/CNPJ extraction validates only digit-count (11 or 14 digits after stripping punctuation), not check-digit algorithms — out of scope for this phase.
- Integration test DB fixtures must go through `app.infrastructure.db.session.get_engine()` (PRAGMA foreign_keys=ON parity), not raw `create_engine()` — this project has regressed on this lesson twice already (Fase 0 and Fase 1 final reviews).
- A background-worker failure must always drive its unit of work to a terminal, visible state — never leave something silently half-done. Extraction failures inside the worker must be caught by the same error handling `processar_lote_em_background` already has for OCR failures (a document whose extraction blows up must not crash the whole batch or strand it).

---

## File Structure

```
backend/
  app/
    domain/
      enums.py                                   # MODIFY: add TipoDocumento
      entities.py                                 # MODIFY: add Extracao
    application/
      repositories.py                             # MODIFY: add ExtracaoRepository
    infrastructure/
      db/
        models.py                                 # MODIFY: real ExtracaoModel columns
      repositories/
        sqlalchemy_extracao_repository.py         # CREATE
      extracao/
        __init__.py                               # CREATE
        tipo_documento.py                         # CREATE
        documento_fiscal.py                       # CREATE
        valor.py                                  # CREATE
        data.py                                   # CREATE
        nomes.py                                  # CREATE
        banco.py                                  # CREATE
        pipeline.py                               # CREATE
      workers/
        lote_worker.py                             # MODIFY: run extraction after OCR success
    api/
      schemas/
        documento_schemas.py                       # MODIFY: add ExtracaoOut, extend DocumentoResultadoOut
      routers/
        documentos_router.py                       # MODIFY: populate ExtracaoOut in /resultado
  alembic/versions/
    0003_fase2_extracao_dados.py                    # CREATE
  tests/
    fakes.py                                        # MODIFY: add FakeExtracaoRepository
    unit/
      test_extracao_domain.py                       # CREATE (folded into a shared file, see Task 2)
      test_tipo_documento.py                        # CREATE
      test_documento_fiscal.py                       # CREATE
      test_valor.py                                  # CREATE
      test_data.py                                   # CREATE
      test_nomes.py                                  # CREATE
      test_banco.py                                  # CREATE
      test_extracao_pipeline.py                      # CREATE
    integration/
      test_fase2_migration.py                        # CREATE
      test_sqlalchemy_extracao_repository.py          # CREATE
      test_lotes_api.py                               # MODIFY: extend worker test to assert extraction ran
      test_documentos_api.py                          # MODIFY: assert /resultado includes extracao fields
frontend/
  src/
    types/documento.ts                               # MODIFY: add Extracao type, extend DocumentoResultado
    components/DocumentoList.tsx                      # MODIFY: render extracted fields
```

---

### Task 1: Database schema — real `extracoes` table + `TipoDocumento` enum

**Files:**
- Modify: `backend/app/domain/enums.py`
- Modify: `backend/app/infrastructure/db/models.py`
- Create: `backend/alembic/versions/0003_fase2_extracao_dados.py`
- Test: `backend/tests/integration/test_fase2_migration.py`

**Interfaces:**
- Produces: `TipoDocumento` enum (`PIX`, `TED`, `DOC`, `BOLETO`, `OUTRO`) in `app.domain.enums`. `ExtracaoModel` (replacing the Fase 0 stub version) in `app.infrastructure.db.models`.

- [ ] **Step 1: Write the failing test**

`backend/tests/integration/test_fase2_migration.py`:
```python
from sqlalchemy import create_engine, inspect
from alembic import command
from alembic.config import Config


def test_migration_adds_extracoes_columns(tmp_path):
    db_path = tmp_path / "test_fase2_migration.db"
    db_url = f"sqlite:///{db_path}"

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(db_url)
    inspector = inspect(engine)

    extracao_cols = {c["name"] for c in inspector.get_columns("extracoes")}
    assert extracao_cols == {
        "id", "documento_id", "pagador_nome", "pagador_documento",
        "recebedor_nome", "recebedor_documento", "valor", "data_pagamento",
        "tipo_documento", "banco_nome", "created_at",
    }

    # downgrade must be symmetric
    command.downgrade(alembic_cfg, "0002")
    inspector = inspect(engine)
    extracao_cols = {c["name"] for c in inspector.get_columns("extracoes")}
    assert extracao_cols == {"id", "empresa_id", "created_at"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/integration/test_fase2_migration.py -v`
Expected: FAIL (extracoes still has the Fase 0 stub columns `id, empresa_id, created_at`).

- [ ] **Step 3: Add `TipoDocumento` enum**

Append to `backend/app/domain/enums.py`:
```python
class TipoDocumento(str, Enum):
    PIX = "PIX"
    TED = "TED"
    DOC = "DOC"
    BOLETO = "BOLETO"
    OUTRO = "OUTRO"
```

- [ ] **Step 4: Replace the stub `ExtracaoModel`**

In `backend/app/infrastructure/db/models.py`, update the import line at the top from:
```python
from datetime import datetime, timezone
```
to:
```python
from datetime import date, datetime, timezone
from decimal import Decimal
```

Update the sqlalchemy import line from:
```python
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
```
to:
```python
from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
```

Replace the existing stub `ExtracaoModel` class (currently `id`, `empresa_id`, `created_at`) with:
```python
class ExtracaoModel(Base):
    __tablename__ = "extracoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    documento_id: Mapped[int] = mapped_column(
        ForeignKey("documentos.id"), nullable=False, unique=True
    )
    pagador_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pagador_documento: Mapped[str | None] = mapped_column(String(14), nullable=True)
    recebedor_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recebedor_documento: Mapped[str | None] = mapped_column(String(14), nullable=True)
    valor: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    data_pagamento: Mapped[date | None] = mapped_column(Date, nullable=True)
    tipo_documento: Mapped[str] = mapped_column(String(20), nullable=False, default="OUTRO")
    banco_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
```

- [ ] **Step 5: Write the migration**

`backend/alembic/versions/0003_fase2_extracao_dados.py`:
```python
"""fase2 extracao de dados: real extracoes table

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("extracoes")
    op.create_table(
        "extracoes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "documento_id", sa.Integer, sa.ForeignKey("documentos.id"),
            nullable=False, unique=True,
        ),
        sa.Column("pagador_nome", sa.String(255), nullable=True),
        sa.Column("pagador_documento", sa.String(14), nullable=True),
        sa.Column("recebedor_nome", sa.String(255), nullable=True),
        sa.Column("recebedor_documento", sa.String(14), nullable=True),
        sa.Column("valor", sa.Numeric(12, 2), nullable=True),
        sa.Column("data_pagamento", sa.Date, nullable=True),
        sa.Column("tipo_documento", sa.String(20), nullable=False, server_default="OUTRO"),
        sa.Column("banco_nome", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("extracoes")
    op.create_table(
        "extracoes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
```

Note: dropping and recreating `extracoes` (rather than `alter_column`) is safe because no real data has ever been written to this stub table — confirm by checking `git log --all --oneline -- backend/alembic/versions/` shows only `0001` and `0002` before this task; if that's no longer true, use `add_column`/`drop_column` instead.

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/integration/test_fase2_migration.py -v`
Expected: PASS

- [ ] **Step 7: Run the full existing suite to confirm no regressions**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all tests pass (baseline: 157 passed, 1 skipped).

- [ ] **Step 8: Commit**

```bash
git add backend/app/domain/enums.py backend/app/infrastructure/db/models.py backend/alembic/versions/0003_fase2_extracao_dados.py backend/tests/integration/test_fase2_migration.py
git commit -m "feat: add real extracoes table and TipoDocumento enum"
```

---

### Task 2: Domain entity `Extracao`

**Files:**
- Modify: `backend/app/domain/entities.py`
- Test: `backend/tests/unit/test_extracao_domain.py`

**Interfaces:**
- Consumes: `TipoDocumento` (Task 1).
- Produces: `Extracao` dataclass in `app.domain.entities`.

- [ ] **Step 1: Write the failing test**

`backend/tests/unit/test_extracao_domain.py`:
```python
from decimal import Decimal
from datetime import date

from app.domain.entities import Extracao
from app.domain.enums import TipoDocumento


def test_extracao_permite_todos_os_campos_ausentes_exceto_tipo():
    extracao = Extracao(
        id=None, documento_id=1, pagador_nome=None, pagador_documento=None,
        recebedor_nome=None, recebedor_documento=None, valor=None,
        data_pagamento=None, tipo_documento=TipoDocumento.OUTRO, banco_nome=None,
    )
    assert extracao.pagador_nome is None
    assert extracao.tipo_documento == TipoDocumento.OUTRO


def test_extracao_com_todos_os_campos_preenchidos():
    extracao = Extracao(
        id=None, documento_id=1, pagador_nome="JOAO DA SILVA",
        pagador_documento="12345678900", recebedor_nome="ENERGISA",
        recebedor_documento="12345678000199", valor=Decimal("150.00"),
        data_pagamento=date(2026, 3, 15), tipo_documento=TipoDocumento.PIX,
        banco_nome="Itaú",
    )
    assert extracao.valor == Decimal("150.00")
    assert extracao.data_pagamento == date(2026, 3, 15)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_extracao_domain.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Add the entity**

In `backend/app/domain/entities.py`, update the top import from:
```python
from app.domain.enums import MetodoOcr, NaturezaConta, StatusDocumento, StatusLote
```
to:
```python
from app.domain.enums import MetodoOcr, NaturezaConta, StatusDocumento, StatusLote, TipoDocumento
```

Add `from datetime import date, datetime` in place of the current `from datetime import datetime`, and add `from decimal import Decimal` alongside the existing imports at the top of the file.

Append:
```python
@dataclass
class Extracao:
    id: int | None
    documento_id: int
    pagador_nome: str | None
    pagador_documento: str | None
    recebedor_nome: str | None
    recebedor_documento: str | None
    valor: Decimal | None
    data_pagamento: date | None
    tipo_documento: TipoDocumento
    banco_nome: str | None
    created_at: datetime | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/unit/test_extracao_domain.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/entities.py backend/tests/unit/test_extracao_domain.py
git commit -m "feat: add Extracao domain entity"
```

---

### Task 3: `ExtracaoRepository` interface + fake

**Files:**
- Modify: `backend/app/application/repositories.py`
- Modify: `backend/tests/fakes.py`

**Interfaces:**
- Consumes: `Extracao` (Task 2).
- Produces: `ExtracaoRepository` abstract class (`criar`, `obter_por_documento_id`) in `app.application.repositories`. `FakeExtracaoRepository` in `tests.fakes`.

- [ ] **Step 1: Add the abstract repository**

In `backend/app/application/repositories.py`, update the top import from:
```python
from app.domain.entities import Conta, Documento, Empresa, LoteProcessamento, OcrResultado, PlanoContas
```
to:
```python
from app.domain.entities import (
    Conta, Documento, Empresa, Extracao, LoteProcessamento, OcrResultado, PlanoContas,
)
```

Append:
```python
class ExtracaoRepository(ABC):
    @abstractmethod
    def criar(self, extracao: Extracao) -> Extracao: ...

    @abstractmethod
    def obter_por_documento_id(self, documento_id: int) -> Extracao | None: ...
```

- [ ] **Step 2: Add the fake**

In `backend/tests/fakes.py`, update the imports:
```python
from app.application.repositories import (
    ContaRepository,
    DocumentoRepository,
    EmpresaRepository,
    ExtracaoRepository,
    LoteProcessamentoRepository,
    OcrResultadoRepository,
    PlanoContasRepository,
)
from app.domain.entities import (
    Conta, Documento, Empresa, Extracao, LoteProcessamento, OcrResultado, PlanoContas,
)
```

Append:
```python
class FakeExtracaoRepository(ExtracaoRepository):
    def __init__(self):
        self._items: dict[int, Extracao] = {}
        self._next_id = 1

    def criar(self, extracao: Extracao) -> Extracao:
        extracao.id = self._next_id
        self._items[self._next_id] = extracao
        self._next_id += 1
        return extracao

    def obter_por_documento_id(self, documento_id: int) -> Extracao | None:
        return next((e for e in self._items.values() if e.documento_id == documento_id), None)
```

- [ ] **Step 3: Verify the fake satisfies the interface**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -c "from tests.fakes import FakeExtracaoRepository; FakeExtracaoRepository(); print('ok')"`
Expected: prints `ok`.

- [ ] **Step 4: Run the full suite**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/application/repositories.py backend/tests/fakes.py
git commit -m "feat: add ExtracaoRepository interface and fake"
```

---

### Task 4: SQLAlchemy repository for `Extracao`

**Files:**
- Create: `backend/app/infrastructure/repositories/sqlalchemy_extracao_repository.py`
- Test: `backend/tests/integration/test_sqlalchemy_extracao_repository.py`

**Interfaces:**
- Consumes: `ExtracaoRepository` (Task 3), `ExtracaoModel` (Task 1), the existing `db_session` fixture (`backend/tests/conftest.py`).
- Produces: `SqlAlchemyExtracaoRepository(session)`.

- [ ] **Step 1: Write the failing test**

`backend/tests/integration/test_sqlalchemy_extracao_repository.py`:
```python
from decimal import Decimal
from datetime import date

from app.domain.entities import Documento, Empresa, Extracao
from app.domain.enums import TipoDocumento
from app.infrastructure.repositories.sqlalchemy_documento_repository import (
    SqlAlchemyDocumentoRepository,
)
from app.infrastructure.repositories.sqlalchemy_empresa_repository import (
    SqlAlchemyEmpresaRepository,
)
from app.infrastructure.repositories.sqlalchemy_extracao_repository import (
    SqlAlchemyExtracaoRepository,
)


def _criar_documento(db_session):
    empresa = SqlAlchemyEmpresaRepository(db_session).criar(
        Empresa(id=None, razao_social="Tesserato", nome_fantasia=None, cnpj="12345678000199")
    )
    db_session.commit()
    documento = SqlAlchemyDocumentoRepository(db_session).criar(
        Documento(
            id=None, empresa_id=empresa.id, nome_arquivo="a.pdf", nome_exibicao="a.pdf",
            caminho_arquivo="x/a.pdf", extensao=".pdf", tamanho_bytes=10,
        )
    )
    db_session.commit()
    return documento


def test_criar_extracao_com_campos_nulos(db_session):
    documento = _criar_documento(db_session)
    repo = SqlAlchemyExtracaoRepository(db_session)

    criada = repo.criar(
        Extracao(
            id=None, documento_id=documento.id, pagador_nome=None, pagador_documento=None,
            recebedor_nome=None, recebedor_documento=None, valor=None,
            data_pagamento=None, tipo_documento=TipoDocumento.OUTRO, banco_nome=None,
        )
    )
    db_session.commit()

    encontrada = repo.obter_por_documento_id(documento.id)
    assert encontrada.id == criada.id
    assert encontrada.pagador_nome is None
    assert encontrada.tipo_documento == TipoDocumento.OUTRO


def test_criar_extracao_com_todos_os_campos(db_session):
    documento = _criar_documento(db_session)
    repo = SqlAlchemyExtracaoRepository(db_session)

    repo.criar(
        Extracao(
            id=None, documento_id=documento.id, pagador_nome="JOAO DA SILVA",
            pagador_documento="12345678900", recebedor_nome="ENERGISA",
            recebedor_documento="12345678000199", valor=Decimal("150.00"),
            data_pagamento=date(2026, 3, 15), tipo_documento=TipoDocumento.PIX,
            banco_nome="Itaú",
        )
    )
    db_session.commit()

    encontrada = repo.obter_por_documento_id(documento.id)
    assert encontrada.valor == Decimal("150.00")
    assert encontrada.data_pagamento == date(2026, 3, 15)
    assert encontrada.tipo_documento == TipoDocumento.PIX


def test_obter_por_documento_id_inexistente_retorna_none(db_session):
    repo = SqlAlchemyExtracaoRepository(db_session)
    assert repo.obter_por_documento_id(999) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/integration/test_sqlalchemy_extracao_repository.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the repository**

`backend/app/infrastructure/repositories/sqlalchemy_extracao_repository.py`:
```python
from sqlalchemy.orm import Session

from app.application.repositories import ExtracaoRepository
from app.domain.entities import Extracao
from app.domain.enums import TipoDocumento
from app.infrastructure.db.models import ExtracaoModel


def _to_entity(model: ExtracaoModel) -> Extracao:
    return Extracao(
        id=model.id,
        documento_id=model.documento_id,
        pagador_nome=model.pagador_nome,
        pagador_documento=model.pagador_documento,
        recebedor_nome=model.recebedor_nome,
        recebedor_documento=model.recebedor_documento,
        valor=model.valor,
        data_pagamento=model.data_pagamento,
        tipo_documento=TipoDocumento(model.tipo_documento),
        banco_nome=model.banco_nome,
        created_at=model.created_at,
    )


class SqlAlchemyExtracaoRepository(ExtracaoRepository):
    def __init__(self, session: Session):
        self._session = session

    def criar(self, extracao: Extracao) -> Extracao:
        model = ExtracaoModel(
            documento_id=extracao.documento_id,
            pagador_nome=extracao.pagador_nome,
            pagador_documento=extracao.pagador_documento,
            recebedor_nome=extracao.recebedor_nome,
            recebedor_documento=extracao.recebedor_documento,
            valor=extracao.valor,
            data_pagamento=extracao.data_pagamento,
            tipo_documento=extracao.tipo_documento.value,
            banco_nome=extracao.banco_nome,
        )
        self._session.add(model)
        self._session.flush()
        return _to_entity(model)

    def obter_por_documento_id(self, documento_id: int) -> Extracao | None:
        model = (
            self._session.query(ExtracaoModel)
            .filter_by(documento_id=documento_id)
            .first()
        )
        return _to_entity(model) if model else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/integration/test_sqlalchemy_extracao_repository.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/infrastructure/repositories/sqlalchemy_extracao_repository.py backend/tests/integration/test_sqlalchemy_extracao_repository.py
git commit -m "feat: add SqlAlchemyExtracaoRepository"
```

---

### Task 5: Extractor — tipo de documento

**Files:**
- Create: `backend/app/infrastructure/extracao/__init__.py`
- Create: `backend/app/infrastructure/extracao/tipo_documento.py`
- Test: `backend/tests/unit/test_tipo_documento.py`

**Interfaces:**
- Consumes: `TipoDocumento` (Task 1).
- Produces: `extrair_tipo_documento(texto: str) -> TipoDocumento`.

- [ ] **Step 1: Write the failing test**

`backend/tests/unit/test_tipo_documento.py`:
```python
from app.domain.enums import TipoDocumento
from app.infrastructure.extracao.tipo_documento import extrair_tipo_documento


def test_detecta_pix():
    assert extrair_tipo_documento("Comprovante de Transferência PIX") == TipoDocumento.PIX


def test_detecta_ted():
    assert extrair_tipo_documento("TED - Transferência Eletrônica Disponível") == TipoDocumento.TED


def test_detecta_doc():
    assert extrair_tipo_documento("Comprovante de DOC realizado com sucesso") == TipoDocumento.DOC


def test_detecta_boleto():
    assert extrair_tipo_documento("Pagamento de BOLETO bancário") == TipoDocumento.BOLETO


def test_nenhuma_palavra_chave_retorna_outro():
    assert extrair_tipo_documento("Recibo de pagamento diverso") == TipoDocumento.OUTRO


def test_doc_nao_confunde_com_palavra_documento():
    # "DOCUMENTO" contém "DOC" como substring, mas não é o tipo de transferência DOC.
    assert extrair_tipo_documento("Este é um DOCUMENTO de cobrança sem tipo especificado") == TipoDocumento.OUTRO
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_tipo_documento.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the extractor**

`backend/app/infrastructure/extracao/tipo_documento.py`:
```python
import re

from app.domain.enums import TipoDocumento

_PADROES = [
    (TipoDocumento.PIX, re.compile(r"\bPIX\b", re.IGNORECASE)),
    (TipoDocumento.TED, re.compile(r"\bTED\b", re.IGNORECASE)),
    (TipoDocumento.DOC, re.compile(r"\bDOC\b", re.IGNORECASE)),
    (TipoDocumento.BOLETO, re.compile(r"\bBOLETO\b", re.IGNORECASE)),
]


def extrair_tipo_documento(texto: str) -> TipoDocumento:
    for tipo, padrao in _PADROES:
        if padrao.search(texto):
            return tipo
    return TipoDocumento.OUTRO
```

`backend/app/infrastructure/extracao/__init__.py`: empty file.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/unit/test_tipo_documento.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/extracao backend/tests/unit/test_tipo_documento.py
git commit -m "feat: add tipo de documento extractor"
```

---

### Task 6: Extractor — CPF/CNPJ

**Files:**
- Create: `backend/app/infrastructure/extracao/documento_fiscal.py`
- Test: `backend/tests/unit/test_documento_fiscal.py`

**Interfaces:**
- Produces: `extrair_documentos(texto: str) -> list[str]` — returns every CPF/CNPJ found in the text, normalized to digits-only, in the order they appear, without duplicates. (Design decision: the pipeline task, Task 11, will treat the first distinct document found as the payer's and the second as the payee's — a simplification consistent with the "essential subset, heuristic-based" scope; it does not try to associate a document number with a specific label like "Pagador:".)

- [ ] **Step 1: Write the failing test**

`backend/tests/unit/test_documento_fiscal.py`:
```python
from app.infrastructure.extracao.documento_fiscal import extrair_documentos


def test_extrai_cnpj_com_pontuacao():
    resultado = extrair_documentos("CNPJ: 12.345.678/0001-95")
    assert resultado == ["12345678000195"]


def test_extrai_cpf_com_pontuacao():
    resultado = extrair_documentos("CPF: 123.456.789-00")
    assert resultado == ["12345678900"]


def test_extrai_multiplos_documentos_na_ordem():
    texto = "Pagador CPF: 123.456.789-00\nRecebedor CNPJ: 12.345.678/0001-95"
    resultado = extrair_documentos(texto)
    assert resultado == ["12345678900", "12345678000195"]


def test_nao_duplica_o_mesmo_documento():
    texto = "CPF 123.456.789-00 repetido: 123.456.789-00"
    resultado = extrair_documentos(texto)
    assert resultado == ["12345678900"]


def test_texto_sem_documento_retorna_lista_vazia():
    assert extrair_documentos("Nenhum documento fiscal aqui.") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_documento_fiscal.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the extractor**

`backend/app/infrastructure/extracao/documento_fiscal.py`:
```python
import re

_PADRAO_DOCUMENTO = re.compile(
    r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}|\d{3}\.?\d{3}\.?\d{3}-?\d{2}"
)


def _normalizar_documento(bruto: str) -> str:
    return re.sub(r"\D", "", bruto)


def extrair_documentos(texto: str) -> list[str]:
    encontrados: list[str] = []
    for match in _PADRAO_DOCUMENTO.finditer(texto):
        digitos = _normalizar_documento(match.group())
        if len(digitos) in (11, 14) and digitos not in encontrados:
            encontrados.append(digitos)
    return encontrados
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/unit/test_documento_fiscal.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/extracao/documento_fiscal.py backend/tests/unit/test_documento_fiscal.py
git commit -m "feat: add CPF/CNPJ extractor"
```

---

### Task 7: Extractor — valor

**Files:**
- Create: `backend/app/infrastructure/extracao/valor.py`
- Test: `backend/tests/unit/test_valor.py`

**Interfaces:**
- Produces: `extrair_valor(texto: str) -> Decimal | None`.

- [ ] **Step 1: Write the failing test**

`backend/tests/unit/test_valor.py`:
```python
from decimal import Decimal

from app.infrastructure.extracao.valor import extrair_valor


def test_extrai_valor_com_milhar():
    assert extrair_valor("Valor: R$ 1.234,56") == Decimal("1234.56")


def test_extrai_valor_sem_espaco():
    assert extrair_valor("Total R$150,00 pago") == Decimal("150.00")


def test_texto_sem_valor_retorna_none():
    assert extrair_valor("Nenhum valor monetário aqui.") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_valor.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the extractor**

`backend/app/infrastructure/extracao/valor.py`:
```python
import re
from decimal import Decimal, InvalidOperation

_PADRAO_VALOR = re.compile(r"R\$\s*([\d.]+,\d{2})")


def extrair_valor(texto: str) -> Decimal | None:
    match = _PADRAO_VALOR.search(texto)
    if not match:
        return None
    bruto = match.group(1)
    normalizado = bruto.replace(".", "").replace(",", ".")
    try:
        return Decimal(normalizado)
    except InvalidOperation:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/unit/test_valor.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/extracao/valor.py backend/tests/unit/test_valor.py
git commit -m "feat: add valor extractor"
```

---

### Task 8: Extractor — data de pagamento

**Files:**
- Create: `backend/app/infrastructure/extracao/data.py`
- Test: `backend/tests/unit/test_data.py`

**Interfaces:**
- Produces: `extrair_data(texto: str) -> date | None`.

- [ ] **Step 1: Write the failing test**

`backend/tests/unit/test_data.py`:
```python
from datetime import date

from app.infrastructure.extracao.data import extrair_data


def test_extrai_data_com_barra():
    assert extrair_data("Data do pagamento: 15/03/2026") == date(2026, 3, 15)


def test_extrai_data_com_hifen():
    assert extrair_data("Pago em 31-12-2025") == date(2025, 12, 31)


def test_data_invalida_retorna_none():
    assert extrair_data("Data: 32/13/2026") is None


def test_texto_sem_data_retorna_none():
    assert extrair_data("Nenhuma data aqui.") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_data.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the extractor**

`backend/app/infrastructure/extracao/data.py`:
```python
import re
from datetime import date

_PADRAO_DATA = re.compile(r"(\d{2})[/-](\d{2})[/-](\d{4})")


def extrair_data(texto: str) -> date | None:
    match = _PADRAO_DATA.search(texto)
    if not match:
        return None
    dia, mes, ano = match.groups()
    try:
        return date(int(ano), int(mes), int(dia))
    except ValueError:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/unit/test_data.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/extracao/data.py backend/tests/unit/test_data.py
git commit -m "feat: add data de pagamento extractor"
```

---

### Task 9: Extractor — nomes do pagador e recebedor

**Files:**
- Create: `backend/app/infrastructure/extracao/nomes.py`
- Test: `backend/tests/unit/test_nomes.py`

**Interfaces:**
- Produces: `extrair_pagador(texto: str) -> str | None`, `extrair_recebedor(texto: str) -> str | None`.

- [ ] **Step 1: Write the failing test**

`backend/tests/unit/test_nomes.py`:
```python
from app.infrastructure.extracao.nomes import extrair_pagador, extrair_recebedor


def test_extrai_pagador_por_rotulo():
    texto = "Pagador: Joao da Silva Ltda\nValor: R$100,00"
    assert extrair_pagador(texto) == "JOAO DA SILVA"


def test_extrai_pagador_por_rotulo_de():
    texto = "De: Maria Souza ME\nData: 01/01/2026"
    assert extrair_pagador(texto) == "MARIA SOUZA"


def test_extrai_recebedor_por_rotulo_favorecido():
    texto = "Favorecido: Energisa S.A.\nBanco: Itaú"
    assert extrair_recebedor(texto) == "ENERGISA"


def test_extrai_recebedor_por_rotulo_para():
    texto = "Para: Claro S/A\nValor pago"
    assert extrair_recebedor(texto) == "CLARO"


def test_normaliza_espacos_multiplos():
    texto = "Pagador:   Joao    da   Silva\nOutro campo"
    assert extrair_pagador(texto) == "JOAO DA SILVA"


def test_sem_rotulo_retorna_none():
    assert extrair_pagador("Nenhum rótulo de pagador aqui.") is None
    assert extrair_recebedor("Nenhum rótulo de recebedor aqui.") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_nomes.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the extractor**

`backend/app/infrastructure/extracao/nomes.py`:
```python
import re

_ROTULOS_PAGADOR = ["PAGADOR", "DE"]
_ROTULOS_RECEBEDOR = ["RECEBEDOR", "FAVORECIDO", "PARA", "BENEFICIARIO", "BENEFICIÁRIO"]

_SUFIXOS_SOCIETARIOS = re.compile(
    r"\b(LTDA\.?|ME\.?|EIRELI\.?|S\.?A\.?|S/A)\b\.?", re.IGNORECASE
)


def _normalizar_nome(bruto: str) -> str:
    nome = bruto.strip()
    nome = re.sub(r"\s+", " ", nome)
    nome = _SUFIXOS_SOCIETARIOS.sub("", nome)
    nome = re.sub(r"\s+", " ", nome).strip()
    return nome.upper()


def _extrair_por_rotulos(texto: str, rotulos: list[str]) -> str | None:
    for rotulo in rotulos:
        padrao = re.compile(rf"{rotulo}\s*:\s*([^\n]+)", re.IGNORECASE)
        match = padrao.search(texto)
        if match:
            nome = _normalizar_nome(match.group(1))
            if nome:
                return nome
    return None


def extrair_pagador(texto: str) -> str | None:
    return _extrair_por_rotulos(texto, _ROTULOS_PAGADOR)


def extrair_recebedor(texto: str) -> str | None:
    return _extrair_por_rotulos(texto, _ROTULOS_RECEBEDOR)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/unit/test_nomes.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/extracao/nomes.py backend/tests/unit/test_nomes.py
git commit -m "feat: add pagador/recebedor name extractor"
```

---

### Task 10: Extractor — banco

**Files:**
- Create: `backend/app/infrastructure/extracao/banco.py`
- Test: `backend/tests/unit/test_banco.py`

**Interfaces:**
- Produces: `extrair_banco(texto: str) -> str | None`.

- [ ] **Step 1: Write the failing test**

`backend/tests/unit/test_banco.py`:
```python
from app.infrastructure.extracao.banco import extrair_banco


def test_extrai_itau():
    assert extrair_banco("Banco Itaú Unibanco S.A.") == "Itaú"


def test_extrai_bradesco_case_insensitive():
    assert extrair_banco("BRADESCO S.A. - Comprovante") == "Bradesco"


def test_extrai_nubank():
    assert extrair_banco("Comprovante Nubank") == "Nubank"


def test_sem_banco_conhecido_retorna_none():
    assert extrair_banco("Comprovante de um banco não listado") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_banco.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the extractor**

`backend/app/infrastructure/extracao/banco.py`:
```python
_BANCOS_CONHECIDOS = [
    ("ITAU", "Itaú"),
    ("ITAÚ", "Itaú"),
    ("BRADESCO", "Bradesco"),
    ("BANCO DO BRASIL", "Banco do Brasil"),
    ("CAIXA ECONOMICA", "Caixa Econômica Federal"),
    ("CAIXA ECONÔMICA", "Caixa Econômica Federal"),
    ("SANTANDER", "Santander"),
    ("NUBANK", "Nubank"),
    ("INTER", "Inter"),
    ("SICOOB", "Sicoob"),
    ("SICREDI", "Sicredi"),
    ("C6 BANK", "C6 Bank"),
]


def extrair_banco(texto: str) -> str | None:
    texto_upper = texto.upper()
    for busca, exibicao in _BANCOS_CONHECIDOS:
        if busca in texto_upper:
            return exibicao
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/unit/test_banco.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/extracao/banco.py backend/tests/unit/test_banco.py
git commit -m "feat: add banco extractor"
```

---

### Task 11: Pipeline aggregator

**Files:**
- Create: `backend/app/infrastructure/extracao/pipeline.py`
- Test: `backend/tests/unit/test_extracao_pipeline.py`

**Interfaces:**
- Consumes: `extrair_tipo_documento` (Task 5), `extrair_documentos` (Task 6), `extrair_valor` (Task 7), `extrair_data` (Task 8), `extrair_pagador`/`extrair_recebedor` (Task 9), `extrair_banco` (Task 10).
- Produces: `DadosExtraidos` dataclass (`pagador_nome`, `pagador_documento`, `recebedor_nome`, `recebedor_documento`, `valor`, `data_pagamento`, `tipo_documento`, `banco_nome`). `extrair_dados_documento(texto: str) -> DadosExtraidos` — a plain, picklable module-level function (this runs inside the same background worker process as the OCR pipeline; keep it free of I/O and non-picklable state, matching the `processar_documento` convention from Fase 1).

- [ ] **Step 1: Write the failing test**

`backend/tests/unit/test_extracao_pipeline.py`:
```python
from datetime import date
from decimal import Decimal

from app.domain.enums import TipoDocumento
from app.infrastructure.extracao.pipeline import extrair_dados_documento


def test_extrai_todos_os_campos_de_um_comprovante_completo():
    texto = (
        "Comprovante de Transferência PIX\n"
        "Pagador: Joao da Silva Ltda\n"
        "CPF: 123.456.789-00\n"
        "Favorecido: Energisa S.A.\n"
        "CNPJ: 12.345.678/0001-95\n"
        "Valor: R$ 1.234,56\n"
        "Data do pagamento: 15/03/2026\n"
        "Banco Itaú Unibanco\n"
    )

    dados = extrair_dados_documento(texto)

    assert dados.tipo_documento == TipoDocumento.PIX
    assert dados.pagador_nome == "JOAO DA SILVA"
    assert dados.pagador_documento == "12345678900"
    assert dados.recebedor_nome == "ENERGISA"
    assert dados.recebedor_documento == "12345678000195"
    assert dados.valor == Decimal("1234.56")
    assert dados.data_pagamento == date(2026, 3, 15)
    assert dados.banco_nome == "Itaú"


def test_campos_ausentes_ficam_none_e_tipo_fica_outro():
    dados = extrair_dados_documento("Texto sem nenhum campo reconhecível.")

    assert dados.tipo_documento == TipoDocumento.OUTRO
    assert dados.pagador_nome is None
    assert dados.pagador_documento is None
    assert dados.recebedor_nome is None
    assert dados.recebedor_documento is None
    assert dados.valor is None
    assert dados.data_pagamento is None
    assert dados.banco_nome is None


def test_apenas_um_documento_no_texto_vira_pagador_recebedor_fica_none():
    texto = "Pagador: Joao da Silva\nCPF: 123.456.789-00\nValor: R$50,00"

    dados = extrair_dados_documento(texto)

    assert dados.pagador_documento == "12345678900"
    assert dados.recebedor_documento is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_extracao_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the pipeline**

`backend/app/infrastructure/extracao/pipeline.py`:
```python
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.enums import TipoDocumento
from app.infrastructure.extracao.banco import extrair_banco
from app.infrastructure.extracao.data import extrair_data
from app.infrastructure.extracao.documento_fiscal import extrair_documentos
from app.infrastructure.extracao.nomes import extrair_pagador, extrair_recebedor
from app.infrastructure.extracao.tipo_documento import extrair_tipo_documento
from app.infrastructure.extracao.valor import extrair_valor


@dataclass
class DadosExtraidos:
    pagador_nome: str | None
    pagador_documento: str | None
    recebedor_nome: str | None
    recebedor_documento: str | None
    valor: Decimal | None
    data_pagamento: date | None
    tipo_documento: TipoDocumento
    banco_nome: str | None


def extrair_dados_documento(texto: str) -> DadosExtraidos:
    documentos = extrair_documentos(texto)
    return DadosExtraidos(
        pagador_nome=extrair_pagador(texto),
        pagador_documento=documentos[0] if documentos else None,
        recebedor_nome=extrair_recebedor(texto),
        recebedor_documento=documentos[1] if len(documentos) > 1 else None,
        valor=extrair_valor(texto),
        data_pagamento=extrair_data(texto),
        tipo_documento=extrair_tipo_documento(texto),
        banco_nome=extrair_banco(texto),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/unit/test_extracao_pipeline.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/infrastructure/extracao/pipeline.py backend/tests/unit/test_extracao_pipeline.py
git commit -m "feat: add extraction pipeline aggregator"
```

---

### Task 12: Wire extraction into the OCR background worker

**Files:**
- Modify: `backend/app/infrastructure/workers/lote_worker.py`
- Modify: `backend/tests/integration/test_lotes_api.py`

**Interfaces:**
- Consumes: `extrair_dados_documento`, `DadosExtraidos` (Task 11), `SqlAlchemyExtracaoRepository` (Task 4), `Extracao` (Task 2).
- Produces: no new public interface — `processar_lote_em_background` now also persists an `Extracao` row for every document that completes OCR successfully, before the document is marked `CONCLUIDO`.

**Current content of `backend/app/infrastructure/workers/lote_worker.py` you are modifying** (read the file yourself to confirm it still matches before editing — it may have changed since this plan was written):

The function `processar_lote_em_background` currently does, inside the `for futuro in as_completed(futuros):` loop, on success (`resultado_pipeline.erro` is falsy):
```python
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
```

- [ ] **Step 1: Write the failing integration test**

Add this test to `backend/tests/integration/test_lotes_api.py` (append it near `test_processar_lote_ate_concluir`, reusing the existing `client`/`empresa_id`/`ambiente` fixtures already defined in that file — read the file first to confirm their exact names/signatures before writing this):

```python
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
```

This test depends on Task 13's API changes (the `resultado["extracao"]` key) to fully pass — it's written now because it's the natural end-to-end proof this task's wiring works, but it will only go green once Task 13 lands too. Run it after Step 3 below and expect it to fail specifically on the `resultado["extracao"]` assertions (a `KeyError`), not on the lote/document processing itself — that distinction confirms the worker wiring in this task is correct even though the full test can't pass yet. Re-run it again after Task 13 and confirm it fully passes then (add that re-run as part of Task 13's verification, not this one).

- [ ] **Step 2: Run test to verify the worker-relevant part fails as expected**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/integration/test_lotes_api.py::test_processar_lote_extrai_dados_do_documento -v`
Expected: FAIL with `KeyError: 'extracao'` (the lote reaches `CONCLUIDO` fine — the failure is specifically that the resultado response doesn't have an `extracao` key yet, since Task 13 hasn't run).

- [ ] **Step 3: Wire extraction into the worker**

In `backend/app/infrastructure/workers/lote_worker.py`:

Add to the imports at the top:
```python
from app.domain.entities import Extracao, OcrResultado
```
(replacing the current `from app.domain.entities import OcrResultado` line)

Add:
```python
from app.infrastructure.extracao.pipeline import extrair_dados_documento
```
alongside the existing `from app.infrastructure.ocr.pipeline import processar_documento` import.

Inside `processar_lote_em_background`, add the extraction repository alongside the other repos already constructed at the top of the function body:
```python
        documento_repo = SqlAlchemyDocumentoRepository(session)
        resultado_repo = SqlAlchemyOcrResultadoRepository(session)
        lote_repo = SqlAlchemyLoteProcessamentoRepository(session)
        storage = LocalFileStorageService(Path(storage_root))
```
becomes:
```python
        documento_repo = SqlAlchemyDocumentoRepository(session)
        resultado_repo = SqlAlchemyOcrResultadoRepository(session)
        extracao_repo = SqlAlchemyExtracaoRepository(session)
        lote_repo = SqlAlchemyLoteProcessamentoRepository(session)
        storage = LocalFileStorageService(Path(storage_root))
```

Add the import for `SqlAlchemyExtracaoRepository` alongside the other function-level repository imports (the block starting with `from app.infrastructure.repositories.sqlalchemy_documento_repository import (`):
```python
    from app.infrastructure.repositories.sqlalchemy_extracao_repository import (
        SqlAlchemyExtracaoRepository,
    )
```

Change the success branch of the `as_completed` loop from:
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
                documento_repo.atualizar(documento)
```
to:
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
                    extracao_repo.criar(
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
                documento_repo.atualizar(documento)
```

Note: this placement means an exception inside `extrair_dados_documento` (which shouldn't normally happen, since every extractor is a pure regex function with no I/O, but a truly malformed/huge text could theoretically be slow or hit a regex edge case) is caught by the SAME outer `try/except Exception` that already wraps the whole worker body and drives the lote to `FALHOU` — consistent with this plan's global constraint that extraction failures must not crash the batch silently. Do not add a second, narrower try/except around just the extraction call; that would be inconsistent with how OCR failures are already handled (they set the document to `ERRO` and continue, but extraction failures are a different, much-lower-probability class of failure — a fully-implemented pure-function pipeline blowing up is closer to a bug than an expected outcome, so falling through to the batch-level `FALHOU` handling is the right severity).

- [ ] **Step 4: Run the test to verify it still fails only on the `extracao` key**

Run: `.venv/Scripts/python -m pytest tests/integration/test_lotes_api.py::test_processar_lote_extrai_dados_do_documento -v`
Expected: still FAIL with `KeyError: 'extracao'` — the worker now creates the `Extracao` row (verify this by adding a temporary print or by trusting Step 6 below, which checks the DB directly), but the API response won't include it until Task 13.

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all previously-passing tests still pass; the new test fails only as described above (this is expected and acceptable at this point in the plan).

- [ ] **Step 6: Commit**

```bash
git add backend/app/infrastructure/workers/lote_worker.py backend/tests/integration/test_lotes_api.py
git commit -m "feat: run field extraction after OCR success in the background worker"
```

---

### Task 13: Extend `GET /documentos/{id}/resultado` with extracted fields

**Files:**
- Modify: `backend/app/api/schemas/documento_schemas.py`
- Modify: `backend/app/api/routers/documentos_router.py`
- Modify: `backend/app/application/use_cases/documento_use_cases.py`
- Test: `backend/tests/unit/test_documento_use_cases.py`
- Test: `backend/tests/integration/test_documentos_api.py`

**Interfaces:**
- Consumes: `ExtracaoRepository` (Task 3), `SqlAlchemyExtracaoRepository` (Task 4), `Extracao` (Task 2).
- Produces: `ExtracaoOut` Pydantic schema (serializes `None` fields as the string `"NÃO IDENTIFICADO"`, except `tipo_documento` which is never `None`). `ObterResultadoUseCase.executar` now returns a 3-tuple `tuple[Documento, OcrResultado | None, Extracao | None]` (was a 2-tuple) — this is a breaking signature change to an existing use case; update its one call site in `documentos_router.py` accordingly.

- [ ] **Step 1: Write the failing unit test for the use case signature change**

In `backend/tests/unit/test_documento_use_cases.py`, first update the EXISTING test
`test_obter_resultado_documento_inexistente_falha` — its current body is:
```python
def test_obter_resultado_documento_inexistente_falha():
    documento_repo = FakeDocumentoRepository()
    resultado_repo = FakeOcrResultadoRepository()

    with pytest.raises(DocumentoNaoEncontrado):
        ObterResultadoUseCase(documento_repo, resultado_repo).executar(999)
```
Change it to also construct a `FakeExtracaoRepository` and pass it as the third constructor
argument, since `ObterResultadoUseCase.__init__` is about to require it:
```python
def test_obter_resultado_documento_inexistente_falha():
    documento_repo = FakeDocumentoRepository()
    resultado_repo = FakeOcrResultadoRepository()
    extracao_repo = FakeExtracaoRepository()

    with pytest.raises(DocumentoNaoEncontrado):
        ObterResultadoUseCase(documento_repo, resultado_repo, extracao_repo).executar(999)
```

Then add these two NEW tests near it:

```python
def test_obter_resultado_retorna_extracao_quando_existe():
    documento_repo = FakeDocumentoRepository()
    resultado_repo = FakeOcrResultadoRepository()
    extracao_repo = FakeExtracaoRepository()
    empresa_repo = FakeEmpresaRepository()
    empresa = _empresa(empresa_repo)
    storage = FakeArmazenamentoArquivos()
    resultados_upload = UploadarDocumentosUseCase(documento_repo, empresa_repo, storage).executar(
        empresa.id, [ArquivoUploadDTO(nome_original="a.pdf", conteudo=b"x")]
    )
    documento_id = resultados_upload[0].documento.id
    extracao_repo.criar(
        Extracao(
            id=None, documento_id=documento_id, pagador_nome="JOAO", pagador_documento=None,
            recebedor_nome=None, recebedor_documento=None, valor=None,
            data_pagamento=None, tipo_documento=TipoDocumento.OUTRO, banco_nome=None,
        )
    )

    documento, resultado, extracao = ObterResultadoUseCase(
        documento_repo, resultado_repo, extracao_repo
    ).executar(documento_id)

    assert resultado is None
    assert extracao is not None
    assert extracao.pagador_nome == "JOAO"


def test_obter_resultado_extracao_none_quando_nao_existe():
    documento_repo = FakeDocumentoRepository()
    resultado_repo = FakeOcrResultadoRepository()
    extracao_repo = FakeExtracaoRepository()
    empresa_repo = FakeEmpresaRepository()
    empresa = _empresa(empresa_repo)
    storage = FakeArmazenamentoArquivos()
    resultados_upload = UploadarDocumentosUseCase(documento_repo, empresa_repo, storage).executar(
        empresa.id, [ArquivoUploadDTO(nome_original="a.pdf", conteudo=b"x")]
    )
    documento_id = resultados_upload[0].documento.id

    _, _, extracao = ObterResultadoUseCase(documento_repo, resultado_repo, extracao_repo).executar(
        documento_id
    )

    assert extracao is None
```

Add `FakeExtracaoRepository` and `Extracao`, `TipoDocumento` to this test file's imports (check the current top of `test_documento_use_cases.py` for the exact existing import lines and merge these in — do not duplicate an existing `from tests.fakes import (...)` line, extend it).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_documento_use_cases.py -v`
Expected: FAIL — `ObterResultadoUseCase.__init__` doesn't accept a third argument yet.

- [ ] **Step 3: Update `ObterResultadoUseCase`**

In `backend/app/application/use_cases/documento_use_cases.py`, update the top import from:
```python
from app.application.repositories import (
    DocumentoRepository,
    EmpresaRepository,
    OcrResultadoRepository,
)
```
to:
```python
from app.application.repositories import (
    DocumentoRepository,
    EmpresaRepository,
    ExtracaoRepository,
    OcrResultadoRepository,
)
```
and:
```python
from app.domain.entities import Documento, OcrResultado
```
to:
```python
from app.domain.entities import Documento, Extracao, OcrResultado
```

Replace the `ObterResultadoUseCase` class with:
```python
class ObterResultadoUseCase:
    def __init__(
        self,
        documento_repo: DocumentoRepository,
        resultado_repo: OcrResultadoRepository,
        extracao_repo: ExtracaoRepository,
    ):
        self._documento_repo = documento_repo
        self._resultado_repo = resultado_repo
        self._extracao_repo = extracao_repo

    def executar(self, documento_id: int) -> tuple[Documento, OcrResultado | None, Extracao | None]:
        documento = self._documento_repo.obter_por_id(documento_id)
        if documento is None:
            raise DocumentoNaoEncontrado(documento_id)
        resultado = self._resultado_repo.obter_por_documento_id(documento_id)
        extracao = self._extracao_repo.obter_por_documento_id(documento_id)
        return documento, resultado, extracao
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/unit/test_documento_use_cases.py -v`
Expected: PASS.

- [ ] **Step 5: Add the `ExtracaoOut` schema**

In `backend/app/api/schemas/documento_schemas.py`, update the top import from:
```python
from app.domain.enums import MetodoOcr, StatusDocumento
```
to:
```python
from app.domain.enums import MetodoOcr, StatusDocumento, TipoDocumento
```

Add, before `DocumentoResultadoOut`:
```python
_NAO_IDENTIFICADO = "NÃO IDENTIFICADO"


class ExtracaoOut(BaseModel):
    pagador_nome: str
    pagador_documento: str
    recebedor_nome: str
    recebedor_documento: str
    valor: str
    data_pagamento: str
    tipo_documento: TipoDocumento
    banco_nome: str

    @classmethod
    def from_extracao(cls, extracao) -> "ExtracaoOut":
        return cls(
            pagador_nome=extracao.pagador_nome or _NAO_IDENTIFICADO,
            pagador_documento=extracao.pagador_documento or _NAO_IDENTIFICADO,
            recebedor_nome=extracao.recebedor_nome or _NAO_IDENTIFICADO,
            recebedor_documento=extracao.recebedor_documento or _NAO_IDENTIFICADO,
            valor=str(extracao.valor) if extracao.valor is not None else _NAO_IDENTIFICADO,
            data_pagamento=(
                extracao.data_pagamento.isoformat()
                if extracao.data_pagamento is not None
                else _NAO_IDENTIFICADO
            ),
            tipo_documento=extracao.tipo_documento,
            banco_nome=extracao.banco_nome or _NAO_IDENTIFICADO,
        )
```

Update `DocumentoResultadoOut` from:
```python
class DocumentoResultadoOut(BaseModel):
    documento: DocumentoOut
    resultado: OcrResultadoOut | None
```
to:
```python
class DocumentoResultadoOut(BaseModel):
    documento: DocumentoOut
    resultado: OcrResultadoOut | None
    extracao: ExtracaoOut | None
```

Design note on `valor`/`data_pagamento` being serialized as `str` rather than `Decimal`/`date`: this keeps the "NÃO IDENTIFICADO" sentinel representable in the same field without a union type on the wire, matching how the design spec describes the API-layer translation. The frontend (Task 14) treats these as display strings, not as values to compute with — this phase has no feature that does arithmetic on the extracted amount.

- [ ] **Step 6: Update the router**

In `backend/app/api/routers/documentos_router.py`, add to the imports:
```python
from app.api.schemas.documento_schemas import (
    DocumentoOut,
    DocumentoResultadoOut,
    ExtracaoOut,
    OcrResultadoOut,
    UploadItemOut,
)
```
(replacing the current shorter import block) and:
```python
from app.infrastructure.repositories.sqlalchemy_extracao_repository import (
    SqlAlchemyExtracaoRepository,
)
```

Replace the `obter_resultado` function with:
```python
@router.get("/documentos/{documento_id}/resultado", response_model=DocumentoResultadoOut)
def obter_resultado(documento_id: int, db: Session = Depends(get_db)):
    documento_repo = SqlAlchemyDocumentoRepository(db)
    resultado_repo = SqlAlchemyOcrResultadoRepository(db)
    extracao_repo = SqlAlchemyExtracaoRepository(db)
    try:
        documento, resultado, extracao = ObterResultadoUseCase(
            documento_repo, resultado_repo, extracao_repo
        ).executar(documento_id)
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
    extracao_out = ExtracaoOut.from_extracao(extracao) if extracao else None
    return DocumentoResultadoOut(documento=documento, resultado=resultado_out, extracao=extracao_out)
```

- [ ] **Step 7: Update the integration test**

In `backend/tests/integration/test_documentos_api.py`, find the existing test that asserts on `GET /documentos/{id}/resultado` for a freshly-uploaded (not-yet-processed) document, and add an assertion that the response includes `"extracao": None` (the field exists and is null, since no `Extracao` row has been created yet for a document that hasn't gone through the worker) — read the existing test first and add the assertion as a natural extension of it, e.g.:
```python
    assert body["extracao"] is None
```

- [ ] **Step 8: Run the previously-deferred Task 12 integration test**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/integration/test_lotes_api.py::test_processar_lote_extrai_dados_do_documento -v`
Expected: PASS now (this is the test written in Task 12 that could only partially pass until this task landed).

- [ ] **Step 9: Run the full suite**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add backend/app/api/schemas/documento_schemas.py backend/app/api/routers/documentos_router.py backend/app/application/use_cases/documento_use_cases.py backend/tests/unit/test_documento_use_cases.py backend/tests/integration/test_documentos_api.py
git commit -m "feat: expose extracted fields via GET /documentos/{id}/resultado"
```

---

### Task 14: Frontend — display extracted fields + manual verification

**Files:**
- Modify: `frontend/src/types/documento.ts`
- Modify: `frontend/src/components/DocumentoList.tsx`

**Interfaces:**
- Consumes: `ExtracaoOut` shape (Task 13).
- Produces: `Extracao` TS interface. `DocumentoResultado.extracao: Extracao | null`.

- [ ] **Step 1: Add the type**

In `frontend/src/types/documento.ts`, add near the top (after the existing type unions):
```ts
export type TipoDocumento = "PIX" | "TED" | "DOC" | "BOLETO" | "OUTRO";
```

Add, after `OcrResultadoDetalhe`:
```ts
export interface Extracao {
  pagador_nome: string;
  pagador_documento: string;
  recebedor_nome: string;
  recebedor_documento: string;
  valor: string;
  data_pagamento: string;
  tipo_documento: TipoDocumento;
  banco_nome: string;
}
```

Update `DocumentoResultado` from:
```ts
export interface DocumentoResultado {
  documento: Documento;
  resultado: OcrResultadoDetalhe | null;
}
```
to:
```ts
export interface DocumentoResultado {
  documento: Documento;
  resultado: OcrResultadoDetalhe | null;
  extracao: Extracao | null;
}
```

- [ ] **Step 2: Render the extracted fields**

In `frontend/src/components/DocumentoList.tsx`, replace the block that renders `resultadoAberto` (currently just the método + `texto_extraido`) with:
```tsx
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
          <p className="mb-1 font-semibold">
            Método: {resultadoAberto.resultado?.metodo} (
            {resultadoAberto.resultado?.tempo_processamento_ms}ms)
          </p>
          <pre className="whitespace-pre-wrap">{resultadoAberto.resultado?.texto_extraido}</pre>
        </div>
      )}
```

- [ ] **Step 3: Verify types and build**

Run: `cd "D:/DEV/Teste Lançamentos/frontend" && npx tsc --noEmit && npm run build`
Expected: both succeed.

- [ ] **Step 4: Run the full backend suite once more**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest -v`
Expected: all pass. This is the complete Fase 2 backend + frontend.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/documento.ts frontend/src/components/DocumentoList.tsx
git commit -m "feat: display extracted document fields in the results panel"
```

- [ ] **Step 6: Manual end-to-end verification (performed by the controller with browser tooling, not by an implementer subagent without one)**

With the backend running (`uvicorn app.main:app --reload` from `backend/`, after `alembic upgrade head`) and frontend running (`npm run dev` from `frontend/`):
1. Open `http://localhost:5173`, select or create an empresa.
2. Upload a real PDF comprovante with embedded, searchable text that includes at least a value, a date, and a payer/payee label (e.g. a synthetic test PDF built the same way Fase 1's manual verification did, via a short PyMuPDF script, with text like `"Pagador: Empresa Teste Ltda\nCPF: 123.456.789-00\nFavorecido: Fornecedor Exemplo\nValor: R$ 500,00\nData do pagamento: 01/06/2026"`).
3. Click "Processar", wait for `CONCLUIDO`.
4. Click "Ver texto" and confirm the extracted-fields grid shows the correct payer name, value, and date — and confirm any field NOT present in your test text (e.g. banco, if you didn't include a bank name) shows "NÃO IDENTIFICADO" rather than blank or `null`.
5. Confirm the raw OCR text still renders below the extracted-fields grid as before (Fase 1 behavior unchanged).

---

## Post-Plan Notes

- Fase 2 is complete when all 14 tasks are committed and the manual end-to-end verification in Task 14 Step 6 passes.
- The next spec (`Fase 3 — Motor de Regras + Busca Semântica`) should be brainstormed separately, following `superpowers:brainstorming`, and will consume the `extracoes` table's `pagador_nome`/`pagador_documento`/`recebedor_nome`/`recebedor_documento` fields as input to rule matching, plus `documentos.nome_exibicao`, which per the Fase 1 design should be updated to a "Tipo - Data" format once these fields exist — that rename was explicitly deferred to "whenever Fase 2 lands," so it is now in-scope to revisit as an early task of Fase 3, not this plan (keeping this plan's scope to extraction/storage only, per the approved design spec).
