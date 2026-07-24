# Fase 0 — Fundação — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundation of the payment-receipt classification system: database schema (including stub tables for future phases), a Clean Architecture backend (domain/application/infrastructure/api) exposing full CRUD for Empresas and Plano de Contas — including spreadsheet import with automatic column detection — and a minimal React frontend to exercise it end to end.

**Architecture:** Clean Architecture / Repository Pattern. `domain` holds framework-free entities and enums. `application/use_cases` holds business logic, depending only on abstract repository interfaces (`application/repositories.py`). `infrastructure` provides SQLAlchemy models and concrete repository implementations, plus the spreadsheet parser. `api` wires FastAPI routers to use cases via dependency injection. This lets use cases be unit-tested with in-memory fake repositories, with no database required.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (declarative), Alembic, Pydantic v2, pytest, httpx (FastAPI `TestClient`), openpyxl (xlsx), stdlib `csv` and `difflib` (fuzzy matching — no extra dependency). Frontend: React 18, TypeScript, Vite, TailwindCSS, shadcn/ui. Database: SQLite (file-based) in this phase.

## Global Constraints

- No paid services anywhere in this phase (spec: 2026-07-24-fase0-fundacao-design.md, "Decisões de contexto").
- No authentication in this phase.
- Runs locally on Windows via terminal, no Docker.
- SQLite now, all schema choices must stay portable to PostgreSQL (portable column types, no SQLite-only features).
- Only `codigo` and `descricao` are required fields when importing a Plano de Contas; if column detection can't identify them with confidence, the import must fail with a clear message — never silently guess.
- Only *contas analíticas* (leaf accounts) may be used in lançamentos — this is a domain validation rule, enforced now even though nothing consumes it yet.
- Every stub table (`documentos`, `ocr_resultados`, `extracoes`, `classificacoes`, `aprendizado`, `historico_alteracoes`, `usuarios`, `logs`, `configuracoes`) must exist in the schema via migration, with no use cases/endpoints built on top of them yet.

---

## File Structure

```
backend/
  requirements.txt
  alembic.ini
  app/
    __init__.py
    main.py
    core/
      __init__.py
      config.py
      exceptions.py
    domain/
      __init__.py
      enums.py
      entities.py
    application/
      __init__.py
      repositories.py
      dto.py
      use_cases/
        __init__.py
        empresa_use_cases.py
        plano_contas_use_cases.py
        conta_use_cases.py
        importar_plano_contas_use_cases.py
    infrastructure/
      __init__.py
      db/
        __init__.py
        base.py
        models.py
        session.py
      repositories/
        __init__.py
        sqlalchemy_empresa_repository.py
        sqlalchemy_plano_contas_repository.py
        sqlalchemy_conta_repository.py
      spreadsheet/
        __init__.py
        column_detector.py
        plano_contas_parser.py
    api/
      __init__.py
      deps.py
      schemas/
        __init__.py
        empresa_schemas.py
        plano_contas_schemas.py
        conta_schemas.py
        import_schemas.py
      routers/
        __init__.py
        empresas_router.py
        planos_contas_router.py
        contas_router.py
  alembic/
    env.py
    script.py.mako
    versions/
      0001_initial_schema.py
  tests/
    __init__.py
    conftest.py
    fakes.py
    unit/
      __init__.py
      test_empresa_use_cases.py
      test_conta_domain.py
      test_plano_contas_use_cases.py
      test_conta_use_cases.py
      test_column_detector.py
    integration/
      __init__.py
      test_plano_contas_parser.py
      test_empresas_api.py
      test_planos_contas_api.py
      fixtures/
        plano_contas_padrao.csv
        plano_contas_variante.csv
frontend/
  package.json
  tsconfig.json
  vite.config.ts
  tailwind.config.js
  postcss.config.js
  index.html
  src/
    main.tsx
    App.tsx
    index.css
    api/
      client.ts
    types/
      empresa.ts
      planoContas.ts
    pages/
      EmpresasPage.tsx
    components/
      EmpresaForm.tsx
      EmpresaList.tsx
      PlanoContasImport.tsx
      ContasTree.tsx
```

---

### Task 1: Backend project scaffolding

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/main.py`
- Test: `backend/tests/__init__.py`
- Test: `backend/tests/integration/__init__.py`
- Test: `backend/tests/integration/test_health.py`

**Interfaces:**
- Produces: `app.core.config.Settings` class with attribute `database_url: str`, and a module-level `settings = Settings()` instance. `app.main.app` — the FastAPI application instance.

- [ ] **Step 1: Create the backend folder and virtual environment**

```bash
mkdir -p backend/app/core
mkdir -p backend/tests/integration
cd backend
python -m venv .venv
```

- [ ] **Step 2: Write requirements.txt**

`backend/requirements.txt`:
```
fastapi==0.115.0
uvicorn[standard]==0.32.0
sqlalchemy==2.0.35
alembic==1.13.3
pydantic==2.9.2
pydantic-settings==2.5.2
python-multipart==0.0.12
openpyxl==3.1.5
pytest==8.3.3
httpx==0.27.2
```

- [ ] **Step 3: Install dependencies**

```bash
cd backend
.venv/Scripts/pip install -r requirements.txt
```
Expected: all packages install with no errors.

- [ ] **Step 4: Write config.py**

`backend/app/core/config.py`:
```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./fase0.db"
    app_name: str = "Classificador de Comprovantes"


settings = Settings()
```

- [ ] **Step 5: Write main.py with a health check endpoint**

`backend/app/main.py`:
```python
from fastapi import FastAPI

from app.core.config import settings

app = FastAPI(title=settings.app_name)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 6: Write the failing test for the health endpoint**

`backend/tests/integration/test_health.py`:
```python
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

`backend/tests/__init__.py` and `backend/tests/integration/__init__.py`: empty files.

- [ ] **Step 7: Run the test to verify it passes**

Run (from `backend/`): `.venv/Scripts/python -m pytest tests/integration/test_health.py -v`
Expected: PASS (this endpoint already exists, so this test should pass immediately — it establishes the test harness works).

- [ ] **Step 8: Commit**

```bash
git add backend/requirements.txt backend/app backend/tests
git commit -m "chore: scaffold FastAPI backend with health check"
```

---

### Task 2: Domain entities and enums

**Files:**
- Create: `backend/app/domain/__init__.py`
- Create: `backend/app/domain/enums.py`
- Create: `backend/app/domain/entities.py`
- Test: `backend/tests/unit/__init__.py`
- Test: `backend/tests/unit/test_conta_domain.py`

**Interfaces:**
- Produces: `NaturezaConta` enum (`ATIVO`, `PASSIVO`, `RECEITA`, `DESPESA`, `PATRIMONIO_LIQUIDO`). `Empresa`, `PlanoContas`, `Conta` dataclasses. `Conta.validar_uso_em_lancamento() -> None`, raising `ValueError` if `conta_analitica` is `False`.

- [ ] **Step 1: Write the failing test**

`backend/tests/unit/test_conta_domain.py`:
```python
import pytest

from app.domain.entities import Conta
from app.domain.enums import NaturezaConta


def test_conta_analitica_pode_ser_usada_em_lancamento():
    conta = Conta(
        id=1,
        plano_conta_id=1,
        codigo="1.1.01",
        descricao="Caixa",
        natureza=NaturezaConta.ATIVO,
        conta_analitica=True,
        conta_pai_id=None,
    )
    conta.validar_uso_em_lancamento()  # não deve levantar exceção


def test_conta_sintetica_nao_pode_ser_usada_em_lancamento():
    conta = Conta(
        id=1,
        plano_conta_id=1,
        codigo="1.1",
        descricao="Disponibilidades",
        natureza=NaturezaConta.ATIVO,
        conta_analitica=False,
        conta_pai_id=None,
    )
    with pytest.raises(ValueError, match="conta sintética"):
        conta.validar_uso_em_lancamento()
```

`backend/tests/unit/__init__.py`: empty file.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/unit/test_conta_domain.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.domain'`

- [ ] **Step 3: Write enums.py**

`backend/app/domain/enums.py`:
```python
from enum import Enum


class NaturezaConta(str, Enum):
    ATIVO = "ATIVO"
    PASSIVO = "PASSIVO"
    RECEITA = "RECEITA"
    DESPESA = "DESPESA"
    PATRIMONIO_LIQUIDO = "PATRIMONIO_LIQUIDO"
```

- [ ] **Step 4: Write entities.py**

`backend/app/domain/entities.py`:
```python
from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import NaturezaConta


@dataclass
class Empresa:
    id: int | None
    razao_social: str
    nome_fantasia: str | None
    cnpj: str
    ativo: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class PlanoContas:
    id: int | None
    empresa_id: int
    nome: str
    versao: int = 1
    ativo: bool = True
    created_at: datetime | None = None


@dataclass
class Conta:
    id: int | None
    plano_conta_id: int
    codigo: str
    descricao: str
    natureza: NaturezaConta
    conta_analitica: bool
    conta_pai_id: int | None = None

    def validar_uso_em_lancamento(self) -> None:
        if not self.conta_analitica:
            raise ValueError(
                f"Conta {self.codigo} é uma conta sintética e não pode ser usada em lançamentos."
            )
```

`backend/app/domain/__init__.py`: empty file.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/unit/test_conta_domain.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/app/domain backend/tests/unit
git commit -m "feat: add domain entities and NaturezaConta enum"
```

---

### Task 3: SQLAlchemy models, DB session, and Alembic migration

**Files:**
- Create: `backend/app/infrastructure/__init__.py`
- Create: `backend/app/infrastructure/db/__init__.py`
- Create: `backend/app/infrastructure/db/base.py`
- Create: `backend/app/infrastructure/db/models.py`
- Create: `backend/app/infrastructure/db/session.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/0001_initial_schema.py`
- Test: `backend/tests/integration/test_schema_migration.py`

**Interfaces:**
- Produces: `Base` (declarative base) in `app.infrastructure.db.base`. `EmpresaModel`, `PlanoContasModel`, `ContaModel`, and stub models `DocumentoModel`, `OcrResultadoModel`, `ExtracaoModel`, `ClassificacaoModel`, `AprendizadoModel`, `HistoricoAlteracaoModel`, `UsuarioModel`, `LogModel`, `ConfiguracaoModel` in `app.infrastructure.db.models`. `get_engine(database_url: str)` and `SessionLocal` factory in `app.infrastructure.db.session`.

- [ ] **Step 1: Write base.py**

`backend/app/infrastructure/db/base.py`:
```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

- [ ] **Step 2: Write models.py**

`backend/app/infrastructure/db/models.py`:
```python
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import NaturezaConta
from app.infrastructure.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EmpresaModel(Base):
    __tablename__ = "empresas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    razao_social: Mapped[str] = mapped_column(String(255), nullable=False)
    nome_fantasia: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cnpj: Mapped[str] = mapped_column(String(14), unique=True, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now, nullable=False
    )

    planos_contas: Mapped[list["PlanoContasModel"]] = relationship(
        back_populates="empresa"
    )


class PlanoContasModel(Base):
    __tablename__ = "planos_contas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    versao: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

    empresa: Mapped["EmpresaModel"] = relationship(back_populates="planos_contas")
    contas: Mapped[list["ContaModel"]] = relationship(back_populates="plano_contas")


class ContaModel(Base):
    __tablename__ = "contas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plano_conta_id: Mapped[int] = mapped_column(
        ForeignKey("planos_contas.id"), nullable=False
    )
    codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    descricao: Mapped[str] = mapped_column(String(255), nullable=False)
    natureza: Mapped[NaturezaConta] = mapped_column(
        String(20), nullable=False
    )
    conta_analitica: Mapped[bool] = mapped_column(Boolean, nullable=False)
    conta_pai_id: Mapped[int | None] = mapped_column(
        ForeignKey("contas.id"), nullable=True
    )

    plano_contas: Mapped["PlanoContasModel"] = relationship(back_populates="contas")


class DocumentoModel(Base):
    __tablename__ = "documentos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)


class OcrResultadoModel(Base):
    __tablename__ = "ocr_resultados"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)


class ExtracaoModel(Base):
    __tablename__ = "extracoes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)


class ClassificacaoModel(Base):
    __tablename__ = "classificacoes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)


class AprendizadoModel(Base):
    __tablename__ = "aprendizado"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)


class HistoricoAlteracaoModel(Base):
    __tablename__ = "historico_alteracoes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)


class UsuarioModel(Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)


class LogModel(Base):
    __tablename__ = "logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int | None] = mapped_column(
        ForeignKey("empresas.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)


class ConfiguracaoModel(Base):
    __tablename__ = "configuracoes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int | None] = mapped_column(
        ForeignKey("empresas.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
```

- [ ] **Step 3: Write session.py**

`backend/app/infrastructure/db/session.py`:
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


def get_engine(database_url: str | None = None):
    url = database_url or settings.database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


engine = get_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
```

`backend/app/infrastructure/__init__.py` and `backend/app/infrastructure/db/__init__.py`: empty files.

- [ ] **Step 4: Initialize Alembic and configure it**

```bash
cd backend
.venv/Scripts/alembic init alembic
```

Replace `backend/alembic.ini` line `sqlalchemy.url = driver://user:pass@localhost/dbname` with:
```
sqlalchemy.url = sqlite:///./fase0.db
```

`backend/alembic/env.py` — replace the generated file's content with:
```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.infrastructure.db.base import Base
from app.infrastructure.db import models  # noqa: F401 (registers models on Base)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 5: Write the initial migration**

`backend/alembic/versions/0001_initial_schema.py`:
```python
"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "empresas",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("razao_social", sa.String(255), nullable=False),
        sa.Column("nome_fantasia", sa.String(255), nullable=True),
        sa.Column("cnpj", sa.String(14), nullable=False, unique=True),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "planos_contas",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("nome", sa.String(255), nullable=False),
        sa.Column("versao", sa.Integer, nullable=False, server_default="1"),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "contas",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "plano_conta_id", sa.Integer, sa.ForeignKey("planos_contas.id"), nullable=False
        ),
        sa.Column("codigo", sa.String(50), nullable=False),
        sa.Column("descricao", sa.String(255), nullable=False),
        sa.Column("natureza", sa.String(20), nullable=False),
        sa.Column("conta_analitica", sa.Boolean, nullable=False),
        sa.Column("conta_pai_id", sa.Integer, sa.ForeignKey("contas.id"), nullable=True),
    )

    for table_name in (
        "documentos",
        "ocr_resultados",
        "extracoes",
        "classificacoes",
        "aprendizado",
        "historico_alteracoes",
    ):
        op.create_table(
            table_name,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "empresa_id", sa.Integer, sa.ForeignKey("empresas.id"), nullable=False
            ),
            sa.Column("created_at", sa.DateTime, nullable=False),
        )

    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    for table_name in ("logs", "configuracoes"):
        op.create_table(
            table_name,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "empresa_id", sa.Integer, sa.ForeignKey("empresas.id"), nullable=True
            ),
            sa.Column("created_at", sa.DateTime, nullable=False),
        )


def downgrade() -> None:
    for table_name in (
        "configuracoes",
        "logs",
        "usuarios",
        "historico_alteracoes",
        "aprendizado",
        "classificacoes",
        "extracoes",
        "ocr_resultados",
        "documentos",
        "contas",
        "planos_contas",
        "empresas",
    ):
        op.drop_table(table_name)
```

Note: `backend/alembic/script.py.mako` is generated automatically by `alembic init` in Step 4 — do not overwrite it.

- [ ] **Step 6: Write the test that verifies migrations create all expected tables**

`backend/tests/integration/test_schema_migration.py`:
```python
from sqlalchemy import create_engine, inspect
from alembic import command
from alembic.config import Config


def test_migration_creates_all_tables(tmp_path):
    db_path = tmp_path / "test_migration.db"
    db_url = f"sqlite:///{db_path}"

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(db_url)
    tables = set(inspect(engine).get_table_names())

    expected = {
        "empresas", "planos_contas", "contas", "documentos", "ocr_resultados",
        "extracoes", "classificacoes", "aprendizado", "historico_alteracoes",
        "usuarios", "logs", "configuracoes", "alembic_version",
    }
    assert expected.issubset(tables)
```

- [ ] **Step 7: Run test to verify it fails, then run migration and re-test**

Run: `.venv/Scripts/python -m pytest tests/integration/test_schema_migration.py -v`
Expected first run: FAIL (`0001_initial_schema.py` not present yet is impossible since we wrote it in Step 5 — if it fails, it will be due to a syntax/import error; fix until this passes).
Then run: PASS, all 13 tables present.

- [ ] **Step 8: Commit**

```bash
git add backend/app/infrastructure/db backend/alembic backend/alembic.ini backend/tests/integration/test_schema_migration.py
git commit -m "feat: add SQLAlchemy models and initial Alembic migration"
```

---

### Task 4: Repository interfaces and in-memory fakes for testing

**Files:**
- Create: `backend/app/application/__init__.py`
- Create: `backend/app/application/repositories.py`
- Create: `backend/tests/fakes.py`

**Interfaces:**
- Consumes: `Empresa`, `PlanoContas`, `Conta` from `app.domain.entities` (Task 2).
- Produces: Abstract classes `EmpresaRepository`, `PlanoContasRepository`, `ContaRepository` with methods: `criar`, `obter_por_id`, `listar`, `atualizar` (Empresa/Conta only), `obter_por_cnpj` (Empresa only), `listar_por_plano` (Conta only), `listar_por_empresa` (PlanoContas only). Fakes: `FakeEmpresaRepository`, `FakePlanoContasRepository`, `FakeContaRepository` in `tests/fakes.py`, implementing the same interfaces in-memory.

- [ ] **Step 1: Write repositories.py (abstract interfaces)**

`backend/app/application/repositories.py`:
```python
from abc import ABC, abstractmethod

from app.domain.entities import Conta, Empresa, PlanoContas


class EmpresaRepository(ABC):
    @abstractmethod
    def criar(self, empresa: Empresa) -> Empresa: ...

    @abstractmethod
    def obter_por_id(self, empresa_id: int) -> Empresa | None: ...

    @abstractmethod
    def obter_por_cnpj(self, cnpj: str) -> Empresa | None: ...

    @abstractmethod
    def listar(self) -> list[Empresa]: ...

    @abstractmethod
    def atualizar(self, empresa: Empresa) -> Empresa: ...


class PlanoContasRepository(ABC):
    @abstractmethod
    def criar(self, plano: PlanoContas) -> PlanoContas: ...

    @abstractmethod
    def obter_por_id(self, plano_id: int) -> PlanoContas | None: ...

    @abstractmethod
    def listar_por_empresa(self, empresa_id: int) -> list[PlanoContas]: ...


class ContaRepository(ABC):
    @abstractmethod
    def criar(self, conta: Conta) -> Conta: ...

    @abstractmethod
    def criar_em_lote(self, contas: list[Conta]) -> list[Conta]: ...

    @abstractmethod
    def obter_por_id(self, conta_id: int) -> Conta | None: ...

    @abstractmethod
    def listar_por_plano(self, plano_conta_id: int) -> list[Conta]: ...

    @abstractmethod
    def atualizar(self, conta: Conta) -> Conta: ...

    @abstractmethod
    def deletar(self, conta_id: int) -> None: ...
```

`backend/app/application/__init__.py`: empty file.

- [ ] **Step 2: Write in-memory fakes for unit tests**

`backend/tests/fakes.py`:
```python
from app.application.repositories import (
    ContaRepository,
    EmpresaRepository,
    PlanoContasRepository,
)
from app.domain.entities import Conta, Empresa, PlanoContas


class FakeEmpresaRepository(EmpresaRepository):
    def __init__(self):
        self._items: dict[int, Empresa] = {}
        self._next_id = 1

    def criar(self, empresa: Empresa) -> Empresa:
        empresa.id = self._next_id
        self._items[self._next_id] = empresa
        self._next_id += 1
        return empresa

    def obter_por_id(self, empresa_id: int) -> Empresa | None:
        return self._items.get(empresa_id)

    def obter_por_cnpj(self, cnpj: str) -> Empresa | None:
        return next((e for e in self._items.values() if e.cnpj == cnpj), None)

    def listar(self) -> list[Empresa]:
        return list(self._items.values())

    def atualizar(self, empresa: Empresa) -> Empresa:
        self._items[empresa.id] = empresa
        return empresa


class FakePlanoContasRepository(PlanoContasRepository):
    def __init__(self):
        self._items: dict[int, PlanoContas] = {}
        self._next_id = 1

    def criar(self, plano: PlanoContas) -> PlanoContas:
        plano.id = self._next_id
        self._items[self._next_id] = plano
        self._next_id += 1
        return plano

    def obter_por_id(self, plano_id: int) -> PlanoContas | None:
        return self._items.get(plano_id)

    def listar_por_empresa(self, empresa_id: int) -> list[PlanoContas]:
        return [p for p in self._items.values() if p.empresa_id == empresa_id]


class FakeContaRepository(ContaRepository):
    def __init__(self):
        self._items: dict[int, Conta] = {}
        self._next_id = 1

    def criar(self, conta: Conta) -> Conta:
        conta.id = self._next_id
        self._items[self._next_id] = conta
        self._next_id += 1
        return conta

    def criar_em_lote(self, contas: list[Conta]) -> list[Conta]:
        return [self.criar(c) for c in contas]

    def obter_por_id(self, conta_id: int) -> Conta | None:
        return self._items.get(conta_id)

    def listar_por_plano(self, plano_conta_id: int) -> list[Conta]:
        return [c for c in self._items.values() if c.plano_conta_id == plano_conta_id]

    def atualizar(self, conta: Conta) -> Conta:
        self._items[conta.id] = conta
        return conta

    def deletar(self, conta_id: int) -> None:
        self._items.pop(conta_id, None)
```

- [ ] **Step 3: Verify the fakes satisfy the abstract interfaces**

Run: `.venv/Scripts/python -c "from tests.fakes import FakeEmpresaRepository, FakePlanoContasRepository, FakeContaRepository; FakeEmpresaRepository(); FakePlanoContasRepository(); FakeContaRepository(); print('ok')"`
Expected: prints `ok` with no `TypeError: Can't instantiate abstract class`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/application/repositories.py backend/app/application/__init__.py backend/tests/fakes.py
git commit -m "feat: add repository interfaces and in-memory fakes"
```

---

### Task 5: Empresa use cases

**Files:**
- Create: `backend/app/application/use_cases/__init__.py`
- Create: `backend/app/application/use_cases/empresa_use_cases.py`
- Create: `backend/app/application/dto.py`
- Test: `backend/tests/unit/test_empresa_use_cases.py`

**Interfaces:**
- Consumes: `EmpresaRepository` (Task 4), `Empresa` (Task 2), `FakeEmpresaRepository` (Task 4).
- Produces: DTOs `CriarEmpresaDTO(razao_social: str, nome_fantasia: str | None, cnpj: str)`, `AtualizarEmpresaDTO(razao_social: str, nome_fantasia: str | None, ativo: bool)` in `app.application.dto`. Use cases: `CriarEmpresaUseCase(repo).executar(dto: CriarEmpresaDTO) -> Empresa`, `ListarEmpresasUseCase(repo).executar() -> list[Empresa]`, `ObterEmpresaUseCase(repo).executar(empresa_id: int) -> Empresa`, `AtualizarEmpresaUseCase(repo).executar(empresa_id: int, dto: AtualizarEmpresaDTO) -> Empresa`, `DesativarEmpresaUseCase(repo).executar(empresa_id: int) -> None`. Raises `app.core.exceptions.EmpresaNaoEncontrada` and `app.core.exceptions.CnpjJaCadastrado`.

- [ ] **Step 1: Write core exceptions**

`backend/app/core/exceptions.py`:
```python
class DomainError(Exception):
    """Base class for domain/application errors."""


class EmpresaNaoEncontrada(DomainError):
    def __init__(self, empresa_id: int):
        super().__init__(f"Empresa {empresa_id} não encontrada.")


class CnpjJaCadastrado(DomainError):
    def __init__(self, cnpj: str):
        super().__init__(f"CNPJ {cnpj} já cadastrado.")


class PlanoContasNaoEncontrado(DomainError):
    def __init__(self, plano_id: int):
        super().__init__(f"Plano de Contas {plano_id} não encontrado.")


class ContaNaoEncontrada(DomainError):
    def __init__(self, conta_id: int):
        super().__init__(f"Conta {conta_id} não encontrada.")


class ImportacaoPlanoContasInvalida(DomainError):
    def __init__(self, motivo: str):
        super().__init__(motivo)
```

- [ ] **Step 2: Write the failing test**

`backend/tests/unit/test_empresa_use_cases.py`:
```python
import pytest

from app.application.dto import AtualizarEmpresaDTO, CriarEmpresaDTO
from app.application.use_cases.empresa_use_cases import (
    AtualizarEmpresaUseCase,
    CriarEmpresaUseCase,
    DesativarEmpresaUseCase,
    ListarEmpresasUseCase,
    ObterEmpresaUseCase,
)
from app.core.exceptions import CnpjJaCadastrado, EmpresaNaoEncontrada
from tests.fakes import FakeEmpresaRepository


def test_criar_empresa():
    repo = FakeEmpresaRepository()
    dto = CriarEmpresaDTO(razao_social="Tesserato Contabilidade", nome_fantasia="Tesserato", cnpj="12345678000199")

    empresa = CriarEmpresaUseCase(repo).executar(dto)

    assert empresa.id == 1
    assert empresa.razao_social == "Tesserato Contabilidade"
    assert empresa.ativo is True


def test_criar_empresa_com_cnpj_duplicado_falha():
    repo = FakeEmpresaRepository()
    dto = CriarEmpresaDTO(razao_social="A", nome_fantasia=None, cnpj="12345678000199")
    CriarEmpresaUseCase(repo).executar(dto)

    with pytest.raises(CnpjJaCadastrado):
        CriarEmpresaUseCase(repo).executar(dto)


def test_listar_empresas():
    repo = FakeEmpresaRepository()
    CriarEmpresaUseCase(repo).executar(CriarEmpresaDTO("A", None, "11111111000191"))
    CriarEmpresaUseCase(repo).executar(CriarEmpresaDTO("B", None, "22222222000192"))

    empresas = ListarEmpresasUseCase(repo).executar()

    assert len(empresas) == 2


def test_obter_empresa_inexistente_falha():
    repo = FakeEmpresaRepository()
    with pytest.raises(EmpresaNaoEncontrada):
        ObterEmpresaUseCase(repo).executar(999)


def test_atualizar_empresa():
    repo = FakeEmpresaRepository()
    empresa = CriarEmpresaUseCase(repo).executar(CriarEmpresaDTO("A", None, "11111111000191"))

    atualizada = AtualizarEmpresaUseCase(repo).executar(
        empresa.id, AtualizarEmpresaDTO(razao_social="A Ltda", nome_fantasia="A", ativo=True)
    )

    assert atualizada.razao_social == "A Ltda"
    assert atualizada.nome_fantasia == "A"


def test_desativar_empresa():
    repo = FakeEmpresaRepository()
    empresa = CriarEmpresaUseCase(repo).executar(CriarEmpresaDTO("A", None, "11111111000191"))

    DesativarEmpresaUseCase(repo).executar(empresa.id)

    assert repo.obter_por_id(empresa.id).ativo is False
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/unit/test_empresa_use_cases.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.application.dto'`

- [ ] **Step 4: Write dto.py**

`backend/app/application/dto.py`:
```python
from dataclasses import dataclass


@dataclass
class CriarEmpresaDTO:
    razao_social: str
    nome_fantasia: str | None
    cnpj: str


@dataclass
class AtualizarEmpresaDTO:
    razao_social: str
    nome_fantasia: str | None
    ativo: bool


@dataclass
class CriarPlanoContasDTO:
    nome: str


@dataclass
class CriarContaDTO:
    codigo: str
    descricao: str
    natureza: str
    conta_analitica: bool
    conta_pai_id: int | None = None


@dataclass
class AtualizarContaDTO:
    codigo: str
    descricao: str
    natureza: str
    conta_analitica: bool
    conta_pai_id: int | None = None
```

- [ ] **Step 5: Write empresa_use_cases.py**

`backend/app/application/use_cases/empresa_use_cases.py`:
```python
from app.application.dto import AtualizarEmpresaDTO, CriarEmpresaDTO
from app.application.repositories import EmpresaRepository
from app.core.exceptions import CnpjJaCadastrado, EmpresaNaoEncontrada
from app.domain.entities import Empresa


class CriarEmpresaUseCase:
    def __init__(self, repo: EmpresaRepository):
        self._repo = repo

    def executar(self, dto: CriarEmpresaDTO) -> Empresa:
        if self._repo.obter_por_cnpj(dto.cnpj) is not None:
            raise CnpjJaCadastrado(dto.cnpj)
        empresa = Empresa(
            id=None,
            razao_social=dto.razao_social,
            nome_fantasia=dto.nome_fantasia,
            cnpj=dto.cnpj,
        )
        return self._repo.criar(empresa)


class ListarEmpresasUseCase:
    def __init__(self, repo: EmpresaRepository):
        self._repo = repo

    def executar(self) -> list[Empresa]:
        return self._repo.listar()


class ObterEmpresaUseCase:
    def __init__(self, repo: EmpresaRepository):
        self._repo = repo

    def executar(self, empresa_id: int) -> Empresa:
        empresa = self._repo.obter_por_id(empresa_id)
        if empresa is None:
            raise EmpresaNaoEncontrada(empresa_id)
        return empresa


class AtualizarEmpresaUseCase:
    def __init__(self, repo: EmpresaRepository):
        self._repo = repo

    def executar(self, empresa_id: int, dto: AtualizarEmpresaDTO) -> Empresa:
        empresa = ObterEmpresaUseCase(self._repo).executar(empresa_id)
        empresa.razao_social = dto.razao_social
        empresa.nome_fantasia = dto.nome_fantasia
        empresa.ativo = dto.ativo
        return self._repo.atualizar(empresa)


class DesativarEmpresaUseCase:
    def __init__(self, repo: EmpresaRepository):
        self._repo = repo

    def executar(self, empresa_id: int) -> None:
        empresa = ObterEmpresaUseCase(self._repo).executar(empresa_id)
        empresa.ativo = False
        self._repo.atualizar(empresa)
```

`backend/app/application/use_cases/__init__.py`: empty file.

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/unit/test_empresa_use_cases.py -v`
Expected: PASS (6 passed)

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/exceptions.py backend/app/application/dto.py backend/app/application/use_cases
git commit -m "feat: add Empresa use cases"
```

---

### Task 6: SQLAlchemy repository implementations

**Files:**
- Create: `backend/app/infrastructure/repositories/__init__.py`
- Create: `backend/app/infrastructure/repositories/sqlalchemy_empresa_repository.py`
- Create: `backend/app/infrastructure/repositories/sqlalchemy_plano_contas_repository.py`
- Create: `backend/app/infrastructure/repositories/sqlalchemy_conta_repository.py`
- Test: `backend/tests/conftest.py`
- Test: `backend/tests/integration/test_sqlalchemy_repositories.py`

**Interfaces:**
- Consumes: `EmpresaRepository`, `PlanoContasRepository`, `ContaRepository` (Task 4), `EmpresaModel`, `PlanoContasModel`, `ContaModel` (Task 3).
- Produces: `SqlAlchemyEmpresaRepository(session)`, `SqlAlchemyPlanoContasRepository(session)`, `SqlAlchemyContaRepository(session)` — concrete implementations, one per abstract repository.

- [ ] **Step 1: Write conftest.py with an in-memory SQLite session fixture**

`backend/tests/conftest.py`:
```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.infrastructure.db.base import Base
from app.infrastructure.db import models  # noqa: F401


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
```

- [ ] **Step 2: Write the failing test**

`backend/tests/integration/test_sqlalchemy_repositories.py`:
```python
from app.domain.entities import Conta, Empresa, PlanoContas
from app.domain.enums import NaturezaConta
from app.infrastructure.repositories.sqlalchemy_conta_repository import (
    SqlAlchemyContaRepository,
)
from app.infrastructure.repositories.sqlalchemy_empresa_repository import (
    SqlAlchemyEmpresaRepository,
)
from app.infrastructure.repositories.sqlalchemy_plano_contas_repository import (
    SqlAlchemyPlanoContasRepository,
)


def test_criar_e_obter_empresa(db_session):
    repo = SqlAlchemyEmpresaRepository(db_session)
    empresa = Empresa(id=None, razao_social="Tesserato", nome_fantasia=None, cnpj="12345678000199")

    criada = repo.criar(empresa)
    db_session.commit()

    encontrada = repo.obter_por_id(criada.id)
    assert encontrada.razao_social == "Tesserato"
    assert encontrada.cnpj == "12345678000199"


def test_obter_empresa_por_cnpj(db_session):
    repo = SqlAlchemyEmpresaRepository(db_session)
    repo.criar(Empresa(id=None, razao_social="Tesserato", nome_fantasia=None, cnpj="12345678000199"))
    db_session.commit()

    encontrada = repo.obter_por_cnpj("12345678000199")
    assert encontrada is not None


def test_criar_plano_contas_e_contas_com_hierarquia(db_session):
    empresa_repo = SqlAlchemyEmpresaRepository(db_session)
    empresa = empresa_repo.criar(
        Empresa(id=None, razao_social="Tesserato", nome_fantasia=None, cnpj="12345678000199")
    )
    db_session.commit()

    plano_repo = SqlAlchemyPlanoContasRepository(db_session)
    plano = plano_repo.criar(PlanoContas(id=None, empresa_id=empresa.id, nome="Plano Padrão"))
    db_session.commit()

    conta_repo = SqlAlchemyContaRepository(db_session)
    pai = conta_repo.criar(
        Conta(
            id=None, plano_conta_id=plano.id, codigo="1.1", descricao="Disponibilidades",
            natureza=NaturezaConta.ATIVO, conta_analitica=False,
        )
    )
    db_session.commit()
    filha = conta_repo.criar(
        Conta(
            id=None, plano_conta_id=plano.id, codigo="1.1.01", descricao="Caixa",
            natureza=NaturezaConta.ATIVO, conta_analitica=True, conta_pai_id=pai.id,
        )
    )
    db_session.commit()

    contas = conta_repo.listar_por_plano(plano.id)
    assert len(contas) == 2
    assert filha.conta_pai_id == pai.id
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/integration/test_sqlalchemy_repositories.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.infrastructure.repositories'`

- [ ] **Step 4: Write sqlalchemy_empresa_repository.py**

`backend/app/infrastructure/repositories/sqlalchemy_empresa_repository.py`:
```python
from sqlalchemy.orm import Session

from app.application.repositories import EmpresaRepository
from app.domain.entities import Empresa
from app.infrastructure.db.models import EmpresaModel


def _to_entity(model: EmpresaModel) -> Empresa:
    return Empresa(
        id=model.id,
        razao_social=model.razao_social,
        nome_fantasia=model.nome_fantasia,
        cnpj=model.cnpj,
        ativo=model.ativo,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlAlchemyEmpresaRepository(EmpresaRepository):
    def __init__(self, session: Session):
        self._session = session

    def criar(self, empresa: Empresa) -> Empresa:
        model = EmpresaModel(
            razao_social=empresa.razao_social,
            nome_fantasia=empresa.nome_fantasia,
            cnpj=empresa.cnpj,
            ativo=empresa.ativo,
        )
        self._session.add(model)
        self._session.flush()
        return _to_entity(model)

    def obter_por_id(self, empresa_id: int) -> Empresa | None:
        model = self._session.get(EmpresaModel, empresa_id)
        return _to_entity(model) if model else None

    def obter_por_cnpj(self, cnpj: str) -> Empresa | None:
        model = self._session.query(EmpresaModel).filter_by(cnpj=cnpj).first()
        return _to_entity(model) if model else None

    def listar(self) -> list[Empresa]:
        return [_to_entity(m) for m in self._session.query(EmpresaModel).all()]

    def atualizar(self, empresa: Empresa) -> Empresa:
        model = self._session.get(EmpresaModel, empresa.id)
        model.razao_social = empresa.razao_social
        model.nome_fantasia = empresa.nome_fantasia
        model.ativo = empresa.ativo
        self._session.flush()
        return _to_entity(model)
```

`backend/app/infrastructure/repositories/__init__.py`: empty file.

- [ ] **Step 5: Write sqlalchemy_plano_contas_repository.py**

`backend/app/infrastructure/repositories/sqlalchemy_plano_contas_repository.py`:
```python
from sqlalchemy.orm import Session

from app.application.repositories import PlanoContasRepository
from app.domain.entities import PlanoContas
from app.infrastructure.db.models import PlanoContasModel


def _to_entity(model: PlanoContasModel) -> PlanoContas:
    return PlanoContas(
        id=model.id,
        empresa_id=model.empresa_id,
        nome=model.nome,
        versao=model.versao,
        ativo=model.ativo,
        created_at=model.created_at,
    )


class SqlAlchemyPlanoContasRepository(PlanoContasRepository):
    def __init__(self, session: Session):
        self._session = session

    def criar(self, plano: PlanoContas) -> PlanoContas:
        model = PlanoContasModel(
            empresa_id=plano.empresa_id, nome=plano.nome, versao=plano.versao, ativo=plano.ativo
        )
        self._session.add(model)
        self._session.flush()
        return _to_entity(model)

    def obter_por_id(self, plano_id: int) -> PlanoContas | None:
        model = self._session.get(PlanoContasModel, plano_id)
        return _to_entity(model) if model else None

    def listar_por_empresa(self, empresa_id: int) -> list[PlanoContas]:
        models = self._session.query(PlanoContasModel).filter_by(empresa_id=empresa_id).all()
        return [_to_entity(m) for m in models]
```

- [ ] **Step 6: Write sqlalchemy_conta_repository.py**

`backend/app/infrastructure/repositories/sqlalchemy_conta_repository.py`:
```python
from sqlalchemy.orm import Session

from app.application.repositories import ContaRepository
from app.domain.entities import Conta
from app.domain.enums import NaturezaConta
from app.infrastructure.db.models import ContaModel


def _to_entity(model: ContaModel) -> Conta:
    return Conta(
        id=model.id,
        plano_conta_id=model.plano_conta_id,
        codigo=model.codigo,
        descricao=model.descricao,
        natureza=NaturezaConta(model.natureza),
        conta_analitica=model.conta_analitica,
        conta_pai_id=model.conta_pai_id,
    )


class SqlAlchemyContaRepository(ContaRepository):
    def __init__(self, session: Session):
        self._session = session

    def criar(self, conta: Conta) -> Conta:
        model = ContaModel(
            plano_conta_id=conta.plano_conta_id,
            codigo=conta.codigo,
            descricao=conta.descricao,
            natureza=conta.natureza.value,
            conta_analitica=conta.conta_analitica,
            conta_pai_id=conta.conta_pai_id,
        )
        self._session.add(model)
        self._session.flush()
        return _to_entity(model)

    def criar_em_lote(self, contas: list[Conta]) -> list[Conta]:
        return [self.criar(c) for c in contas]

    def obter_por_id(self, conta_id: int) -> Conta | None:
        model = self._session.get(ContaModel, conta_id)
        return _to_entity(model) if model else None

    def listar_por_plano(self, plano_conta_id: int) -> list[Conta]:
        models = self._session.query(ContaModel).filter_by(plano_conta_id=plano_conta_id).all()
        return [_to_entity(m) for m in models]

    def atualizar(self, conta: Conta) -> Conta:
        model = self._session.get(ContaModel, conta.id)
        model.codigo = conta.codigo
        model.descricao = conta.descricao
        model.natureza = conta.natureza.value
        model.conta_analitica = conta.conta_analitica
        model.conta_pai_id = conta.conta_pai_id
        self._session.flush()
        return _to_entity(model)

    def deletar(self, conta_id: int) -> None:
        model = self._session.get(ContaModel, conta_id)
        if model is not None:
            self._session.delete(model)
            self._session.flush()
```

- [ ] **Step 7: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/integration/test_sqlalchemy_repositories.py -v`
Expected: PASS (3 passed)

- [ ] **Step 8: Commit**

```bash
git add backend/app/infrastructure/repositories backend/tests/conftest.py backend/tests/integration/test_sqlalchemy_repositories.py
git commit -m "feat: add SQLAlchemy repository implementations"
```

---

### Task 7: Plano de Contas and Conta use cases (manual CRUD, no import yet)

**Files:**
- Create: `backend/app/application/use_cases/plano_contas_use_cases.py`
- Create: `backend/app/application/use_cases/conta_use_cases.py`
- Test: `backend/tests/unit/test_plano_contas_use_cases.py`
- Test: `backend/tests/unit/test_conta_use_cases.py`

**Interfaces:**
- Consumes: `PlanoContasRepository`, `ContaRepository` (Task 4), `CriarPlanoContasDTO`, `CriarContaDTO`, `AtualizarContaDTO` (Task 5), `PlanoContasNaoEncontrado`, `ContaNaoEncontrada` (Task 5).
- Produces: `CriarPlanoContasUseCase(repo).executar(empresa_id: int, dto: CriarPlanoContasDTO) -> PlanoContas`, `ListarPlanosContasUseCase(repo).executar(empresa_id: int) -> list[PlanoContas]`. `CriarContaUseCase(repo).executar(plano_conta_id: int, dto: CriarContaDTO) -> Conta`, `ListarContasUseCase(repo).executar(plano_conta_id: int) -> list[Conta]`, `AtualizarContaUseCase(repo).executar(conta_id: int, dto: AtualizarContaDTO) -> Conta`, `DeletarContaUseCase(repo).executar(conta_id: int) -> None`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/unit/test_plano_contas_use_cases.py`:
```python
from app.application.dto import CriarPlanoContasDTO
from app.application.use_cases.plano_contas_use_cases import (
    CriarPlanoContasUseCase,
    ListarPlanosContasUseCase,
)
from tests.fakes import FakePlanoContasRepository


def test_criar_plano_contas():
    repo = FakePlanoContasRepository()
    plano = CriarPlanoContasUseCase(repo).executar(1, CriarPlanoContasDTO(nome="Plano Padrão"))

    assert plano.id == 1
    assert plano.empresa_id == 1
    assert plano.nome == "Plano Padrão"


def test_listar_planos_por_empresa():
    repo = FakePlanoContasRepository()
    CriarPlanoContasUseCase(repo).executar(1, CriarPlanoContasDTO(nome="Plano A"))
    CriarPlanoContasUseCase(repo).executar(2, CriarPlanoContasDTO(nome="Plano B"))

    planos = ListarPlanosContasUseCase(repo).executar(1)

    assert len(planos) == 1
    assert planos[0].nome == "Plano A"
```

`backend/tests/unit/test_conta_use_cases.py`:
```python
import pytest

from app.application.dto import AtualizarContaDTO, CriarContaDTO
from app.application.use_cases.conta_use_cases import (
    AtualizarContaUseCase,
    CriarContaUseCase,
    DeletarContaUseCase,
    ListarContasUseCase,
)
from app.core.exceptions import ContaNaoEncontrada
from tests.fakes import FakeContaRepository


def test_criar_conta():
    repo = FakeContaRepository()
    dto = CriarContaDTO(codigo="1.1.01", descricao="Caixa", natureza="ATIVO", conta_analitica=True)

    conta = CriarContaUseCase(repo).executar(1, dto)

    assert conta.id == 1
    assert conta.codigo == "1.1.01"
    assert conta.natureza.value == "ATIVO"


def test_listar_contas_por_plano():
    repo = FakeContaRepository()
    CriarContaUseCase(repo).executar(1, CriarContaDTO("1.1", "Disponibilidades", "ATIVO", False))
    CriarContaUseCase(repo).executar(1, CriarContaDTO("1.1.01", "Caixa", "ATIVO", True))
    CriarContaUseCase(repo).executar(2, CriarContaDTO("2.1", "Fornecedores", "PASSIVO", True))

    contas = ListarContasUseCase(repo).executar(1)

    assert len(contas) == 2


def test_atualizar_conta():
    repo = FakeContaRepository()
    conta = CriarContaUseCase(repo).executar(1, CriarContaDTO("1.1.01", "Caixa", "ATIVO", True))

    atualizada = AtualizarContaUseCase(repo).executar(
        conta.id, AtualizarContaDTO("1.1.01", "Caixa e Equivalentes", "ATIVO", True)
    )

    assert atualizada.descricao == "Caixa e Equivalentes"


def test_deletar_conta():
    repo = FakeContaRepository()
    conta = CriarContaUseCase(repo).executar(1, CriarContaDTO("1.1.01", "Caixa", "ATIVO", True))

    DeletarContaUseCase(repo).executar(conta.id)

    assert repo.obter_por_id(conta.id) is None


def test_atualizar_conta_inexistente_falha():
    repo = FakeContaRepository()
    with pytest.raises(ContaNaoEncontrada):
        AtualizarContaUseCase(repo).executar(999, AtualizarContaDTO("1", "x", "ATIVO", True))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/unit/test_plano_contas_use_cases.py tests/unit/test_conta_use_cases.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.application.use_cases.plano_contas_use_cases'`

- [ ] **Step 3: Write plano_contas_use_cases.py**

`backend/app/application/use_cases/plano_contas_use_cases.py`:
```python
from app.application.dto import CriarPlanoContasDTO
from app.application.repositories import PlanoContasRepository
from app.domain.entities import PlanoContas


class CriarPlanoContasUseCase:
    def __init__(self, repo: PlanoContasRepository):
        self._repo = repo

    def executar(self, empresa_id: int, dto: CriarPlanoContasDTO) -> PlanoContas:
        plano = PlanoContas(id=None, empresa_id=empresa_id, nome=dto.nome)
        return self._repo.criar(plano)


class ListarPlanosContasUseCase:
    def __init__(self, repo: PlanoContasRepository):
        self._repo = repo

    def executar(self, empresa_id: int) -> list[PlanoContas]:
        return self._repo.listar_por_empresa(empresa_id)
```

- [ ] **Step 4: Write conta_use_cases.py**

`backend/app/application/use_cases/conta_use_cases.py`:
```python
from app.application.dto import AtualizarContaDTO, CriarContaDTO
from app.application.repositories import ContaRepository
from app.core.exceptions import ContaNaoEncontrada
from app.domain.entities import Conta
from app.domain.enums import NaturezaConta


class CriarContaUseCase:
    def __init__(self, repo: ContaRepository):
        self._repo = repo

    def executar(self, plano_conta_id: int, dto: CriarContaDTO) -> Conta:
        conta = Conta(
            id=None,
            plano_conta_id=plano_conta_id,
            codigo=dto.codigo,
            descricao=dto.descricao,
            natureza=NaturezaConta(dto.natureza),
            conta_analitica=dto.conta_analitica,
            conta_pai_id=dto.conta_pai_id,
        )
        return self._repo.criar(conta)


class ListarContasUseCase:
    def __init__(self, repo: ContaRepository):
        self._repo = repo

    def executar(self, plano_conta_id: int) -> list[Conta]:
        return self._repo.listar_por_plano(plano_conta_id)


class AtualizarContaUseCase:
    def __init__(self, repo: ContaRepository):
        self._repo = repo

    def executar(self, conta_id: int, dto: AtualizarContaDTO) -> Conta:
        conta = self._repo.obter_por_id(conta_id)
        if conta is None:
            raise ContaNaoEncontrada(conta_id)
        conta.codigo = dto.codigo
        conta.descricao = dto.descricao
        conta.natureza = NaturezaConta(dto.natureza)
        conta.conta_analitica = dto.conta_analitica
        conta.conta_pai_id = dto.conta_pai_id
        return self._repo.atualizar(conta)


class DeletarContaUseCase:
    def __init__(self, repo: ContaRepository):
        self._repo = repo

    def executar(self, conta_id: int) -> None:
        self._repo.deletar(conta_id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/unit/test_plano_contas_use_cases.py tests/unit/test_conta_use_cases.py -v`
Expected: PASS (7 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/app/application/use_cases/plano_contas_use_cases.py backend/app/application/use_cases/conta_use_cases.py backend/tests/unit/test_plano_contas_use_cases.py backend/tests/unit/test_conta_use_cases.py
git commit -m "feat: add PlanoContas and Conta use cases"
```

---

### Task 8: API dependency wiring and Empresa endpoints

**Files:**
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/deps.py`
- Create: `backend/app/api/schemas/__init__.py`
- Create: `backend/app/api/schemas/empresa_schemas.py`
- Create: `backend/app/api/routers/__init__.py`
- Create: `backend/app/api/routers/empresas_router.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/integration/test_empresas_api.py`

**Interfaces:**
- Consumes: use cases from Task 5, `SqlAlchemyEmpresaRepository` (Task 6), `SessionLocal` (Task 3).
- Produces: `get_db()` FastAPI dependency yielding a `Session`. `EmpresaOut`, `EmpresaCreateIn`, `EmpresaUpdateIn` Pydantic schemas. Router `empresas_router` mounted at `/empresas`.

- [ ] **Step 1: Write deps.py**

`backend/app/api/deps.py`:
```python
from collections.abc import Generator

from sqlalchemy.orm import Session

from app.infrastructure.db.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

- [ ] **Step 2: Write empresa_schemas.py**

`backend/app/api/schemas/empresa_schemas.py`:
```python
from datetime import datetime

from pydantic import BaseModel


class EmpresaCreateIn(BaseModel):
    razao_social: str
    nome_fantasia: str | None = None
    cnpj: str


class EmpresaUpdateIn(BaseModel):
    razao_social: str
    nome_fantasia: str | None = None
    ativo: bool


class EmpresaOut(BaseModel):
    id: int
    razao_social: str
    nome_fantasia: str | None
    cnpj: str
    ativo: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

`backend/app/api/schemas/__init__.py`: empty file.

- [ ] **Step 3: Write the failing test**

`backend/tests/integration/test_empresas_api.py`:
```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.infrastructure.db.base import Base
from app.infrastructure.db import models  # noqa: F401
from app.main import app


@pytest.fixture
def client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        session = TestSessionLocal()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_criar_e_listar_empresa(client):
    response = client.post(
        "/empresas",
        json={"razao_social": "Tesserato", "nome_fantasia": "Tesserato", "cnpj": "12345678000199"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["razao_social"] == "Tesserato"
    empresa_id = body["id"]

    response = client.get("/empresas")
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = client.get(f"/empresas/{empresa_id}")
    assert response.status_code == 200
    assert response.json()["cnpj"] == "12345678000199"


def test_criar_empresa_cnpj_duplicado_retorna_409(client):
    payload = {"razao_social": "Tesserato", "nome_fantasia": None, "cnpj": "12345678000199"}
    client.post("/empresas", json=payload)

    response = client.post("/empresas", json=payload)
    assert response.status_code == 409


def test_obter_empresa_inexistente_retorna_404(client):
    response = client.get("/empresas/999")
    assert response.status_code == 404


def test_atualizar_e_desativar_empresa(client):
    response = client.post(
        "/empresas", json={"razao_social": "A", "nome_fantasia": None, "cnpj": "11111111000191"}
    )
    empresa_id = response.json()["id"]

    response = client.put(
        f"/empresas/{empresa_id}",
        json={"razao_social": "A Ltda", "nome_fantasia": "A", "ativo": True},
    )
    assert response.status_code == 200
    assert response.json()["razao_social"] == "A Ltda"

    response = client.delete(f"/empresas/{empresa_id}")
    assert response.status_code == 204

    response = client.get(f"/empresas/{empresa_id}")
    assert response.json()["ativo"] is False
```

- [ ] **Step 4: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/integration/test_empresas_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.api'`

- [ ] **Step 5: Write empresas_router.py**

`backend/app/api/routers/empresas_router.py`:
```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.schemas.empresa_schemas import EmpresaCreateIn, EmpresaOut, EmpresaUpdateIn
from app.application.dto import AtualizarEmpresaDTO, CriarEmpresaDTO
from app.application.use_cases.empresa_use_cases import (
    AtualizarEmpresaUseCase,
    CriarEmpresaUseCase,
    DesativarEmpresaUseCase,
    ListarEmpresasUseCase,
    ObterEmpresaUseCase,
)
from app.core.exceptions import CnpjJaCadastrado, EmpresaNaoEncontrada
from app.infrastructure.repositories.sqlalchemy_empresa_repository import (
    SqlAlchemyEmpresaRepository,
)

router = APIRouter(prefix="/empresas", tags=["empresas"])


@router.post("", response_model=EmpresaOut, status_code=status.HTTP_201_CREATED)
def criar_empresa(payload: EmpresaCreateIn, db: Session = Depends(get_db)):
    repo = SqlAlchemyEmpresaRepository(db)
    try:
        empresa = CriarEmpresaUseCase(repo).executar(
            CriarEmpresaDTO(payload.razao_social, payload.nome_fantasia, payload.cnpj)
        )
    except CnpjJaCadastrado as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return empresa


@router.get("", response_model=list[EmpresaOut])
def listar_empresas(db: Session = Depends(get_db)):
    repo = SqlAlchemyEmpresaRepository(db)
    return ListarEmpresasUseCase(repo).executar()


@router.get("/{empresa_id}", response_model=EmpresaOut)
def obter_empresa(empresa_id: int, db: Session = Depends(get_db)):
    repo = SqlAlchemyEmpresaRepository(db)
    try:
        return ObterEmpresaUseCase(repo).executar(empresa_id)
    except EmpresaNaoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{empresa_id}", response_model=EmpresaOut)
def atualizar_empresa(empresa_id: int, payload: EmpresaUpdateIn, db: Session = Depends(get_db)):
    repo = SqlAlchemyEmpresaRepository(db)
    try:
        return AtualizarEmpresaUseCase(repo).executar(
            empresa_id,
            AtualizarEmpresaDTO(payload.razao_social, payload.nome_fantasia, payload.ativo),
        )
    except EmpresaNaoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{empresa_id}", status_code=status.HTTP_204_NO_CONTENT)
def desativar_empresa(empresa_id: int, db: Session = Depends(get_db)):
    repo = SqlAlchemyEmpresaRepository(db)
    try:
        DesativarEmpresaUseCase(repo).executar(empresa_id)
    except EmpresaNaoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

`backend/app/api/routers/__init__.py` and `backend/app/api/__init__.py`: empty files.

- [ ] **Step 6: Wire the router into main.py**

`backend/app/main.py` (replace full content):
```python
from fastapi import FastAPI

from app.api.routers.empresas_router import router as empresas_router
from app.core.config import settings

app = FastAPI(title=settings.app_name)

app.include_router(empresas_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 7: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/integration/test_empresas_api.py -v`
Expected: PASS (4 passed)

- [ ] **Step 8: Run the full backend test suite so far**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all tests pass.

- [ ] **Step 9: Commit**

```bash
git add backend/app/api backend/app/main.py backend/tests/integration/test_empresas_api.py
git commit -m "feat: add Empresa REST endpoints"
```

---

### Task 9: PlanoContas and Conta REST endpoints

**Files:**
- Create: `backend/app/api/schemas/plano_contas_schemas.py`
- Create: `backend/app/api/schemas/conta_schemas.py`
- Create: `backend/app/api/routers/planos_contas_router.py`
- Create: `backend/app/api/routers/contas_router.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/integration/test_planos_contas_api.py`

**Interfaces:**
- Consumes: use cases from Task 7, `SqlAlchemyPlanoContasRepository`, `SqlAlchemyContaRepository` (Task 6).
- Produces: routers `planos_contas_router` (prefix `/empresas/{empresa_id}/planos-contas` plus `/planos-contas/{plano_id}/contas`) and `contas_router` (prefix `/contas` for update/delete by id).

- [ ] **Step 1: Write plano_contas_schemas.py and conta_schemas.py**

`backend/app/api/schemas/plano_contas_schemas.py`:
```python
from pydantic import BaseModel


class PlanoContasCreateIn(BaseModel):
    nome: str


class PlanoContasOut(BaseModel):
    id: int
    empresa_id: int
    nome: str
    versao: int
    ativo: bool

    model_config = {"from_attributes": True}
```

`backend/app/api/schemas/conta_schemas.py`:
```python
from pydantic import BaseModel

from app.domain.enums import NaturezaConta


class ContaCreateIn(BaseModel):
    codigo: str
    descricao: str
    natureza: NaturezaConta
    conta_analitica: bool
    conta_pai_id: int | None = None


class ContaUpdateIn(BaseModel):
    codigo: str
    descricao: str
    natureza: NaturezaConta
    conta_analitica: bool
    conta_pai_id: int | None = None


class ContaOut(BaseModel):
    id: int
    plano_conta_id: int
    codigo: str
    descricao: str
    natureza: NaturezaConta
    conta_analitica: bool
    conta_pai_id: int | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Write the failing test**

`backend/tests/integration/test_planos_contas_api.py`:
```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.infrastructure.db.base import Base
from app.infrastructure.db import models  # noqa: F401
from app.main import app


@pytest.fixture
def client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        session = TestSessionLocal()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def empresa_id(client):
    response = client.post(
        "/empresas", json={"razao_social": "Tesserato", "nome_fantasia": None, "cnpj": "12345678000199"}
    )
    return response.json()["id"]


def test_criar_plano_contas_e_contas(client, empresa_id):
    response = client.post(f"/empresas/{empresa_id}/planos-contas", json={"nome": "Plano Padrão"})
    assert response.status_code == 201
    plano_id = response.json()["id"]

    response = client.get(f"/empresas/{empresa_id}/planos-contas")
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = client.post(
        f"/planos-contas/{plano_id}/contas",
        json={
            "codigo": "1.1.01", "descricao": "Caixa", "natureza": "ATIVO",
            "conta_analitica": True, "conta_pai_id": None,
        },
    )
    assert response.status_code == 201
    conta_id = response.json()["id"]

    response = client.get(f"/planos-contas/{plano_id}/contas")
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = client.put(
        f"/contas/{conta_id}",
        json={
            "codigo": "1.1.01", "descricao": "Caixa e Equivalentes", "natureza": "ATIVO",
            "conta_analitica": True, "conta_pai_id": None,
        },
    )
    assert response.status_code == 200
    assert response.json()["descricao"] == "Caixa e Equivalentes"

    response = client.delete(f"/contas/{conta_id}")
    assert response.status_code == 204

    response = client.get(f"/planos-contas/{plano_id}/contas")
    assert len(response.json()) == 0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/integration/test_planos_contas_api.py -v`
Expected: FAIL with 404s (routers not registered yet).

- [ ] **Step 4: Write planos_contas_router.py**

`backend/app/api/routers/planos_contas_router.py`:
```python
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.schemas.plano_contas_schemas import PlanoContasCreateIn, PlanoContasOut
from app.application.dto import CriarPlanoContasDTO
from app.application.use_cases.plano_contas_use_cases import (
    CriarPlanoContasUseCase,
    ListarPlanosContasUseCase,
)
from app.infrastructure.repositories.sqlalchemy_plano_contas_repository import (
    SqlAlchemyPlanoContasRepository,
)

router = APIRouter(tags=["planos-contas"])


@router.post(
    "/empresas/{empresa_id}/planos-contas",
    response_model=PlanoContasOut,
    status_code=status.HTTP_201_CREATED,
)
def criar_plano_contas(empresa_id: int, payload: PlanoContasCreateIn, db: Session = Depends(get_db)):
    repo = SqlAlchemyPlanoContasRepository(db)
    return CriarPlanoContasUseCase(repo).executar(empresa_id, CriarPlanoContasDTO(payload.nome))


@router.get("/empresas/{empresa_id}/planos-contas", response_model=list[PlanoContasOut])
def listar_planos_contas(empresa_id: int, db: Session = Depends(get_db)):
    repo = SqlAlchemyPlanoContasRepository(db)
    return ListarPlanosContasUseCase(repo).executar(empresa_id)
```

- [ ] **Step 5: Write contas_router.py**

`backend/app/api/routers/contas_router.py`:
```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.schemas.conta_schemas import ContaCreateIn, ContaOut, ContaUpdateIn
from app.application.dto import AtualizarContaDTO, CriarContaDTO
from app.application.use_cases.conta_use_cases import (
    AtualizarContaUseCase,
    CriarContaUseCase,
    DeletarContaUseCase,
    ListarContasUseCase,
)
from app.core.exceptions import ContaNaoEncontrada
from app.infrastructure.repositories.sqlalchemy_conta_repository import (
    SqlAlchemyContaRepository,
)

router = APIRouter(tags=["contas"])


@router.post(
    "/planos-contas/{plano_id}/contas", response_model=ContaOut, status_code=status.HTTP_201_CREATED
)
def criar_conta(plano_id: int, payload: ContaCreateIn, db: Session = Depends(get_db)):
    repo = SqlAlchemyContaRepository(db)
    dto = CriarContaDTO(
        payload.codigo, payload.descricao, payload.natureza.value,
        payload.conta_analitica, payload.conta_pai_id,
    )
    return CriarContaUseCase(repo).executar(plano_id, dto)


@router.get("/planos-contas/{plano_id}/contas", response_model=list[ContaOut])
def listar_contas(plano_id: int, db: Session = Depends(get_db)):
    repo = SqlAlchemyContaRepository(db)
    return ListarContasUseCase(repo).executar(plano_id)


@router.put("/contas/{conta_id}", response_model=ContaOut)
def atualizar_conta(conta_id: int, payload: ContaUpdateIn, db: Session = Depends(get_db)):
    repo = SqlAlchemyContaRepository(db)
    dto = AtualizarContaDTO(
        payload.codigo, payload.descricao, payload.natureza.value,
        payload.conta_analitica, payload.conta_pai_id,
    )
    try:
        return AtualizarContaUseCase(repo).executar(conta_id, dto)
    except ContaNaoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/contas/{conta_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_conta(conta_id: int, db: Session = Depends(get_db)):
    repo = SqlAlchemyContaRepository(db)
    DeletarContaUseCase(repo).executar(conta_id)
```

- [ ] **Step 6: Register both routers in main.py**

`backend/app/main.py` (replace full content):
```python
from fastapi import FastAPI

from app.api.routers.contas_router import router as contas_router
from app.api.routers.empresas_router import router as empresas_router
from app.api.routers.planos_contas_router import router as planos_contas_router
from app.core.config import settings

app = FastAPI(title=settings.app_name)

app.include_router(empresas_router)
app.include_router(planos_contas_router)
app.include_router(contas_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 7: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/integration/test_planos_contas_api.py -v`
Expected: PASS (1 passed)

- [ ] **Step 8: Run the full backend test suite**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all tests pass.

- [ ] **Step 9: Commit**

```bash
git add backend/app/api backend/app/main.py backend/tests/integration/test_planos_contas_api.py
git commit -m "feat: add PlanoContas and Conta REST endpoints"
```

---

### Task 10: Column detector for spreadsheet import

**Files:**
- Create: `backend/app/infrastructure/spreadsheet/__init__.py`
- Create: `backend/app/infrastructure/spreadsheet/column_detector.py`
- Test: `backend/tests/unit/test_column_detector.py`

**Interfaces:**
- Produces: `detectar_colunas(cabecalhos: list[str]) -> dict[str, int | None]` returning a mapping from field name (`codigo`, `descricao`, `natureza`, `conta_analitica`, `conta_pai`) to the column index in `cabecalhos` (or `None` if not found). `CAMPOS_OBRIGATORIOS = {"codigo", "descricao"}`.

- [ ] **Step 1: Write the failing test**

`backend/tests/unit/test_column_detector.py`:
```python
from app.infrastructure.spreadsheet.column_detector import detectar_colunas


def test_detecta_colunas_com_nomes_exatos():
    mapeamento = detectar_colunas(["Código", "Descrição", "Natureza"])
    assert mapeamento["codigo"] == 0
    assert mapeamento["descricao"] == 1
    assert mapeamento["natureza"] == 2


def test_detecta_colunas_com_sinonimos():
    mapeamento = detectar_colunas(["Cod. Conta", "Nome da Conta", "Tipo"])
    assert mapeamento["codigo"] == 0
    assert mapeamento["descricao"] == 1
    assert mapeamento["natureza"] == 2


def test_detecta_colunas_em_ingles():
    mapeamento = detectar_colunas(["Account Code", "Account Name"])
    assert mapeamento["codigo"] == 0
    assert mapeamento["descricao"] == 1


def test_coluna_nao_reconhecida_fica_none():
    mapeamento = detectar_colunas(["Código", "Descrição", "Coluna Aleatória XYZ"])
    assert mapeamento["natureza"] is None


def test_detecta_conta_analitica_e_conta_pai():
    mapeamento = detectar_colunas(["Código", "Descrição", "Conta Analítica", "Conta Pai"])
    assert mapeamento["conta_analitica"] == 2
    assert mapeamento["conta_pai"] == 3
```

`backend/tests/unit/__init__.py` already exists from Task 2.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/unit/test_column_detector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.infrastructure.spreadsheet'`

- [ ] **Step 3: Write column_detector.py**

`backend/app/infrastructure/spreadsheet/column_detector.py`:
```python
import unicodedata
from difflib import SequenceMatcher

CAMPOS_OBRIGATORIOS = {"codigo", "descricao"}

_SINONIMOS: dict[str, list[str]] = {
    "codigo": ["codigo", "cod", "cod conta", "codigo conta", "account code", "code"],
    "descricao": [
        "descricao", "descricao da conta", "nome", "nome da conta", "historico",
        "account name", "name", "conta",
    ],
    "natureza": ["natureza", "tipo", "tipo de conta", "account type", "type"],
    "conta_analitica": [
        "conta analitica", "analitica", "analytic account", "e analitica",
    ],
    "conta_pai": ["conta pai", "conta superior", "parent account", "parent"],
}


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sem_acento.strip().lower().replace(".", "").replace("_", " ")


def _similaridade(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def detectar_colunas(cabecalhos: list[str]) -> dict[str, int | None]:
    normalizados = [_normalizar(h) for h in cabecalhos]
    resultado: dict[str, int | None] = {}

    for campo, sinonimos in _SINONIMOS.items():
        melhor_indice: int | None = None
        melhor_score = 0.0

        for indice, cabecalho in enumerate(normalizados):
            if cabecalho in sinonimos:
                melhor_indice = indice
                melhor_score = 1.0
                break
            for sinonimo in sinonimos:
                score = _similaridade(cabecalho, sinonimo)
                if score > melhor_score:
                    melhor_score = score
                    melhor_indice = indice

        resultado[campo] = melhor_indice if melhor_score >= 0.8 else None

    return resultado
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/unit/test_column_detector.py -v`
Expected: PASS (5 passed). If `test_coluna_nao_reconhecida_fica_none` fails because "Coluna Aleatória XYZ" scores >= 0.8 against a synonym, that indicates the threshold is too low — this is expected to pass as written since "coluna aleatoria xyz" has low similarity to all "natureza" synonyms.

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/spreadsheet backend/tests/unit/test_column_detector.py
git commit -m "feat: add automatic column detector for spreadsheet import"
```

---

### Task 11: Plano de Contas spreadsheet parser

**Files:**
- Create: `backend/app/infrastructure/spreadsheet/plano_contas_parser.py`
- Create: `backend/tests/integration/fixtures/plano_contas_padrao.csv`
- Create: `backend/tests/integration/fixtures/plano_contas_variante.csv`
- Test: `backend/tests/integration/test_plano_contas_parser.py`

**Interfaces:**
- Consumes: `detectar_colunas`, `CAMPOS_OBRIGATORIOS` (Task 10).
- Produces: `LinhaPlanoContas` dataclass (`codigo`, `descricao`, `natureza: str | None`, `conta_analitica: bool | None`, `conta_pai: str | None`). `ParsePlanoContasResultado` dataclass (`mapeamento: dict[str, int | None]`, `linhas: list[LinhaPlanoContas]`). `parsear_planilha(conteudo: bytes, nome_arquivo: str) -> ParsePlanoContasResultado`, raising `app.core.exceptions.ImportacaoPlanoContasInvalida` when `codigo` or `descricao` can't be detected. Supports `.csv` and `.xlsx` based on `nome_arquivo` extension.

- [ ] **Step 1: Create fixture files**

`backend/tests/integration/fixtures/plano_contas_padrao.csv`:
```
Código,Descrição,Natureza,Conta Analítica,Conta Pai
1,ATIVO,ATIVO,False,
1.1,Disponibilidades,ATIVO,False,1
1.1.01,Caixa,ATIVO,True,1.1
3.1.02.001,Despesas com Energia,DESPESA,True,
```

`backend/tests/integration/fixtures/plano_contas_variante.csv`:
```
Cod. Conta,Nome da Conta,Tipo
2,PASSIVO,PASSIVO
2.1,Fornecedores,PASSIVO
```

- [ ] **Step 2: Write the failing test**

`backend/tests/integration/test_plano_contas_parser.py`:
```python
from pathlib import Path

import pytest

from app.core.exceptions import ImportacaoPlanoContasInvalida
from app.infrastructure.spreadsheet.plano_contas_parser import parsear_planilha

FIXTURES = Path(__file__).parent / "fixtures"


def test_parseia_planilha_padrao():
    conteudo = (FIXTURES / "plano_contas_padrao.csv").read_bytes()

    resultado = parsear_planilha(conteudo, "plano_contas_padrao.csv")

    assert resultado.mapeamento["codigo"] == 0
    assert resultado.mapeamento["descricao"] == 1
    assert len(resultado.linhas) == 4
    assert resultado.linhas[2].codigo == "1.1.01"
    assert resultado.linhas[2].descricao == "Caixa"
    assert resultado.linhas[2].conta_analitica is True


def test_parseia_planilha_com_colunas_variantes():
    conteudo = (FIXTURES / "plano_contas_variante.csv").read_bytes()

    resultado = parsear_planilha(conteudo, "plano_contas_variante.csv")

    assert resultado.mapeamento["codigo"] == 0
    assert resultado.mapeamento["descricao"] == 1
    assert len(resultado.linhas) == 2
    assert resultado.linhas[0].codigo == "2"


def test_planilha_sem_colunas_obrigatorias_falha():
    conteudo = b"Coluna A,Coluna B\nx,y\n"

    with pytest.raises(ImportacaoPlanoContasInvalida):
        parsear_planilha(conteudo, "invalida.csv")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/integration/test_plano_contas_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.infrastructure.spreadsheet.plano_contas_parser'`

- [ ] **Step 4: Write plano_contas_parser.py**

`backend/app/infrastructure/spreadsheet/plano_contas_parser.py`:
```python
import csv
import io
from dataclasses import dataclass

from openpyxl import load_workbook

from app.core.exceptions import ImportacaoPlanoContasInvalida
from app.infrastructure.spreadsheet.column_detector import (
    CAMPOS_OBRIGATORIOS,
    detectar_colunas,
)


@dataclass
class LinhaPlanoContas:
    codigo: str
    descricao: str
    natureza: str | None
    conta_analitica: bool | None
    conta_pai: str | None


@dataclass
class ParsePlanoContasResultado:
    mapeamento: dict[str, int | None]
    linhas: list[LinhaPlanoContas]


def _ler_linhas_csv(conteudo: bytes) -> list[list[str]]:
    texto = conteudo.decode("utf-8-sig")
    leitor = csv.reader(io.StringIO(texto))
    return [linha for linha in leitor if any(celula.strip() for celula in linha)]


def _ler_linhas_xlsx(conteudo: bytes) -> list[list[str]]:
    planilha = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    aba = planilha.active
    linhas = []
    for linha in aba.iter_rows(values_only=True):
        if any(celula is not None and str(celula).strip() for celula in linha):
            linhas.append(["" if celula is None else str(celula) for celula in linha])
    return linhas


def _parse_bool(valor: str | None) -> bool | None:
    if valor is None or valor == "":
        return None
    return valor.strip().lower() in {"true", "verdadeiro", "sim", "1"}


def parsear_planilha(conteudo: bytes, nome_arquivo: str) -> ParsePlanoContasResultado:
    if nome_arquivo.lower().endswith(".xlsx"):
        linhas_brutas = _ler_linhas_xlsx(conteudo)
    else:
        linhas_brutas = _ler_linhas_csv(conteudo)

    if not linhas_brutas:
        raise ImportacaoPlanoContasInvalida("A planilha está vazia.")

    cabecalhos, *linhas_dados = linhas_brutas
    mapeamento = detectar_colunas(cabecalhos)

    faltantes = [campo for campo in CAMPOS_OBRIGATORIOS if mapeamento.get(campo) is None]
    if faltantes:
        raise ImportacaoPlanoContasInvalida(
            "Não foi possível identificar as colunas obrigatórias "
            f"{faltantes} no cabeçalho {cabecalhos}. Ajuste os nomes das colunas e reenvie."
        )

    def valor(linha: list[str], campo: str) -> str | None:
        indice = mapeamento.get(campo)
        if indice is None or indice >= len(linha):
            return None
        return linha[indice] or None

    linhas = [
        LinhaPlanoContas(
            codigo=valor(linha, "codigo") or "",
            descricao=valor(linha, "descricao") or "",
            natureza=valor(linha, "natureza"),
            conta_analitica=_parse_bool(valor(linha, "conta_analitica")),
            conta_pai=valor(linha, "conta_pai"),
        )
        for linha in linhas_dados
    ]

    return ParsePlanoContasResultado(mapeamento=mapeamento, linhas=linhas)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/integration/test_plano_contas_parser.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/app/infrastructure/spreadsheet/plano_contas_parser.py backend/tests/integration/fixtures backend/tests/integration/test_plano_contas_parser.py
git commit -m "feat: add plano de contas spreadsheet parser with auto column detection"
```

---

### Task 12: Import preview/confirm use cases

**Files:**
- Create: `backend/app/application/use_cases/importar_plano_contas_use_cases.py`
- Test: `backend/tests/unit/test_importar_plano_contas_use_cases.py`

**Interfaces:**
- Consumes: `parsear_planilha`, `ParsePlanoContasResultado`, `LinhaPlanoContas` (Task 11), `ContaRepository` (Task 4), `NaturezaConta` (Task 2).
- Produces: `PreviewImportacaoUseCase().executar(conteudo: bytes, nome_arquivo: str) -> ParsePlanoContasResultado`. `ConfirmarImportacaoUseCase(conta_repo).executar(plano_conta_id: int, linhas: list[LinhaPlanoContas]) -> list[Conta]` — creates parent accounts (by matching `conta_pai` code within the same batch) before child accounts, defaulting `natureza` to `DESPESA` and `conta_analitica` to `True` when not provided by the sheet (documented assumption, since the spec requires never inventing extracted *document* data — this default applies only to plano de contas import metadata, not to comprovante extraction).

- [ ] **Step 1: Write the failing test**

`backend/tests/unit/test_importar_plano_contas_use_cases.py`:
```python
from app.application.use_cases.importar_plano_contas_use_cases import (
    ConfirmarImportacaoUseCase,
    PreviewImportacaoUseCase,
)
from app.core.exceptions import ImportacaoPlanoContasInvalida
from app.infrastructure.spreadsheet.plano_contas_parser import LinhaPlanoContas
from tests.fakes import FakeContaRepository

import pytest


def test_preview_retorna_mapeamento_e_linhas():
    conteudo = b"Codigo,Descricao,Natureza\n1.1.01,Caixa,ATIVO\n"

    resultado = PreviewImportacaoUseCase().executar(conteudo, "arquivo.csv")

    assert resultado.mapeamento["codigo"] == 0
    assert len(resultado.linhas) == 1


def test_preview_planilha_invalida_propaga_erro():
    conteudo = b"A,B\nx,y\n"

    with pytest.raises(ImportacaoPlanoContasInvalida):
        PreviewImportacaoUseCase().executar(conteudo, "arquivo.csv")


def test_confirmar_importacao_cria_contas_com_hierarquia():
    repo = FakeContaRepository()
    linhas = [
        LinhaPlanoContas(codigo="1.1", descricao="Disponibilidades", natureza="ATIVO", conta_analitica=False, conta_pai=None),
        LinhaPlanoContas(codigo="1.1.01", descricao="Caixa", natureza="ATIVO", conta_analitica=True, conta_pai="1.1"),
    ]

    contas = ConfirmarImportacaoUseCase(repo).executar(plano_conta_id=1, linhas=linhas)

    assert len(contas) == 2
    pai = next(c for c in contas if c.codigo == "1.1")
    filha = next(c for c in contas if c.codigo == "1.1.01")
    assert filha.conta_pai_id == pai.id


def test_confirmar_importacao_aplica_defaults_quando_natureza_ausente():
    repo = FakeContaRepository()
    linhas = [
        LinhaPlanoContas(codigo="3.1", descricao="Despesas Gerais", natureza=None, conta_analitica=None, conta_pai=None),
    ]

    contas = ConfirmarImportacaoUseCase(repo).executar(plano_conta_id=1, linhas=linhas)

    assert contas[0].natureza.value == "DESPESA"
    assert contas[0].conta_analitica is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/unit/test_importar_plano_contas_use_cases.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.application.use_cases.importar_plano_contas_use_cases'`

- [ ] **Step 3: Write importar_plano_contas_use_cases.py**

`backend/app/application/use_cases/importar_plano_contas_use_cases.py`:
```python
from app.application.repositories import ContaRepository
from app.domain.entities import Conta
from app.domain.enums import NaturezaConta
from app.infrastructure.spreadsheet.plano_contas_parser import (
    LinhaPlanoContas,
    ParsePlanoContasResultado,
    parsear_planilha,
)


class PreviewImportacaoUseCase:
    def executar(self, conteudo: bytes, nome_arquivo: str) -> ParsePlanoContasResultado:
        return parsear_planilha(conteudo, nome_arquivo)


class ConfirmarImportacaoUseCase:
    def __init__(self, repo: ContaRepository):
        self._repo = repo

    def executar(self, plano_conta_id: int, linhas: list[LinhaPlanoContas]) -> list[Conta]:
        codigo_para_id: dict[str, int] = {}
        contas_criadas: list[Conta] = []

        linhas_ordenadas = sorted(linhas, key=lambda l: len(l.codigo))

        for linha in linhas_ordenadas:
            conta_pai_id = codigo_para_id.get(linha.conta_pai) if linha.conta_pai else None
            conta = Conta(
                id=None,
                plano_conta_id=plano_conta_id,
                codigo=linha.codigo,
                descricao=linha.descricao,
                natureza=NaturezaConta(linha.natureza) if linha.natureza else NaturezaConta.DESPESA,
                conta_analitica=linha.conta_analitica if linha.conta_analitica is not None else True,
                conta_pai_id=conta_pai_id,
            )
            criada = self._repo.criar(conta)
            codigo_para_id[linha.codigo] = criada.id
            contas_criadas.append(criada)

        return contas_criadas
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/unit/test_importar_plano_contas_use_cases.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/application/use_cases/importar_plano_contas_use_cases.py backend/tests/unit/test_importar_plano_contas_use_cases.py
git commit -m "feat: add plano de contas import preview/confirm use cases"
```

---

### Task 13: Import preview/confirm REST endpoints

**Files:**
- Create: `backend/app/api/schemas/import_schemas.py`
- Modify: `backend/app/api/routers/planos_contas_router.py`
- Test: `backend/tests/integration/test_import_api.py`

**Interfaces:**
- Consumes: `PreviewImportacaoUseCase`, `ConfirmarImportacaoUseCase` (Task 12), `SqlAlchemyContaRepository` (Task 6).
- Produces: `POST /planos-contas/{plano_id}/import/preview` (multipart file, returns `ImportPreviewOut`), `POST /planos-contas/{plano_id}/import/confirm` (multipart file, returns `list[ContaOut]`).

- [ ] **Step 1: Write import_schemas.py**

`backend/app/api/schemas/import_schemas.py`:
```python
from pydantic import BaseModel


class LinhaPreviewOut(BaseModel):
    codigo: str
    descricao: str
    natureza: str | None
    conta_analitica: bool | None
    conta_pai: str | None


class ImportPreviewOut(BaseModel):
    mapeamento: dict[str, int | None]
    linhas: list[LinhaPreviewOut]
```

- [ ] **Step 2: Write the failing test**

`backend/tests/integration/test_import_api.py`:
```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.infrastructure.db.base import Base
from app.infrastructure.db import models  # noqa: F401
from app.main import app


@pytest.fixture
def client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        session = TestSessionLocal()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def plano_id(client):
    empresa = client.post(
        "/empresas", json={"razao_social": "Tesserato", "nome_fantasia": None, "cnpj": "12345678000199"}
    ).json()
    plano = client.post(f"/empresas/{empresa['id']}/planos-contas", json={"nome": "Plano Padrão"}).json()
    return plano["id"]


CSV_CONTEUDO = b"Codigo,Descricao,Natureza,Conta Analitica,Conta Pai\n1.1,Disponibilidades,ATIVO,False,\n1.1.01,Caixa,ATIVO,True,1.1\n"


def test_preview_importacao(client, plano_id):
    response = client.post(
        f"/planos-contas/{plano_id}/import/preview",
        files={"arquivo": ("plano.csv", CSV_CONTEUDO, "text/csv")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mapeamento"]["codigo"] == 0
    assert len(body["linhas"]) == 2


def test_preview_importacao_invalida_retorna_422(client, plano_id):
    response = client.post(
        f"/planos-contas/{plano_id}/import/preview",
        files={"arquivo": ("plano.csv", b"A,B\nx,y\n", "text/csv")},
    )
    assert response.status_code == 422


def test_confirmar_importacao(client, plano_id):
    response = client.post(
        f"/planos-contas/{plano_id}/import/confirm",
        files={"arquivo": ("plano.csv", CSV_CONTEUDO, "text/csv")},
    )
    assert response.status_code == 201
    contas = response.json()
    assert len(contas) == 2

    response = client.get(f"/planos-contas/{plano_id}/contas")
    assert len(response.json()) == 2
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/integration/test_import_api.py -v`
Expected: FAIL with 404 (routes don't exist yet).

- [ ] **Step 4: Add import endpoints to planos_contas_router.py**

Append to `backend/app/api/routers/planos_contas_router.py` (add these imports at the top alongside existing ones, and these two endpoints at the end of the file):

```python
from fastapi import File, HTTPException, UploadFile

from app.api.schemas.import_schemas import ImportPreviewOut
from app.api.schemas.conta_schemas import ContaOut
from app.application.use_cases.importar_plano_contas_use_cases import (
    ConfirmarImportacaoUseCase,
    PreviewImportacaoUseCase,
)
from app.core.exceptions import ImportacaoPlanoContasInvalida
from app.infrastructure.repositories.sqlalchemy_conta_repository import (
    SqlAlchemyContaRepository,
)


@router.post("/planos-contas/{plano_id}/import/preview", response_model=ImportPreviewOut)
async def preview_importacao(plano_id: int, arquivo: UploadFile = File(...)):
    conteudo = await arquivo.read()
    try:
        return PreviewImportacaoUseCase().executar(conteudo, arquivo.filename)
    except ImportacaoPlanoContasInvalida as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/planos-contas/{plano_id}/import/confirm",
    response_model=list[ContaOut],
    status_code=201,
)
async def confirmar_importacao(
    plano_id: int, arquivo: UploadFile = File(...), db: Session = Depends(get_db)
):
    conteudo = await arquivo.read()
    try:
        resultado = PreviewImportacaoUseCase().executar(conteudo, arquivo.filename)
    except ImportacaoPlanoContasInvalida as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    repo = SqlAlchemyContaRepository(db)
    return ConfirmarImportacaoUseCase(repo).executar(plano_id, resultado.linhas)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/integration/test_import_api.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Run the full backend test suite**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all tests pass (this is the full Fase 0 backend).

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/schemas/import_schemas.py backend/app/api/routers/planos_contas_router.py backend/tests/integration/test_import_api.py
git commit -m "feat: add plano de contas import preview/confirm REST endpoints"
```

---

### Task 14: Frontend scaffolding

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/index.css`
- Create: `frontend/src/App.tsx`

**Interfaces:**
- Produces: a running Vite dev server at `http://localhost:5173` rendering `App` with Tailwind active.

- [ ] **Step 1: Scaffold the Vite React-TS project**

```bash
cd "D:/DEV/Teste Lançamentos"
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

- [ ] **Step 2: Configure Tailwind content paths**

`frontend/tailwind.config.js`:
```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: { extend: {} },
  plugins: [],
};
```

- [ ] **Step 3: Add Tailwind directives**

`frontend/src/index.css` (replace generated content):
```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 4: Write a minimal App.tsx to verify Tailwind renders**

`frontend/src/App.tsx`:
```tsx
export default function App() {
  return (
    <div className="min-h-screen bg-slate-50 p-8">
      <h1 className="text-2xl font-bold text-slate-800">
        Classificador de Comprovantes — Fase 0
      </h1>
    </div>
  );
}
```

`frontend/src/main.tsx` (Vite's default template already imports `./index.css` and renders `<App />` — verify it matches):
```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

- [ ] **Step 5: Run the dev server and verify Tailwind styling renders**

```bash
npm run dev
```
Open `http://localhost:5173` in a browser and confirm the heading renders in bold dark-slate text on a light-slate background (visual confirmation Tailwind is active). Stop the server with Ctrl+C when done.

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "chore: scaffold Vite React TS frontend with Tailwind"
```

---

### Task 15: Frontend API client and types

**Files:**
- Create: `frontend/src/types/empresa.ts`
- Create: `frontend/src/types/planoContas.ts`
- Create: `frontend/src/api/client.ts`

**Interfaces:**
- Produces: `Empresa`, `PlanoContas`, `Conta` TS interfaces matching the backend Pydantic `Out` schemas. `api.empresas.list()`, `api.empresas.create(input)`, `api.empresas.deactivate(id)`, `api.planosContas.list(empresaId)`, `api.planosContas.create(empresaId, nome)`, `api.contas.listByPlano(planoId)`, `api.contas.importPreview(planoId, file)`, `api.contas.importConfirm(planoId, file)` — all typed fetch wrappers against `http://localhost:8000`.

- [ ] **Step 1: Write empresa.ts and planoContas.ts**

`frontend/src/types/empresa.ts`:
```ts
export interface Empresa {
  id: number;
  razao_social: string;
  nome_fantasia: string | null;
  cnpj: string;
  ativo: boolean;
  created_at: string;
  updated_at: string;
}

export interface EmpresaCreateInput {
  razao_social: string;
  nome_fantasia: string | null;
  cnpj: string;
}
```

`frontend/src/types/planoContas.ts`:
```ts
export interface PlanoContas {
  id: number;
  empresa_id: number;
  nome: string;
  versao: number;
  ativo: boolean;
}

export interface Conta {
  id: number;
  plano_conta_id: number;
  codigo: string;
  descricao: string;
  natureza: string;
  conta_analitica: boolean;
  conta_pai_id: number | null;
}

export interface ImportPreviewLinha {
  codigo: string;
  descricao: string;
  natureza: string | null;
  conta_analitica: boolean | null;
  conta_pai: string | null;
}

export interface ImportPreview {
  mapeamento: Record<string, number | null>;
  linhas: ImportPreviewLinha[];
}
```

- [ ] **Step 2: Write client.ts**

`frontend/src/api/client.ts`:
```ts
import type { Empresa, EmpresaCreateInput } from "../types/empresa";
import type { Conta, ImportPreview, PlanoContas } from "../types/planoContas";

const BASE_URL = "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: init?.body instanceof FormData ? init.headers : { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail ?? "Erro na requisição");
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export const api = {
  empresas: {
    list: () => request<Empresa[]>("/empresas"),
    create: (input: EmpresaCreateInput) =>
      request<Empresa>("/empresas", { method: "POST", body: JSON.stringify(input) }),
    deactivate: (id: number) => request<void>(`/empresas/${id}`, { method: "DELETE" }),
  },
  planosContas: {
    list: (empresaId: number) =>
      request<PlanoContas[]>(`/empresas/${empresaId}/planos-contas`),
    create: (empresaId: number, nome: string) =>
      request<PlanoContas>(`/empresas/${empresaId}/planos-contas`, {
        method: "POST",
        body: JSON.stringify({ nome }),
      }),
  },
  contas: {
    listByPlano: (planoId: number) => request<Conta[]>(`/planos-contas/${planoId}/contas`),
    importPreview: (planoId: number, file: File) => {
      const formData = new FormData();
      formData.append("arquivo", file);
      return request<ImportPreview>(`/planos-contas/${planoId}/import/preview`, {
        method: "POST",
        body: formData,
      });
    },
    importConfirm: (planoId: number, file: File) => {
      const formData = new FormData();
      formData.append("arquivo", file);
      return request<Conta[]>(`/planos-contas/${planoId}/import/confirm`, {
        method: "POST",
        body: formData,
      });
    },
  },
};
```

- [ ] **Step 3: Verify the frontend still builds with no type errors**

```bash
cd frontend
npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types frontend/src/api
git commit -m "feat: add typed API client for empresas and plano de contas"
```

---

### Task 16: Frontend Empresa + Plano de Contas page

**Files:**
- Create: `frontend/src/components/EmpresaForm.tsx`
- Create: `frontend/src/components/EmpresaList.tsx`
- Create: `frontend/src/components/PlanoContasImport.tsx`
- Create: `frontend/src/components/ContasTree.tsx`
- Create: `frontend/src/pages/EmpresasPage.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `api` client, `Empresa`, `PlanoContas`, `Conta`, `ImportPreview` types (Task 15).
- Produces: `EmpresasPage` — the single Fase 0 screen. `EmpresaForm({ onCreated: (empresa: Empresa) => void })`. `EmpresaList({ empresas: Empresa[], selectedId: number | null, onSelect: (id: number) => void })`. `PlanoContasImport({ planoId: number, onImported: (contas: Conta[]) => void })`. `ContasTree({ contas: Conta[] })`.

- [ ] **Step 1: Write EmpresaForm.tsx**

`frontend/src/components/EmpresaForm.tsx`:
```tsx
import { useState } from "react";
import { api } from "../api/client";
import type { Empresa } from "../types/empresa";

export function EmpresaForm({ onCreated }: { onCreated: (empresa: Empresa) => void }) {
  const [razaoSocial, setRazaoSocial] = useState("");
  const [cnpj, setCnpj] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    try {
      const empresa = await api.empresas.create({
        razao_social: razaoSocial,
        nome_fantasia: null,
        cnpj,
      });
      setRazaoSocial("");
      setCnpj("");
      onCreated(empresa);
    } catch (err) {
      setErro((err as Error).message);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-2 rounded border border-slate-200 p-4">
      <label className="text-sm font-medium text-slate-700">
        Razão Social
        <input
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
          value={razaoSocial}
          onChange={(e) => setRazaoSocial(e.target.value)}
          required
        />
      </label>
      <label className="text-sm font-medium text-slate-700">
        CNPJ
        <input
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
          value={cnpj}
          onChange={(e) => setCnpj(e.target.value)}
          required
        />
      </label>
      {erro && <p className="text-sm text-red-600">{erro}</p>}
      <button type="submit" className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white">
        Cadastrar Empresa
      </button>
    </form>
  );
}
```

- [ ] **Step 2: Write EmpresaList.tsx**

`frontend/src/components/EmpresaList.tsx`:
```tsx
import type { Empresa } from "../types/empresa";

export function EmpresaList({
  empresas,
  selectedId,
  onSelect,
}: {
  empresas: Empresa[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <ul className="flex flex-col gap-1">
      {empresas.map((empresa) => (
        <li key={empresa.id}>
          <button
            onClick={() => onSelect(empresa.id)}
            className={`w-full rounded px-3 py-1.5 text-left text-sm ${
              selectedId === empresa.id ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-800"
            }`}
          >
            {empresa.razao_social} — {empresa.cnpj}
          </button>
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 3: Write ContasTree.tsx**

`frontend/src/components/ContasTree.tsx`:
```tsx
import type { Conta } from "../types/planoContas";

function montarArvore(contas: Conta[], paiId: number | null): Conta[] {
  return contas
    .filter((c) => c.conta_pai_id === paiId)
    .sort((a, b) => a.codigo.localeCompare(b.codigo));
}

function No({ conta, contas, nivel }: { conta: Conta; contas: Conta[]; nivel: number }) {
  const filhas = montarArvore(contas, conta.id);
  return (
    <li style={{ marginLeft: nivel * 16 }}>
      <span className="text-sm text-slate-800">
        {conta.codigo} — {conta.descricao}
        {conta.conta_analitica ? "" : " (sintética)"}
      </span>
      {filhas.length > 0 && (
        <ul>
          {filhas.map((filha) => (
            <No key={filha.id} conta={filha} contas={contas} nivel={nivel + 1} />
          ))}
        </ul>
      )}
    </li>
  );
}

export function ContasTree({ contas }: { contas: Conta[] }) {
  const raizes = montarArvore(contas, null);
  if (contas.length === 0) {
    return <p className="text-sm text-slate-500">Nenhuma conta importada ainda.</p>;
  }
  return (
    <ul>
      {raizes.map((raiz) => (
        <No key={raiz.id} conta={raiz} contas={contas} nivel={0} />
      ))}
    </ul>
  );
}
```

- [ ] **Step 4: Write PlanoContasImport.tsx**

`frontend/src/components/PlanoContasImport.tsx`:
```tsx
import { useState } from "react";
import { api } from "../api/client";
import type { Conta, ImportPreview } from "../types/planoContas";

export function PlanoContasImport({
  planoId,
  onImported,
}: {
  planoId: number;
  onImported: (contas: Conta[]) => void;
}) {
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  async function handlePreview() {
    if (!arquivo) return;
    setErro(null);
    try {
      const resultado = await api.contas.importPreview(planoId, arquivo);
      setPreview(resultado);
    } catch (err) {
      setErro((err as Error).message);
    }
  }

  async function handleConfirmar() {
    if (!arquivo) return;
    setErro(null);
    try {
      const contas = await api.contas.importConfirm(planoId, arquivo);
      setPreview(null);
      setArquivo(null);
      onImported(contas);
    } catch (err) {
      setErro((err as Error).message);
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded border border-slate-200 p-4">
      <input
        type="file"
        accept=".csv,.xlsx"
        onChange={(e) => setArquivo(e.target.files?.[0] ?? null)}
      />
      <button
        onClick={handlePreview}
        disabled={!arquivo}
        className="rounded bg-slate-200 px-3 py-1.5 text-sm text-slate-800 disabled:opacity-50"
      >
        Pré-visualizar
      </button>

      {erro && <p className="text-sm text-red-600">{erro}</p>}

      {preview && (
        <div>
          <p className="text-sm text-slate-600">
            Colunas detectadas: {JSON.stringify(preview.mapeamento)}
          </p>
          <p className="text-sm text-slate-600">{preview.linhas.length} linha(s) encontradas.</p>
          <button
            onClick={handleConfirmar}
            className="mt-2 rounded bg-slate-800 px-3 py-1.5 text-sm text-white"
          >
            Confirmar Importação
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Write EmpresasPage.tsx**

`frontend/src/pages/EmpresasPage.tsx`:
```tsx
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { ContasTree } from "../components/ContasTree";
import { EmpresaForm } from "../components/EmpresaForm";
import { EmpresaList } from "../components/EmpresaList";
import { PlanoContasImport } from "../components/PlanoContasImport";
import type { Empresa } from "../types/empresa";
import type { Conta, PlanoContas } from "../types/planoContas";

export function EmpresasPage() {
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [empresaSelecionadaId, setEmpresaSelecionadaId] = useState<number | null>(null);
  const [planos, setPlanos] = useState<PlanoContas[]>([]);
  const [planoSelecionadoId, setPlanoSelecionadoId] = useState<number | null>(null);
  const [contas, setContas] = useState<Conta[]>([]);
  const [nomePlano, setNomePlano] = useState("");

  useEffect(() => {
    api.empresas.list().then(setEmpresas);
  }, []);

  useEffect(() => {
    if (empresaSelecionadaId === null) {
      setPlanos([]);
      setPlanoSelecionadoId(null);
      return;
    }
    api.planosContas.list(empresaSelecionadaId).then(setPlanos);
  }, [empresaSelecionadaId]);

  useEffect(() => {
    if (planoSelecionadoId === null) {
      setContas([]);
      return;
    }
    api.contas.listByPlano(planoSelecionadoId).then(setContas);
  }, [planoSelecionadoId]);

  async function handleCriarPlano() {
    if (empresaSelecionadaId === null || !nomePlano) return;
    const plano = await api.planosContas.create(empresaSelecionadaId, nomePlano);
    setPlanos((atual) => [...atual, plano]);
    setNomePlano("");
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6 p-8">
      <h1 className="text-2xl font-bold text-slate-800">
        Classificador de Comprovantes — Fase 0
      </h1>

      <section className="grid grid-cols-2 gap-4">
        <EmpresaForm onCreated={(empresa) => setEmpresas((atual) => [...atual, empresa])} />
        <div>
          <h2 className="mb-2 text-sm font-semibold text-slate-700">Empresas</h2>
          <EmpresaList
            empresas={empresas}
            selectedId={empresaSelecionadaId}
            onSelect={setEmpresaSelecionadaId}
          />
        </div>
      </section>

      {empresaSelecionadaId !== null && (
        <section className="flex flex-col gap-3 border-t border-slate-200 pt-4">
          <h2 className="text-sm font-semibold text-slate-700">Planos de Contas</h2>
          <div className="flex gap-2">
            <input
              className="flex-1 rounded border border-slate-300 px-2 py-1"
              placeholder="Nome do novo plano de contas"
              value={nomePlano}
              onChange={(e) => setNomePlano(e.target.value)}
            />
            <button
              onClick={handleCriarPlano}
              className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white"
            >
              Criar
            </button>
          </div>
          <ul className="flex flex-col gap-1">
            {planos.map((plano) => (
              <li key={plano.id}>
                <button
                  onClick={() => setPlanoSelecionadoId(plano.id)}
                  className={`w-full rounded px-3 py-1.5 text-left text-sm ${
                    planoSelecionadoId === plano.id
                      ? "bg-slate-800 text-white"
                      : "bg-slate-100 text-slate-800"
                  }`}
                >
                  {plano.nome}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {planoSelecionadoId !== null && (
        <section className="grid grid-cols-2 gap-4 border-t border-slate-200 pt-4">
          <PlanoContasImport
            planoId={planoSelecionadoId}
            onImported={(novasContas) => setContas((atual) => [...atual, ...novasContas])}
          />
          <div>
            <h2 className="mb-2 text-sm font-semibold text-slate-700">Contas</h2>
            <ContasTree contas={contas} />
          </div>
        </section>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Wire EmpresasPage into App.tsx**

`frontend/src/App.tsx` (replace full content):
```tsx
import { EmpresasPage } from "./pages/EmpresasPage";

export default function App() {
  return <EmpresasPage />;
}
```

- [ ] **Step 7: Manual end-to-end verification**

With the backend running (`uvicorn app.main:app --reload` from `backend/`, after activating `.venv`) and frontend running (`npm run dev` from `frontend/`):
1. Open `http://localhost:5173`.
2. Cadastrar uma empresa via `EmpresaForm` — confirm it appears in the list.
3. Select the empresa, create a Plano de Contas.
4. Select the plano, upload `backend/tests/integration/fixtures/plano_contas_padrao.csv` via `PlanoContasImport`, click "Pré-visualizar", confirm the detected mapping and row count show correctly, click "Confirmar Importação".
5. Confirm the `ContasTree` renders the imported accounts in the correct parent/child hierarchy.

Note: the backend as built has no CORS middleware, so browser requests from `http://localhost:5173` to `http://localhost:8000` will be blocked by the browser. Before this manual verification, add CORS support:

`backend/app/main.py` — add after `app = FastAPI(...)`:
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- [ ] **Step 8: Run full backend test suite once more after the CORS change**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all tests still pass (CORS middleware doesn't affect `TestClient` behavior).

- [ ] **Step 9: Commit**

```bash
git add frontend/src backend/app/main.py
git commit -m "feat: add Empresa/Plano de Contas frontend page with CORS support"
```

---

## Post-Plan Notes

- Fase 0 is complete when all 16 tasks are committed and the manual end-to-end verification in Task 16 Step 7 passes.
- The next spec (`Fase 1 — Upload + Pipeline de OCR`) should be brainstormed separately, following `superpowers:brainstorming`, and will build on the `documentos` and `ocr_resultados` stub tables created in Task 3.
