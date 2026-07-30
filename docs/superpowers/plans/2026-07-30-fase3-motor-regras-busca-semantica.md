# Fase 3 — Motor de Regras + Busca Semântica Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Classificar automaticamente cada comprovante numa conta do plano de contas da empresa, primeiro por regras explícitas cadastradas pelo usuário, com fallback por busca fuzzy de nome contra classificações históricas.

**Architecture:** Duas tabelas novas/reais (`regras`, `classificacoes`), dois módulos de infraestrutura puros (`motor_regras.py`, `busca_fuzzy.py`) compostos por um `pipeline.py` de classificação, chamado automaticamente dentro do worker de background da Fase 1 logo após a extração (Fase 2) ser persistida. CRUD de regras via API REST + tela mínima no frontend. Painel de resultado do documento (Fase 2) ganha a classificação.

**Tech Stack:** Python/FastAPI/SQLAlchemy/Alembic (backend), React/TS/Vite/Tailwind (frontend), `rapidfuzz` para similaridade de string (já instalado como dependência transitiva, sem custo adicional).

## Global Constraints

- 100% gratuito/open-source, sem serviços pagos, sem modelo de IA/ML nesta fase (embeddings/IA generativa ficam para a Fase 4).
- Sem autenticação nesta fase.
- Execução local em Windows via terminal, sem Docker.
- SQLite agora, schema portável para PostgreSQL no futuro (tipos e constraints portáveis).
- Integração de teste de banco DEVE usar `app.infrastructure.db.session.get_engine()` (nunca `create_engine()` cru) para manter `PRAGMA foreign_keys=ON` — este projeto já regrediu nessa lição duas vezes (Fase 0 e Fase 1).
- Toda regra precisa de pelo menos UMA condição preenchida (`documento_fiscal`, `tipo_documento`, `valor_min`/`valor_max`, `palavra_chave_nome`) — regra vazia é rejeitada.
- `lado_alvo` é obrigatório sempre que `documento_fiscal` ou `palavra_chave_nome` estiver preenchido; pode ser nulo quando a regra só usa `tipo_documento`/faixa de valor.
- Entre regras que batem, a mais específica (mais condições preenchidas) vence; empate: a regra com `id` mais antigo (criado primeiro) vence.
- Busca fuzzy: SEM limiar mínimo de similaridade — sempre sugere o melhor candidato disponível, se houver histórico. Prioridade de nome: `recebedor_nome`, caindo para `pagador_nome` se ausente. Empate de score: usa o candidato histórico com `created_at` mais recente.
- Classificação roda automaticamente dentro de `processar_lote_em_background` (worker da Fase 1), logo após a `Extracao` ser persistida com sucesso — mesmo `try/except` externo já existente, SEM try/except mais estreito ao redor só da classificação (mesma decisão de severidade da extração na Fase 2).
- `conta_id` de uma regra deve apontar para uma conta ANALÍTICA (`conta_analitica=True`) pertencente a um plano de contas da mesma empresa da regra.

---

## File Structure

```
backend/
  app/
    domain/
      enums.py                                        # MODIFY: LadoRegra, OrigemClassificacao
      entities.py                                      # MODIFY: Regra, Classificacao
    core/
      exceptions.py                                    # MODIFY: novas exceções de regra/conta
    application/
      repositories.py                                  # MODIFY: RegraRepository, ClassificacaoRepository
      dto.py                                            # MODIFY: CriarRegraDTO, AtualizarRegraDTO
      use_cases/
        regra_use_cases.py                              # CREATE
        documento_use_cases.py                          # MODIFY: ObterResultadoUseCase 4-tupla
    infrastructure/
      db/
        models.py                                       # MODIFY: RegraModel, ClassificacaoModel real
      repositories/
        sqlalchemy_regra_repository.py                  # CREATE
        sqlalchemy_classificacao_repository.py          # CREATE
      classificacao/
        __init__.py                                     # CREATE
        motor_regras.py                                 # CREATE
        busca_fuzzy.py                                  # CREATE
        pipeline.py                                     # CREATE
      workers/
        lote_worker.py                                  # MODIFY: chama classificação após extração
    api/
      schemas/
        regra_schemas.py                                # CREATE
        documento_schemas.py                             # MODIFY: ClassificacaoOut
      routers/
        regras_router.py                                # CREATE
        documentos_router.py                             # MODIFY: injeta classificacao no resultado
      main.py                                            # MODIFY: registra regras_router
  alembic/versions/
    0004_fase3_motor_regras.py                          # CREATE
  requirements.txt                                       # MODIFY: rapidfuzz
  tests/
    fakes.py                                             # MODIFY: FakeRegraRepository, FakeClassificacaoRepository
    unit/
      test_regra_domain.py                               # CREATE
      test_classificacao_domain.py                       # CREATE
      test_motor_regras.py                                # CREATE
      test_busca_fuzzy.py                                 # CREATE
      test_classificacao_pipeline.py                      # CREATE
      test_regra_use_cases.py                             # CREATE
      test_documento_use_cases.py                          # MODIFY
    integration/
      test_fase3_migration.py                             # CREATE
      test_sqlalchemy_regra_repository.py                  # CREATE
      test_sqlalchemy_classificacao_repository.py          # CREATE
      test_regras_api.py                                   # CREATE
      test_lotes_api.py                                    # MODIFY
      test_documentos_api.py                               # MODIFY
frontend/
  src/
    types/
      regra.ts                                           # CREATE
      documento.ts                                        # MODIFY: Classificacao
    api/
      client.ts                                           # MODIFY: regras CRUD
    components/
      RegraForm.tsx                                       # CREATE
      RegraList.tsx                                        # CREATE
      DocumentoList.tsx                                    # MODIFY: exibe classificação
    pages/
      EmpresasPage.tsx                                     # MODIFY: seção de regras
```

---

### Task 1: Schema — `regras` (nova) + `classificacoes` (real) + enums

**Files:**
- Modify: `backend/app/domain/enums.py`
- Modify: `backend/app/infrastructure/db/models.py`
- Create: `backend/alembic/versions/0004_fase3_motor_regras.py`
- Test: `backend/tests/integration/test_fase3_migration.py`

**Interfaces:**
- Produces: `LadoRegra` (`PAGADOR`/`RECEBEDOR`), `OrigemClassificacao` (`REGRA`/`FUZZY`) em `app.domain.enums`. `RegraModel`, `ClassificacaoModel` (colunas reais) em `app.infrastructure.db.models`.

- [ ] **Step 1: Adicionar os enums**

Em `backend/app/domain/enums.py`, adicionar ao final do arquivo:

```python
class LadoRegra(str, Enum):
    PAGADOR = "PAGADOR"
    RECEBEDOR = "RECEBEDOR"


class OrigemClassificacao(str, Enum):
    REGRA = "REGRA"
    FUZZY = "FUZZY"
```

- [ ] **Step 2: Escrever o teste de migration (falhando)**

`backend/tests/integration/test_fase3_migration.py`:

```python
from sqlalchemy import create_engine, inspect
from alembic import command
from alembic.config import Config


def test_migration_cria_regras_e_classificacoes_reais(tmp_path):
    db_path = tmp_path / "test_fase3_migration.db"
    db_url = f"sqlite:///{db_path}"

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(db_url)
    inspector = inspect(engine)

    regra_cols = {c["name"] for c in inspector.get_columns("regras")}
    assert regra_cols == {
        "id", "empresa_id", "conta_id", "lado_alvo", "documento_fiscal",
        "tipo_documento", "valor_min", "valor_max", "palavra_chave_nome",
        "ativo", "created_at",
    }

    classificacao_cols = {c["name"] for c in inspector.get_columns("classificacoes")}
    assert classificacao_cols == {
        "id", "empresa_id", "documento_id", "conta_id", "origem",
        "regra_id", "score_similaridade", "created_at",
    }

    # downgrade must be symmetric
    command.downgrade(alembic_cfg, "0003")
    inspector = inspect(engine)
    classificacao_cols = {c["name"] for c in inspector.get_columns("classificacoes")}
    assert classificacao_cols == {"id", "empresa_id", "created_at"}
    assert "regras" not in inspector.get_table_names()
```

- [ ] **Step 3: Rodar o teste para confirmar que falha**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/integration/test_fase3_migration.py -v`
Expected: FAIL — a migration "0004" ainda não existe (erro do Alembic ao tentar chegar em "head").

- [ ] **Step 4: Criar a migration**

`backend/alembic/versions/0004_fase3_motor_regras.py`:

```python
"""fase3 motor de regras: tabela regras + classificacoes reais

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "regras",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("conta_id", sa.Integer, sa.ForeignKey("contas.id"), nullable=False),
        sa.Column("lado_alvo", sa.String(20), nullable=True),
        sa.Column("documento_fiscal", sa.String(14), nullable=True),
        sa.Column("tipo_documento", sa.String(20), nullable=True),
        sa.Column("valor_min", sa.Numeric(12, 2), nullable=True),
        sa.Column("valor_max", sa.Numeric(12, 2), nullable=True),
        sa.Column("palavra_chave_nome", sa.String(255), nullable=True),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.drop_table("classificacoes")
    op.create_table(
        "classificacoes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column(
            "documento_id", sa.Integer, sa.ForeignKey("documentos.id"),
            nullable=False, unique=True,
        ),
        sa.Column("conta_id", sa.Integer, sa.ForeignKey("contas.id"), nullable=False),
        sa.Column("origem", sa.String(20), nullable=False),
        sa.Column("regra_id", sa.Integer, sa.ForeignKey("regras.id"), nullable=True),
        sa.Column("score_similaridade", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("classificacoes")
    op.create_table(
        "classificacoes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.drop_table("regras")
```

Nota: no downgrade, `classificacoes` (que referencia `regras` via `regra_id`) é derrubada e recriada como o stub original ANTES de derrubar `regras` — ordem de dependência correta.

- [ ] **Step 5: Rodar o teste para confirmar que passa**

Run: `.venv/Scripts/python -m pytest tests/integration/test_fase3_migration.py -v`
Expected: PASS (1 passed)

- [ ] **Step 6: Adicionar os models SQLAlchemy**

Em `backend/app/infrastructure/db/models.py`, atualizar o import do topo de:

```python
from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
```

para:

```python
from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
```

Adicionar, logo antes de `class ClassificacaoModel(Base):`:

```python
class RegraModel(Base):
    __tablename__ = "regras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(
        ForeignKey("empresas.id"), nullable=False, index=True
    )
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id"), nullable=False)
    lado_alvo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    documento_fiscal: Mapped[str | None] = mapped_column(String(14), nullable=True)
    tipo_documento: Mapped[str | None] = mapped_column(String(20), nullable=True)
    valor_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    valor_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    palavra_chave_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

```

Substituir o `ClassificacaoModel` stub existente:

```python
class ClassificacaoModel(Base):
    __tablename__ = "classificacoes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
```

por:

```python
class ClassificacaoModel(Base):
    __tablename__ = "classificacoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(
        ForeignKey("empresas.id"), nullable=False, index=True
    )
    documento_id: Mapped[int] = mapped_column(
        ForeignKey("documentos.id"), nullable=False, unique=True
    )
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id"), nullable=False)
    origem: Mapped[str] = mapped_column(String(20), nullable=False)
    regra_id: Mapped[int | None] = mapped_column(ForeignKey("regras.id"), nullable=True)
    score_similaridade: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
```

- [ ] **Step 7: Rodar a suíte completa**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all pass (a suíte usa `Base.metadata.create_all` nos fixtures de teste, que já reflete os novos models).

- [ ] **Step 8: Commit**

```bash
git add backend/app/domain/enums.py backend/app/infrastructure/db/models.py backend/alembic/versions/0004_fase3_motor_regras.py backend/tests/integration/test_fase3_migration.py
git commit -m "feat: add regras table and real classificacoes table"
```

---

### Task 2: Domain entities `Regra` e `Classificacao` + exceções

**Files:**
- Modify: `backend/app/domain/entities.py`
- Modify: `backend/app/core/exceptions.py`
- Test: `backend/tests/unit/test_regra_domain.py`
- Test: `backend/tests/unit/test_classificacao_domain.py`

**Interfaces:**
- Consumes: `LadoRegra`, `OrigemClassificacao`, `TipoDocumento` (Task 1).
- Produces: `Regra`, `Classificacao` dataclasses em `app.domain.entities`. Exceções `ContaNaoPertenceAEmpresa`, `ContaNaoAnalitica`, `RegraNaoEncontrada`, `RegraSemCondicoes`, `RegraSemLadoAlvo` em `app.core.exceptions`.

- [ ] **Step 1: Escrever os testes das entidades (falhando)**

`backend/tests/unit/test_regra_domain.py`:

```python
from decimal import Decimal

from app.domain.entities import Regra
from app.domain.enums import LadoRegra, TipoDocumento


def test_regra_permite_todos_os_campos_opcionais_ausentes():
    regra = Regra(
        id=None, empresa_id=1, conta_id=10, lado_alvo=None, documento_fiscal=None,
        tipo_documento=TipoDocumento.PIX, valor_min=None, valor_max=None,
        palavra_chave_nome=None,
    )
    assert regra.ativo is True
    assert regra.lado_alvo is None


def test_regra_com_todos_os_campos_preenchidos():
    regra = Regra(
        id=None, empresa_id=1, conta_id=10, lado_alvo=LadoRegra.RECEBEDOR,
        documento_fiscal="12345678000195", tipo_documento=TipoDocumento.PIX,
        valor_min=Decimal("100.00"), valor_max=Decimal("500.00"),
        palavra_chave_nome="ENERGISA", ativo=False,
    )
    assert regra.lado_alvo == LadoRegra.RECEBEDOR
    assert regra.valor_min == Decimal("100.00")
    assert regra.ativo is False
```

`backend/tests/unit/test_classificacao_domain.py`:

```python
from app.domain.entities import Classificacao
from app.domain.enums import OrigemClassificacao


def test_classificacao_por_regra_nao_tem_score():
    classificacao = Classificacao(
        id=None, empresa_id=1, documento_id=1, conta_id=10,
        origem=OrigemClassificacao.REGRA, regra_id=5,
    )
    assert classificacao.score_similaridade is None
    assert classificacao.regra_id == 5


def test_classificacao_por_fuzzy_tem_score_e_sem_regra():
    classificacao = Classificacao(
        id=None, empresa_id=1, documento_id=1, conta_id=10,
        origem=OrigemClassificacao.FUZZY, score_similaridade=0.87,
    )
    assert classificacao.regra_id is None
    assert classificacao.score_similaridade == 0.87
```

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_regra_domain.py tests/unit/test_classificacao_domain.py -v`
Expected: FAIL com `ImportError` (`Regra`/`Classificacao` não existem ainda).

- [ ] **Step 3: Adicionar as entidades**

Em `backend/app/domain/entities.py`, atualizar o import do topo de:

```python
from app.domain.enums import MetodoOcr, NaturezaConta, StatusDocumento, StatusLote, TipoDocumento
```

para:

```python
from app.domain.enums import (
    LadoRegra, MetodoOcr, NaturezaConta, OrigemClassificacao, StatusDocumento, StatusLote,
    TipoDocumento,
)
```

Adicionar ao final do arquivo:

```python
@dataclass
class Regra:
    id: int | None
    empresa_id: int
    conta_id: int
    lado_alvo: LadoRegra | None
    documento_fiscal: str | None
    tipo_documento: TipoDocumento | None
    valor_min: Decimal | None
    valor_max: Decimal | None
    palavra_chave_nome: str | None
    ativo: bool = True
    created_at: datetime | None = None


@dataclass
class Classificacao:
    id: int | None
    empresa_id: int
    documento_id: int
    conta_id: int
    origem: OrigemClassificacao
    regra_id: int | None = None
    score_similaridade: float | None = None
    created_at: datetime | None = None
```

- [ ] **Step 4: Rodar os testes para confirmar que passam**

Run: `.venv/Scripts/python -m pytest tests/unit/test_regra_domain.py tests/unit/test_classificacao_domain.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Adicionar as novas exceções**

Em `backend/app/core/exceptions.py`, adicionar ao final do arquivo:

```python
class ContaNaoPertenceAEmpresa(DomainError):
    def __init__(self, conta_id: int, empresa_id: int):
        super().__init__(
            f"A conta {conta_id} não pertence a um plano de contas da empresa {empresa_id}."
        )


class ContaNaoAnalitica(DomainError):
    def __init__(self, motivo: str):
        super().__init__(motivo)


class RegraNaoEncontrada(DomainError):
    def __init__(self, regra_id: int):
        super().__init__(f"Regra {regra_id} não encontrada.")


class RegraSemCondicoes(DomainError):
    def __init__(self):
        super().__init__(
            "A regra precisa de pelo menos uma condição preenchida "
            "(documento fiscal, tipo de documento, faixa de valor ou palavra-chave)."
        )


class RegraSemLadoAlvo(DomainError):
    def __init__(self):
        super().__init__(
            "É necessário informar o lado alvo (pagador/recebedor) quando a regra usa "
            "documento fiscal ou palavra-chave no nome."
        )
```

- [ ] **Step 6: Rodar a suíte completa**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/domain/entities.py backend/app/core/exceptions.py backend/tests/unit/test_regra_domain.py backend/tests/unit/test_classificacao_domain.py
git commit -m "feat: add Regra and Classificacao domain entities"
```

---

### Task 3: Repository interfaces + fakes

**Files:**
- Modify: `backend/app/application/repositories.py`
- Modify: `backend/tests/fakes.py`

**Interfaces:**
- Consumes: `Regra`, `Classificacao` (Task 2).
- Produces: `RegraRepository` (`criar`, `obter_por_id`, `listar_por_empresa`, `atualizar`, `deletar`), `ClassificacaoRepository` (`criar`, `obter_por_documento_id`, `listar_por_empresa`) em `app.application.repositories`. `FakeRegraRepository`, `FakeClassificacaoRepository` em `tests.fakes`.

- [ ] **Step 1: Adicionar as interfaces abstratas**

Em `backend/app/application/repositories.py`, atualizar o import do topo de:

```python
from app.domain.entities import (
    Conta, Documento, Empresa, Extracao, LoteProcessamento, OcrResultado, PlanoContas,
)
```

para:

```python
from app.domain.entities import (
    Classificacao, Conta, Documento, Empresa, Extracao, LoteProcessamento, OcrResultado,
    PlanoContas, Regra,
)
```

Adicionar ao final do arquivo:

```python
class RegraRepository(ABC):
    @abstractmethod
    def criar(self, regra: Regra) -> Regra: ...

    @abstractmethod
    def obter_por_id(self, regra_id: int) -> Regra | None: ...

    @abstractmethod
    def listar_por_empresa(self, empresa_id: int) -> list[Regra]: ...

    @abstractmethod
    def atualizar(self, regra: Regra) -> Regra: ...

    @abstractmethod
    def deletar(self, regra_id: int) -> None: ...


class ClassificacaoRepository(ABC):
    @abstractmethod
    def criar(self, classificacao: Classificacao) -> Classificacao: ...

    @abstractmethod
    def obter_por_documento_id(self, documento_id: int) -> Classificacao | None: ...

    @abstractmethod
    def listar_por_empresa(self, empresa_id: int) -> list[Classificacao]: ...
```

- [ ] **Step 2: Adicionar os fakes**

Em `backend/tests/fakes.py`, atualizar os imports do topo de:

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

para:

```python
from app.application.repositories import (
    ClassificacaoRepository,
    ContaRepository,
    DocumentoRepository,
    EmpresaRepository,
    ExtracaoRepository,
    LoteProcessamentoRepository,
    OcrResultadoRepository,
    PlanoContasRepository,
    RegraRepository,
)
from app.domain.entities import (
    Classificacao, Conta, Documento, Empresa, Extracao, LoteProcessamento, OcrResultado,
    PlanoContas, Regra,
)
```

Adicionar ao final do arquivo:

```python
class FakeRegraRepository(RegraRepository):
    def __init__(self):
        self._items: dict[int, Regra] = {}
        self._next_id = 1

    def criar(self, regra: Regra) -> Regra:
        regra.id = self._next_id
        self._items[self._next_id] = regra
        self._next_id += 1
        return regra

    def obter_por_id(self, regra_id: int) -> Regra | None:
        return self._items.get(regra_id)

    def listar_por_empresa(self, empresa_id: int) -> list[Regra]:
        return [r for r in self._items.values() if r.empresa_id == empresa_id]

    def atualizar(self, regra: Regra) -> Regra:
        self._items[regra.id] = regra
        return regra

    def deletar(self, regra_id: int) -> None:
        self._items.pop(regra_id, None)


class FakeClassificacaoRepository(ClassificacaoRepository):
    def __init__(self):
        self._items: dict[int, Classificacao] = {}
        self._next_id = 1

    def criar(self, classificacao: Classificacao) -> Classificacao:
        classificacao.id = self._next_id
        self._items[self._next_id] = classificacao
        self._next_id += 1
        return classificacao

    def obter_por_documento_id(self, documento_id: int) -> Classificacao | None:
        return next(
            (c for c in self._items.values() if c.documento_id == documento_id), None
        )

    def listar_por_empresa(self, empresa_id: int) -> list[Classificacao]:
        return [c for c in self._items.values() if c.empresa_id == empresa_id]
```

- [ ] **Step 3: Verificar que os fakes satisfazem a interface**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -c "from tests.fakes import FakeRegraRepository, FakeClassificacaoRepository; FakeRegraRepository(); FakeClassificacaoRepository(); print('ok')"`
Expected: prints `ok`.

- [ ] **Step 4: Rodar a suíte completa**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/application/repositories.py backend/tests/fakes.py
git commit -m "feat: add RegraRepository and ClassificacaoRepository interfaces and fakes"
```

---

### Task 4: SQLAlchemy repositories para `Regra` e `Classificacao`

**Files:**
- Create: `backend/app/infrastructure/repositories/sqlalchemy_regra_repository.py`
- Create: `backend/app/infrastructure/repositories/sqlalchemy_classificacao_repository.py`
- Test: `backend/tests/integration/test_sqlalchemy_regra_repository.py`
- Test: `backend/tests/integration/test_sqlalchemy_classificacao_repository.py`

**Interfaces:**
- Consumes: `RegraRepository`, `ClassificacaoRepository` (Task 3), `RegraModel`, `ClassificacaoModel` (Task 1), `Regra`, `Classificacao` (Task 2), o fixture `db_session` (`backend/tests/conftest.py`).
- Produces: `SqlAlchemyRegraRepository(session)`, `SqlAlchemyClassificacaoRepository(session)`.

- [ ] **Step 1: Escrever os testes falhando**

`backend/tests/integration/test_sqlalchemy_regra_repository.py`:

```python
from decimal import Decimal

from app.domain.entities import Conta, Empresa, PlanoContas, Regra
from app.domain.enums import LadoRegra, NaturezaConta, TipoDocumento
from app.infrastructure.repositories.sqlalchemy_conta_repository import (
    SqlAlchemyContaRepository,
)
from app.infrastructure.repositories.sqlalchemy_empresa_repository import (
    SqlAlchemyEmpresaRepository,
)
from app.infrastructure.repositories.sqlalchemy_plano_contas_repository import (
    SqlAlchemyPlanoContasRepository,
)
from app.infrastructure.repositories.sqlalchemy_regra_repository import (
    SqlAlchemyRegraRepository,
)


def _empresa_e_conta(db_session):
    empresa = SqlAlchemyEmpresaRepository(db_session).criar(
        Empresa(id=None, razao_social="Tesserato", nome_fantasia=None, cnpj="12345678000199")
    )
    db_session.commit()
    plano = SqlAlchemyPlanoContasRepository(db_session).criar(
        PlanoContas(id=None, empresa_id=empresa.id, nome="Plano")
    )
    db_session.commit()
    conta = SqlAlchemyContaRepository(db_session).criar(
        Conta(
            id=None, plano_conta_id=plano.id, codigo="1", descricao="Energia",
            natureza=NaturezaConta.DESPESA, conta_analitica=True,
        )
    )
    db_session.commit()
    return empresa, conta


def test_criar_regra_com_campos_minimos(db_session):
    empresa, conta = _empresa_e_conta(db_session)
    repo = SqlAlchemyRegraRepository(db_session)

    criada = repo.criar(
        Regra(
            id=None, empresa_id=empresa.id, conta_id=conta.id, lado_alvo=None,
            documento_fiscal=None, tipo_documento=TipoDocumento.PIX,
            valor_min=None, valor_max=None, palavra_chave_nome=None,
        )
    )
    db_session.commit()

    encontrada = repo.obter_por_id(criada.id)
    assert encontrada.tipo_documento == TipoDocumento.PIX
    assert encontrada.lado_alvo is None
    assert encontrada.ativo is True


def test_criar_regra_com_todos_os_campos(db_session):
    empresa, conta = _empresa_e_conta(db_session)
    repo = SqlAlchemyRegraRepository(db_session)

    repo.criar(
        Regra(
            id=None, empresa_id=empresa.id, conta_id=conta.id,
            lado_alvo=LadoRegra.RECEBEDOR, documento_fiscal="12345678000195",
            tipo_documento=TipoDocumento.PIX, valor_min=Decimal("100.00"),
            valor_max=Decimal("500.00"), palavra_chave_nome="ENERGISA", ativo=False,
        )
    )
    db_session.commit()

    encontradas = repo.listar_por_empresa(empresa.id)
    assert len(encontradas) == 1
    assert encontradas[0].lado_alvo == LadoRegra.RECEBEDOR
    assert encontradas[0].valor_min == Decimal("100.00")
    assert encontradas[0].ativo is False


def test_atualizar_regra(db_session):
    empresa, conta = _empresa_e_conta(db_session)
    repo = SqlAlchemyRegraRepository(db_session)
    criada = repo.criar(
        Regra(
            id=None, empresa_id=empresa.id, conta_id=conta.id, lado_alvo=None,
            documento_fiscal=None, tipo_documento=TipoDocumento.PIX,
            valor_min=None, valor_max=None, palavra_chave_nome=None,
        )
    )
    db_session.commit()

    criada.ativo = False
    criada.tipo_documento = TipoDocumento.BOLETO
    repo.atualizar(criada)
    db_session.commit()

    atualizada = repo.obter_por_id(criada.id)
    assert atualizada.ativo is False
    assert atualizada.tipo_documento == TipoDocumento.BOLETO


def test_deletar_regra(db_session):
    empresa, conta = _empresa_e_conta(db_session)
    repo = SqlAlchemyRegraRepository(db_session)
    criada = repo.criar(
        Regra(
            id=None, empresa_id=empresa.id, conta_id=conta.id, lado_alvo=None,
            documento_fiscal=None, tipo_documento=TipoDocumento.PIX,
            valor_min=None, valor_max=None, palavra_chave_nome=None,
        )
    )
    db_session.commit()

    repo.deletar(criada.id)
    db_session.commit()

    assert repo.obter_por_id(criada.id) is None
```

`backend/tests/integration/test_sqlalchemy_classificacao_repository.py`:

```python
from app.domain.entities import (
    Conta, Documento, Empresa, PlanoContas,
)
from app.domain.enums import NaturezaConta, OrigemClassificacao
from app.domain.entities import Classificacao
from app.infrastructure.repositories.sqlalchemy_classificacao_repository import (
    SqlAlchemyClassificacaoRepository,
)
from app.infrastructure.repositories.sqlalchemy_conta_repository import (
    SqlAlchemyContaRepository,
)
from app.infrastructure.repositories.sqlalchemy_documento_repository import (
    SqlAlchemyDocumentoRepository,
)
from app.infrastructure.repositories.sqlalchemy_empresa_repository import (
    SqlAlchemyEmpresaRepository,
)
from app.infrastructure.repositories.sqlalchemy_plano_contas_repository import (
    SqlAlchemyPlanoContasRepository,
)


def _empresa_conta_documento(db_session):
    empresa = SqlAlchemyEmpresaRepository(db_session).criar(
        Empresa(id=None, razao_social="Tesserato", nome_fantasia=None, cnpj="12345678000199")
    )
    db_session.commit()
    plano = SqlAlchemyPlanoContasRepository(db_session).criar(
        PlanoContas(id=None, empresa_id=empresa.id, nome="Plano")
    )
    db_session.commit()
    conta = SqlAlchemyContaRepository(db_session).criar(
        Conta(
            id=None, plano_conta_id=plano.id, codigo="1", descricao="Energia",
            natureza=NaturezaConta.DESPESA, conta_analitica=True,
        )
    )
    db_session.commit()
    documento = SqlAlchemyDocumentoRepository(db_session).criar(
        Documento(
            id=None, empresa_id=empresa.id, nome_arquivo="a.pdf", nome_exibicao="a.pdf",
            caminho_arquivo="x/a.pdf", extensao=".pdf", tamanho_bytes=10,
        )
    )
    db_session.commit()
    return empresa, conta, documento


def test_criar_classificacao_por_regra(db_session):
    empresa, conta, documento = _empresa_conta_documento(db_session)
    repo = SqlAlchemyClassificacaoRepository(db_session)

    criada = repo.criar(
        Classificacao(
            id=None, empresa_id=empresa.id, documento_id=documento.id, conta_id=conta.id,
            origem=OrigemClassificacao.REGRA, regra_id=None, score_similaridade=None,
        )
    )
    db_session.commit()

    encontrada = repo.obter_por_documento_id(documento.id)
    assert encontrada.id == criada.id
    assert encontrada.origem == OrigemClassificacao.REGRA
    assert encontrada.score_similaridade is None


def test_criar_classificacao_por_fuzzy_com_score(db_session):
    empresa, conta, documento = _empresa_conta_documento(db_session)
    repo = SqlAlchemyClassificacaoRepository(db_session)

    repo.criar(
        Classificacao(
            id=None, empresa_id=empresa.id, documento_id=documento.id, conta_id=conta.id,
            origem=OrigemClassificacao.FUZZY, regra_id=None, score_similaridade=0.87,
        )
    )
    db_session.commit()

    encontradas = repo.listar_por_empresa(empresa.id)
    assert len(encontradas) == 1
    assert encontradas[0].score_similaridade == 0.87


def test_obter_por_documento_id_inexistente_retorna_none(db_session):
    repo = SqlAlchemyClassificacaoRepository(db_session)
    assert repo.obter_por_documento_id(999) is None
```

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/integration/test_sqlalchemy_regra_repository.py tests/integration/test_sqlalchemy_classificacao_repository.py -v`
Expected: FAIL com `ModuleNotFoundError`.

- [ ] **Step 3: Escrever os repositórios**

`backend/app/infrastructure/repositories/sqlalchemy_regra_repository.py`:

```python
from sqlalchemy.orm import Session

from app.application.repositories import RegraRepository
from app.domain.entities import Regra
from app.domain.enums import LadoRegra, TipoDocumento
from app.infrastructure.db.models import RegraModel


def _to_entity(model: RegraModel) -> Regra:
    return Regra(
        id=model.id,
        empresa_id=model.empresa_id,
        conta_id=model.conta_id,
        lado_alvo=LadoRegra(model.lado_alvo) if model.lado_alvo else None,
        documento_fiscal=model.documento_fiscal,
        tipo_documento=TipoDocumento(model.tipo_documento) if model.tipo_documento else None,
        valor_min=model.valor_min,
        valor_max=model.valor_max,
        palavra_chave_nome=model.palavra_chave_nome,
        ativo=model.ativo,
        created_at=model.created_at,
    )


class SqlAlchemyRegraRepository(RegraRepository):
    def __init__(self, session: Session):
        self._session = session

    def criar(self, regra: Regra) -> Regra:
        model = RegraModel(
            empresa_id=regra.empresa_id,
            conta_id=regra.conta_id,
            lado_alvo=regra.lado_alvo.value if regra.lado_alvo else None,
            documento_fiscal=regra.documento_fiscal,
            tipo_documento=regra.tipo_documento.value if regra.tipo_documento else None,
            valor_min=regra.valor_min,
            valor_max=regra.valor_max,
            palavra_chave_nome=regra.palavra_chave_nome,
            ativo=regra.ativo,
        )
        self._session.add(model)
        self._session.flush()
        return _to_entity(model)

    def obter_por_id(self, regra_id: int) -> Regra | None:
        model = self._session.get(RegraModel, regra_id)
        return _to_entity(model) if model else None

    def listar_por_empresa(self, empresa_id: int) -> list[Regra]:
        models = self._session.query(RegraModel).filter_by(empresa_id=empresa_id).all()
        return [_to_entity(m) for m in models]

    def atualizar(self, regra: Regra) -> Regra:
        model = self._session.get(RegraModel, regra.id)
        model.conta_id = regra.conta_id
        model.lado_alvo = regra.lado_alvo.value if regra.lado_alvo else None
        model.documento_fiscal = regra.documento_fiscal
        model.tipo_documento = regra.tipo_documento.value if regra.tipo_documento else None
        model.valor_min = regra.valor_min
        model.valor_max = regra.valor_max
        model.palavra_chave_nome = regra.palavra_chave_nome
        model.ativo = regra.ativo
        self._session.flush()
        return _to_entity(model)

    def deletar(self, regra_id: int) -> None:
        model = self._session.get(RegraModel, regra_id)
        if model is not None:
            self._session.delete(model)
            self._session.flush()
```

`backend/app/infrastructure/repositories/sqlalchemy_classificacao_repository.py`:

```python
from sqlalchemy.orm import Session

from app.application.repositories import ClassificacaoRepository
from app.domain.entities import Classificacao
from app.domain.enums import OrigemClassificacao
from app.infrastructure.db.models import ClassificacaoModel


def _to_entity(model: ClassificacaoModel) -> Classificacao:
    return Classificacao(
        id=model.id,
        empresa_id=model.empresa_id,
        documento_id=model.documento_id,
        conta_id=model.conta_id,
        origem=OrigemClassificacao(model.origem),
        regra_id=model.regra_id,
        score_similaridade=model.score_similaridade,
        created_at=model.created_at,
    )


class SqlAlchemyClassificacaoRepository(ClassificacaoRepository):
    def __init__(self, session: Session):
        self._session = session

    def criar(self, classificacao: Classificacao) -> Classificacao:
        model = ClassificacaoModel(
            empresa_id=classificacao.empresa_id,
            documento_id=classificacao.documento_id,
            conta_id=classificacao.conta_id,
            origem=classificacao.origem.value,
            regra_id=classificacao.regra_id,
            score_similaridade=classificacao.score_similaridade,
        )
        self._session.add(model)
        self._session.flush()
        return _to_entity(model)

    def obter_por_documento_id(self, documento_id: int) -> Classificacao | None:
        model = (
            self._session.query(ClassificacaoModel)
            .filter_by(documento_id=documento_id)
            .first()
        )
        return _to_entity(model) if model else None

    def listar_por_empresa(self, empresa_id: int) -> list[Classificacao]:
        models = (
            self._session.query(ClassificacaoModel).filter_by(empresa_id=empresa_id).all()
        )
        return [_to_entity(m) for m in models]
```

- [ ] **Step 4: Rodar os testes para confirmar que passam**

Run: `.venv/Scripts/python -m pytest tests/integration/test_sqlalchemy_regra_repository.py tests/integration/test_sqlalchemy_classificacao_repository.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Rodar a suíte completa**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/infrastructure/repositories/sqlalchemy_regra_repository.py backend/app/infrastructure/repositories/sqlalchemy_classificacao_repository.py backend/tests/integration/test_sqlalchemy_regra_repository.py backend/tests/integration/test_sqlalchemy_classificacao_repository.py
git commit -m "feat: add SqlAlchemyRegraRepository and SqlAlchemyClassificacaoRepository"
```

---

### Task 5: Motor de regras (matching + especificidade)

**Files:**
- Create: `backend/app/infrastructure/classificacao/__init__.py`
- Create: `backend/app/infrastructure/classificacao/motor_regras.py`
- Test: `backend/tests/unit/test_motor_regras.py`

**Interfaces:**
- Consumes: `Extracao` (Fase 2, `app.domain.entities`), `Regra`, `LadoRegra` (Task 2).
- Produces: `encontrar_regra_mais_especifica(extracao: Extracao, regras: list[Regra]) -> Regra | None`.

- [ ] **Step 1: Escrever o teste falhando**

`backend/tests/unit/test_motor_regras.py`:

```python
from decimal import Decimal

from app.domain.entities import Extracao, Regra
from app.domain.enums import LadoRegra, TipoDocumento
from app.infrastructure.classificacao.motor_regras import encontrar_regra_mais_especifica


def _extracao(**overrides):
    base = dict(
        id=1, documento_id=1, pagador_nome="JOAO", pagador_documento="12345678900",
        recebedor_nome="ENERGISA", recebedor_documento="12345678000195",
        valor=Decimal("150.00"), data_pagamento=None, tipo_documento=TipoDocumento.PIX,
        banco_nome=None,
    )
    base.update(overrides)
    return Extracao(**base)


def _regra(id=1, **overrides):
    base = dict(
        id=id, empresa_id=1, conta_id=10, lado_alvo=None, documento_fiscal=None,
        tipo_documento=None, valor_min=None, valor_max=None, palavra_chave_nome=None,
        ativo=True,
    )
    base.update(overrides)
    return Regra(**base)


def test_regra_por_cnpj_recebedor_bate():
    regra = _regra(lado_alvo=LadoRegra.RECEBEDOR, documento_fiscal="12345678000195")
    assert encontrar_regra_mais_especifica(_extracao(), [regra]) is regra


def test_regra_por_cnpj_nao_bate_com_documento_diferente():
    regra = _regra(lado_alvo=LadoRegra.PAGADOR, documento_fiscal="99999999999")
    assert encontrar_regra_mais_especifica(_extracao(), [regra]) is None


def test_regra_mais_especifica_vence_sobre_regra_generica():
    regra_generica = _regra(id=1, lado_alvo=LadoRegra.RECEBEDOR, documento_fiscal="12345678000195")
    regra_especifica = _regra(
        id=2, conta_id=20, lado_alvo=LadoRegra.RECEBEDOR,
        documento_fiscal="12345678000195", tipo_documento=TipoDocumento.PIX,
    )
    encontrada = encontrar_regra_mais_especifica(_extracao(), [regra_generica, regra_especifica])
    assert encontrada is regra_especifica


def test_empate_de_especificidade_regra_mais_antiga_vence():
    regra_a = _regra(id=5, conta_id=10, lado_alvo=LadoRegra.RECEBEDOR, documento_fiscal="12345678000195")
    regra_b = _regra(id=2, conta_id=20, lado_alvo=LadoRegra.RECEBEDOR, documento_fiscal="12345678000195")
    encontrada = encontrar_regra_mais_especifica(_extracao(), [regra_a, regra_b])
    assert encontrada is regra_b


def test_regra_por_faixa_de_valor():
    regra = _regra(valor_min=Decimal("100.00"), valor_max=Decimal("200.00"))
    assert encontrar_regra_mais_especifica(_extracao(valor=Decimal("150.00")), [regra]) is regra
    assert encontrar_regra_mais_especifica(_extracao(valor=Decimal("50.00")), [regra]) is None
    assert encontrar_regra_mais_especifica(_extracao(valor=None), [regra]) is None


def test_regra_por_palavra_chave_no_nome():
    regra = _regra(lado_alvo=LadoRegra.RECEBEDOR, palavra_chave_nome="ENERGISA")
    assert encontrar_regra_mais_especifica(_extracao(recebedor_nome="ENERGISA CE"), [regra]) is regra
    assert encontrar_regra_mais_especifica(_extracao(recebedor_nome="CLARO"), [regra]) is None


def test_regra_inativa_e_ignorada():
    regra = _regra(lado_alvo=LadoRegra.RECEBEDOR, documento_fiscal="12345678000195", ativo=False)
    assert encontrar_regra_mais_especifica(_extracao(), [regra]) is None


def test_sem_regras_retorna_none():
    assert encontrar_regra_mais_especifica(_extracao(), []) is None
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_motor_regras.py -v`
Expected: FAIL com `ModuleNotFoundError`.

- [ ] **Step 3: Escrever o motor de regras**

`backend/app/infrastructure/classificacao/__init__.py`: arquivo vazio.

`backend/app/infrastructure/classificacao/motor_regras.py`:

```python
from app.domain.entities import Extracao, Regra
from app.domain.enums import LadoRegra


def _nome_do_lado(extracao: Extracao, lado: LadoRegra | None) -> str | None:
    if lado == LadoRegra.PAGADOR:
        return extracao.pagador_nome
    if lado == LadoRegra.RECEBEDOR:
        return extracao.recebedor_nome
    return None


def _documento_do_lado(extracao: Extracao, lado: LadoRegra | None) -> str | None:
    if lado == LadoRegra.PAGADOR:
        return extracao.pagador_documento
    if lado == LadoRegra.RECEBEDOR:
        return extracao.recebedor_documento
    return None


def _regra_bate(regra: Regra, extracao: Extracao) -> bool:
    if regra.documento_fiscal is not None:
        if _documento_do_lado(extracao, regra.lado_alvo) != regra.documento_fiscal:
            return False
    if regra.tipo_documento is not None:
        if extracao.tipo_documento != regra.tipo_documento:
            return False
    if regra.valor_min is not None or regra.valor_max is not None:
        if extracao.valor is None:
            return False
        if regra.valor_min is not None and extracao.valor < regra.valor_min:
            return False
        if regra.valor_max is not None and extracao.valor > regra.valor_max:
            return False
    if regra.palavra_chave_nome is not None:
        nome = _nome_do_lado(extracao, regra.lado_alvo)
        if nome is None or regra.palavra_chave_nome.upper() not in nome.upper():
            return False
    return True


def _especificidade(regra: Regra) -> int:
    pontos = 0
    if regra.documento_fiscal is not None:
        pontos += 1
    if regra.tipo_documento is not None:
        pontos += 1
    if regra.valor_min is not None or regra.valor_max is not None:
        pontos += 1
    if regra.palavra_chave_nome is not None:
        pontos += 1
    return pontos


def encontrar_regra_mais_especifica(extracao: Extracao, regras: list[Regra]) -> Regra | None:
    candidatas = [r for r in regras if r.ativo and _regra_bate(r, extracao)]
    if not candidatas:
        return None
    # Mais específica vence; empate: id mais antigo (menor) vence.
    return max(candidatas, key=lambda r: (_especificidade(r), -(r.id or 0)))
```

- [ ] **Step 4: Rodar o teste para confirmar que passa**

Run: `.venv/Scripts/python -m pytest tests/unit/test_motor_regras.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/classificacao backend/tests/unit/test_motor_regras.py
git commit -m "feat: add motor de regras (matching + especificidade)"
```

---

### Task 6: Busca fuzzy (fallback por similaridade de nome)

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/app/infrastructure/classificacao/busca_fuzzy.py`
- Test: `backend/tests/unit/test_busca_fuzzy.py`

**Interfaces:**
- Produces: `buscar_conta_por_similaridade(nome_alvo: str | None, historico: list[tuple[str, int, datetime]]) -> tuple[int, float] | None` — `historico` é uma lista de `(nome, conta_id, created_at)`; retorna `(conta_id, score)` do melhor candidato, ou `None` se não houver histórico ou `nome_alvo` for `None`.

- [ ] **Step 1: Adicionar a dependência**

Em `backend/requirements.txt`, adicionar ao final do arquivo:

```
rapidfuzz==3.14.5
```

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pip install -r requirements.txt`
Expected: sucesso (já instalado como dependência transitiva do PaddleOCR nesta máquina, mas fixamos a versão explicitamente).

- [ ] **Step 2: Escrever o teste falhando**

`backend/tests/unit/test_busca_fuzzy.py`:

```python
from datetime import datetime, timezone

from app.infrastructure.classificacao.busca_fuzzy import buscar_conta_por_similaridade


def test_retorna_conta_do_nome_mais_similar():
    historico = [
        ("ENERGISA CEARA", 10, datetime(2026, 1, 1, tzinfo=timezone.utc)),
        ("CLARO SA", 20, datetime(2026, 1, 2, tzinfo=timezone.utc)),
    ]
    resultado = buscar_conta_por_similaridade("ENERGISA CE", historico)
    assert resultado is not None
    conta_id, score = resultado
    assert conta_id == 10
    assert 0.0 < score <= 1.0


def test_sem_historico_retorna_none():
    assert buscar_conta_por_similaridade("ENERGISA", []) is None


def test_nome_alvo_none_retorna_none():
    historico = [("ENERGISA", 10, datetime(2026, 1, 1, tzinfo=timezone.utc))]
    assert buscar_conta_por_similaridade(None, historico) is None


def test_empate_de_score_usa_candidato_mais_recente():
    historico = [
        ("ENERGISA", 10, datetime(2026, 1, 1, tzinfo=timezone.utc)),
        ("ENERGISA", 20, datetime(2026, 1, 5, tzinfo=timezone.utc)),
    ]
    conta_id, _ = buscar_conta_por_similaridade("ENERGISA", historico)
    assert conta_id == 20
```

- [ ] **Step 3: Rodar o teste para confirmar que falha**

Run: `.venv/Scripts/python -m pytest tests/unit/test_busca_fuzzy.py -v`
Expected: FAIL com `ModuleNotFoundError`.

- [ ] **Step 4: Escrever a busca fuzzy**

`backend/app/infrastructure/classificacao/busca_fuzzy.py`:

```python
from datetime import datetime

from rapidfuzz import fuzz


def buscar_conta_por_similaridade(
    nome_alvo: str | None, historico: list[tuple[str, int, datetime]]
) -> tuple[int, float] | None:
    if nome_alvo is None or not historico:
        return None

    melhor: tuple[int, float, datetime] | None = None
    for nome_historico, conta_id, created_at in historico:
        score = fuzz.ratio(nome_alvo.upper(), nome_historico.upper()) / 100.0
        if melhor is None:
            melhor = (conta_id, score, created_at)
            continue
        _, melhor_score, melhor_created_at = melhor
        if score > melhor_score or (score == melhor_score and created_at > melhor_created_at):
            melhor = (conta_id, score, created_at)

    if melhor is None:
        return None
    conta_id, score, _ = melhor
    return conta_id, score
```

- [ ] **Step 5: Rodar o teste para confirmar que passa**

Run: `.venv/Scripts/python -m pytest tests/unit/test_busca_fuzzy.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/app/infrastructure/classificacao/busca_fuzzy.py backend/tests/unit/test_busca_fuzzy.py
git commit -m "feat: add busca fuzzy fallback por similaridade de nome"
```

---

### Task 7: Pipeline de classificação (aggregator)

**Files:**
- Create: `backend/app/infrastructure/classificacao/pipeline.py`
- Test: `backend/tests/unit/test_classificacao_pipeline.py`

**Interfaces:**
- Consumes: `encontrar_regra_mais_especifica` (Task 5), `buscar_conta_por_similaridade` (Task 6), `Extracao`, `Regra`, `OrigemClassificacao` (Task 2).
- Produces: `ResultadoClassificacao` dataclass (`conta_id`, `origem`, `regra_id`, `score_similaridade`). `classificar_documento(extracao: Extracao, regras: list[Regra], historico_fuzzy: list[tuple[str, int, datetime]]) -> ResultadoClassificacao | None` — função pura, picklable, sem I/O (roda dentro do mesmo worker de background do OCR/extração, mesma convenção de `extrair_dados_documento` da Fase 2).

- [ ] **Step 1: Escrever o teste falhando**

`backend/tests/unit/test_classificacao_pipeline.py`:

```python
from datetime import datetime, timezone
from decimal import Decimal

from app.domain.entities import Extracao, Regra
from app.domain.enums import LadoRegra, OrigemClassificacao, TipoDocumento
from app.infrastructure.classificacao.pipeline import classificar_documento


def _extracao(**overrides):
    base = dict(
        id=1, documento_id=1, pagador_nome="JOAO", pagador_documento="12345678900",
        recebedor_nome="ENERGISA", recebedor_documento="12345678000195",
        valor=Decimal("150.00"), data_pagamento=None, tipo_documento=TipoDocumento.PIX,
        banco_nome=None,
    )
    base.update(overrides)
    return Extracao(**base)


def test_classifica_por_regra_quando_bate():
    regra = Regra(
        id=1, empresa_id=1, conta_id=10, lado_alvo=LadoRegra.RECEBEDOR,
        documento_fiscal="12345678000195", tipo_documento=None,
        valor_min=None, valor_max=None, palavra_chave_nome=None, ativo=True,
    )
    resultado = classificar_documento(_extracao(), [regra], [])
    assert resultado.origem == OrigemClassificacao.REGRA
    assert resultado.conta_id == 10
    assert resultado.regra_id == 1
    assert resultado.score_similaridade is None


def test_cai_para_fuzzy_quando_nenhuma_regra_bate():
    historico = [("ENERGISA CEARA", 20, datetime(2026, 1, 1, tzinfo=timezone.utc))]
    resultado = classificar_documento(_extracao(), [], historico)
    assert resultado.origem == OrigemClassificacao.FUZZY
    assert resultado.conta_id == 20
    assert resultado.regra_id is None
    assert resultado.score_similaridade is not None


def test_sem_regra_e_sem_historico_retorna_none():
    assert classificar_documento(_extracao(), [], []) is None


def test_usa_pagador_quando_recebedor_ausente_no_fuzzy():
    historico = [("JOAO", 30, datetime(2026, 1, 1, tzinfo=timezone.utc))]
    resultado = classificar_documento(_extracao(recebedor_nome=None), [], historico)
    assert resultado.conta_id == 30
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_classificacao_pipeline.py -v`
Expected: FAIL com `ModuleNotFoundError`.

- [ ] **Step 3: Escrever o pipeline**

`backend/app/infrastructure/classificacao/pipeline.py`:

```python
from dataclasses import dataclass
from datetime import datetime

from app.domain.entities import Extracao, Regra
from app.domain.enums import OrigemClassificacao
from app.infrastructure.classificacao.busca_fuzzy import buscar_conta_por_similaridade
from app.infrastructure.classificacao.motor_regras import encontrar_regra_mais_especifica


@dataclass
class ResultadoClassificacao:
    conta_id: int
    origem: OrigemClassificacao
    regra_id: int | None
    score_similaridade: float | None


def classificar_documento(
    extracao: Extracao,
    regras: list[Regra],
    historico_fuzzy: list[tuple[str, int, datetime]],
) -> ResultadoClassificacao | None:
    regra = encontrar_regra_mais_especifica(extracao, regras)
    if regra is not None:
        return ResultadoClassificacao(
            conta_id=regra.conta_id,
            origem=OrigemClassificacao.REGRA,
            regra_id=regra.id,
            score_similaridade=None,
        )

    nome_alvo = extracao.recebedor_nome or extracao.pagador_nome
    resultado_fuzzy = buscar_conta_por_similaridade(nome_alvo, historico_fuzzy)
    if resultado_fuzzy is None:
        return None
    conta_id, score = resultado_fuzzy
    return ResultadoClassificacao(
        conta_id=conta_id,
        origem=OrigemClassificacao.FUZZY,
        regra_id=None,
        score_similaridade=score,
    )
```

- [ ] **Step 4: Rodar o teste para confirmar que passa**

Run: `.venv/Scripts/python -m pytest tests/unit/test_classificacao_pipeline.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Rodar a suíte completa**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/infrastructure/classificacao/pipeline.py backend/tests/unit/test_classificacao_pipeline.py
git commit -m "feat: add classification pipeline aggregator"
```

---

### Task 8: Casos de uso CRUD de `Regra`

**Files:**
- Modify: `backend/app/application/dto.py`
- Create: `backend/app/application/use_cases/regra_use_cases.py`
- Test: `backend/tests/unit/test_regra_use_cases.py`

**Interfaces:**
- Consumes: `RegraRepository` (Task 3), `ContaRepository`, `PlanoContasRepository` (já existentes), `Regra`, `Conta.validar_uso_em_lancamento()` (já existente em `app.domain.entities`), exceções (Task 2).
- Produces: `CriarRegraDTO`, `AtualizarRegraDTO` em `app.application.dto`. `CriarRegraUseCase`, `ListarRegrasUseCase`, `AtualizarRegraUseCase`, `DeletarRegraUseCase` em `app.application.use_cases.regra_use_cases`.

- [ ] **Step 1: Adicionar os DTOs**

Em `backend/app/application/dto.py`, adicionar ao final do arquivo:

```python
@dataclass
class CriarRegraDTO:
    conta_id: int
    lado_alvo: str | None
    documento_fiscal: str | None
    tipo_documento: str | None
    valor_min: Decimal | None
    valor_max: Decimal | None
    palavra_chave_nome: str | None


@dataclass
class AtualizarRegraDTO:
    conta_id: int
    lado_alvo: str | None
    documento_fiscal: str | None
    tipo_documento: str | None
    valor_min: Decimal | None
    valor_max: Decimal | None
    palavra_chave_nome: str | None
    ativo: bool
```

Adicionar `from decimal import Decimal` ao topo do arquivo, junto aos demais imports (se ainda não estiver presente).

- [ ] **Step 2: Escrever o teste falhando**

`backend/tests/unit/test_regra_use_cases.py`:

```python
import pytest

from app.application.dto import AtualizarRegraDTO, CriarRegraDTO
from app.application.use_cases.regra_use_cases import (
    AtualizarRegraUseCase,
    CriarRegraUseCase,
    DeletarRegraUseCase,
    ListarRegrasUseCase,
)
from app.core.exceptions import (
    ContaNaoAnalitica,
    ContaNaoEncontrada,
    ContaNaoPertenceAEmpresa,
    RegraNaoEncontrada,
    RegraSemCondicoes,
    RegraSemLadoAlvo,
)
from app.domain.entities import Conta, PlanoContas
from app.domain.enums import NaturezaConta
from tests.fakes import FakeContaRepository, FakePlanoContasRepository, FakeRegraRepository


def _plano_e_conta(plano_repo, conta_repo, empresa_id=1, conta_analitica=True):
    plano = plano_repo.criar(PlanoContas(id=None, empresa_id=empresa_id, nome="Plano"))
    conta = conta_repo.criar(
        Conta(
            id=None, plano_conta_id=plano.id, codigo="1", descricao="Energia",
            natureza=NaturezaConta.DESPESA, conta_analitica=conta_analitica,
        )
    )
    return plano, conta


def _dto(conta_id, **overrides):
    base = dict(
        conta_id=conta_id, lado_alvo="RECEBEDOR", documento_fiscal="12345678000195",
        tipo_documento=None, valor_min=None, valor_max=None, palavra_chave_nome=None,
    )
    base.update(overrides)
    return CriarRegraDTO(**base)


def test_criar_regra_com_sucesso():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    _, conta = _plano_e_conta(plano_repo, conta_repo, empresa_id=1)

    regra = CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, _dto(conta.id))

    assert regra.id is not None
    assert regra.empresa_id == 1
    assert regra.conta_id == conta.id


def test_criar_regra_com_conta_inexistente_falha():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()

    with pytest.raises(ContaNaoEncontrada):
        CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, _dto(999))


def test_criar_regra_com_conta_de_outra_empresa_falha():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    _, conta = _plano_e_conta(plano_repo, conta_repo, empresa_id=2)

    with pytest.raises(ContaNaoPertenceAEmpresa):
        CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, _dto(conta.id))


def test_criar_regra_com_conta_sintetica_falha():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    _, conta = _plano_e_conta(plano_repo, conta_repo, empresa_id=1, conta_analitica=False)

    with pytest.raises(ContaNaoAnalitica):
        CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, _dto(conta.id))


def test_criar_regra_sem_nenhuma_condicao_falha():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    _, conta = _plano_e_conta(plano_repo, conta_repo, empresa_id=1)
    dto = _dto(
        conta.id, lado_alvo=None, documento_fiscal=None, tipo_documento=None,
        valor_min=None, valor_max=None, palavra_chave_nome=None,
    )

    with pytest.raises(RegraSemCondicoes):
        CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, dto)


def test_criar_regra_com_palavra_chave_sem_lado_alvo_falha():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    _, conta = _plano_e_conta(plano_repo, conta_repo, empresa_id=1)
    dto = _dto(
        conta.id, lado_alvo=None, documento_fiscal=None, tipo_documento=None,
        valor_min=None, valor_max=None, palavra_chave_nome="ENERGISA",
    )

    with pytest.raises(RegraSemLadoAlvo):
        CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, dto)


def test_listar_regras_por_empresa():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    _, conta = _plano_e_conta(plano_repo, conta_repo, empresa_id=1)
    CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, _dto(conta.id))

    regras = ListarRegrasUseCase(regra_repo).executar(1)

    assert len(regras) == 1


def test_atualizar_regra_com_sucesso():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    _, conta = _plano_e_conta(plano_repo, conta_repo, empresa_id=1)
    criada = CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, _dto(conta.id))

    dto_update = AtualizarRegraDTO(
        conta_id=conta.id, lado_alvo="RECEBEDOR", documento_fiscal="99999999000191",
        tipo_documento=None, valor_min=None, valor_max=None, palavra_chave_nome=None,
        ativo=False,
    )
    atualizada = AtualizarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(
        1, criada.id, dto_update
    )

    assert atualizada.documento_fiscal == "99999999000191"
    assert atualizada.ativo is False


def test_atualizar_regra_inexistente_falha():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    _, conta = _plano_e_conta(plano_repo, conta_repo, empresa_id=1)
    dto_update = AtualizarRegraDTO(
        conta_id=conta.id, lado_alvo="RECEBEDOR", documento_fiscal="99999999000191",
        tipo_documento=None, valor_min=None, valor_max=None, palavra_chave_nome=None,
        ativo=True,
    )

    with pytest.raises(RegraNaoEncontrada):
        AtualizarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, 999, dto_update)


def test_atualizar_regra_de_outra_empresa_falha():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    _, conta = _plano_e_conta(plano_repo, conta_repo, empresa_id=1)
    criada = CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, _dto(conta.id))
    dto_update = AtualizarRegraDTO(
        conta_id=conta.id, lado_alvo="RECEBEDOR", documento_fiscal="99999999000191",
        tipo_documento=None, valor_min=None, valor_max=None, palavra_chave_nome=None,
        ativo=True,
    )

    with pytest.raises(RegraNaoEncontrada):
        AtualizarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(2, criada.id, dto_update)


def test_deletar_regra():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    _, conta = _plano_e_conta(plano_repo, conta_repo, empresa_id=1)
    criada = CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, _dto(conta.id))

    DeletarRegraUseCase(regra_repo).executar(1, criada.id)

    assert regra_repo.obter_por_id(criada.id) is None


def test_deletar_regra_de_outra_empresa_falha():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    _, conta = _plano_e_conta(plano_repo, conta_repo, empresa_id=1)
    criada = CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, _dto(conta.id))

    with pytest.raises(RegraNaoEncontrada):
        DeletarRegraUseCase(regra_repo).executar(2, criada.id)
```

- [ ] **Step 3: Rodar o teste para confirmar que falha**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_regra_use_cases.py -v`
Expected: FAIL com `ModuleNotFoundError`.

- [ ] **Step 4: Escrever os casos de uso**

`backend/app/application/use_cases/regra_use_cases.py`:

```python
from app.application.dto import AtualizarRegraDTO, CriarRegraDTO
from app.application.repositories import ContaRepository, PlanoContasRepository, RegraRepository
from app.core.exceptions import (
    ContaNaoAnalitica,
    ContaNaoEncontrada,
    ContaNaoPertenceAEmpresa,
    RegraNaoEncontrada,
    RegraSemCondicoes,
    RegraSemLadoAlvo,
)
from app.domain.entities import Regra
from app.domain.enums import LadoRegra, TipoDocumento


def _validar_conta(
    conta_repo: ContaRepository, plano_repo: PlanoContasRepository, conta_id: int, empresa_id: int
):
    conta = conta_repo.obter_por_id(conta_id)
    if conta is None:
        raise ContaNaoEncontrada(conta_id)
    plano = plano_repo.obter_por_id(conta.plano_conta_id)
    if plano is None or plano.empresa_id != empresa_id:
        raise ContaNaoPertenceAEmpresa(conta_id, empresa_id)
    try:
        conta.validar_uso_em_lancamento()
    except ValueError as exc:
        raise ContaNaoAnalitica(str(exc)) from exc


def _validar_condicoes(
    documento_fiscal: str | None,
    tipo_documento: str | None,
    valor_min,
    valor_max,
    palavra_chave_nome: str | None,
    lado_alvo: str | None,
) -> None:
    condicoes = [documento_fiscal, tipo_documento, valor_min, valor_max, palavra_chave_nome]
    if all(c is None for c in condicoes):
        raise RegraSemCondicoes()
    if (documento_fiscal is not None or palavra_chave_nome is not None) and lado_alvo is None:
        raise RegraSemLadoAlvo()


class CriarRegraUseCase:
    def __init__(
        self, repo: RegraRepository, conta_repo: ContaRepository, plano_repo: PlanoContasRepository
    ):
        self._repo = repo
        self._conta_repo = conta_repo
        self._plano_repo = plano_repo

    def executar(self, empresa_id: int, dto: CriarRegraDTO) -> Regra:
        _validar_conta(self._conta_repo, self._plano_repo, dto.conta_id, empresa_id)
        _validar_condicoes(
            dto.documento_fiscal, dto.tipo_documento, dto.valor_min, dto.valor_max,
            dto.palavra_chave_nome, dto.lado_alvo,
        )
        regra = Regra(
            id=None,
            empresa_id=empresa_id,
            conta_id=dto.conta_id,
            lado_alvo=LadoRegra(dto.lado_alvo) if dto.lado_alvo else None,
            documento_fiscal=dto.documento_fiscal,
            tipo_documento=TipoDocumento(dto.tipo_documento) if dto.tipo_documento else None,
            valor_min=dto.valor_min,
            valor_max=dto.valor_max,
            palavra_chave_nome=dto.palavra_chave_nome,
            ativo=True,
        )
        return self._repo.criar(regra)


class ListarRegrasUseCase:
    def __init__(self, repo: RegraRepository):
        self._repo = repo

    def executar(self, empresa_id: int) -> list[Regra]:
        return self._repo.listar_por_empresa(empresa_id)


class AtualizarRegraUseCase:
    def __init__(
        self, repo: RegraRepository, conta_repo: ContaRepository, plano_repo: PlanoContasRepository
    ):
        self._repo = repo
        self._conta_repo = conta_repo
        self._plano_repo = plano_repo

    def executar(self, empresa_id: int, regra_id: int, dto: AtualizarRegraDTO) -> Regra:
        regra = self._repo.obter_por_id(regra_id)
        if regra is None or regra.empresa_id != empresa_id:
            raise RegraNaoEncontrada(regra_id)
        _validar_conta(self._conta_repo, self._plano_repo, dto.conta_id, empresa_id)
        _validar_condicoes(
            dto.documento_fiscal, dto.tipo_documento, dto.valor_min, dto.valor_max,
            dto.palavra_chave_nome, dto.lado_alvo,
        )
        regra.conta_id = dto.conta_id
        regra.lado_alvo = LadoRegra(dto.lado_alvo) if dto.lado_alvo else None
        regra.documento_fiscal = dto.documento_fiscal
        regra.tipo_documento = TipoDocumento(dto.tipo_documento) if dto.tipo_documento else None
        regra.valor_min = dto.valor_min
        regra.valor_max = dto.valor_max
        regra.palavra_chave_nome = dto.palavra_chave_nome
        regra.ativo = dto.ativo
        return self._repo.atualizar(regra)


class DeletarRegraUseCase:
    def __init__(self, repo: RegraRepository):
        self._repo = repo

    def executar(self, empresa_id: int, regra_id: int) -> None:
        regra = self._repo.obter_por_id(regra_id)
        if regra is None or regra.empresa_id != empresa_id:
            raise RegraNaoEncontrada(regra_id)
        self._repo.deletar(regra_id)
```

- [ ] **Step 5: Rodar o teste para confirmar que passa**

Run: `.venv/Scripts/python -m pytest tests/unit/test_regra_use_cases.py -v`
Expected: PASS (12 passed)

- [ ] **Step 6: Rodar a suíte completa**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/application/dto.py backend/app/application/use_cases/regra_use_cases.py backend/tests/unit/test_regra_use_cases.py
git commit -m "feat: add Regra CRUD use cases"
```

---

### Task 9: API de regras (schemas + router)

**Files:**
- Create: `backend/app/api/schemas/regra_schemas.py`
- Create: `backend/app/api/routers/regras_router.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/integration/test_regras_api.py`

**Interfaces:**
- Consumes: `CriarRegraUseCase`, `ListarRegrasUseCase`, `AtualizarRegraUseCase`, `DeletarRegraUseCase` (Task 8), `SqlAlchemyRegraRepository` (Task 4), `SqlAlchemyContaRepository`/`SqlAlchemyPlanoContasRepository` (já existentes).
- Produces: `RegraCreateIn`, `RegraUpdateIn`, `RegraOut` em `app.api.schemas.regra_schemas`. Rotas `POST/GET /empresas/{empresa_id}/regras`, `PATCH/DELETE /empresas/{empresa_id}/regras/{regra_id}`.

- [ ] **Step 1: Escrever o teste falhando**

`backend/tests/integration/test_regras_api.py`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.infrastructure.db.base import Base
from app.infrastructure.db import models  # noqa: F401
from app.infrastructure.db.session import get_engine
from app.main import app


@pytest.fixture
def client():
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

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def conta_id(client):
    empresa_id = client.post(
        "/empresas", json={"razao_social": "Tesserato", "nome_fantasia": None, "cnpj": "12345678000199"}
    ).json()["id"]
    plano_id = client.post(
        f"/empresas/{empresa_id}/planos-contas", json={"nome": "Plano"}
    ).json()["id"]
    conta = client.post(
        f"/planos-contas/{plano_id}/contas",
        json={
            "codigo": "1", "descricao": "Energia", "natureza": "DESPESA",
            "conta_analitica": True, "conta_pai_id": None,
        },
    ).json()
    return empresa_id, conta["id"]


def test_criar_listar_atualizar_e_deletar_regra(client, conta_id):
    empresa_id, conta_id_ = conta_id

    resposta_criar = client.post(
        f"/empresas/{empresa_id}/regras",
        json={
            "conta_id": conta_id_, "lado_alvo": "RECEBEDOR",
            "documento_fiscal": "12345678000195", "tipo_documento": None,
            "valor_min": None, "valor_max": None, "palavra_chave_nome": None,
        },
    )
    assert resposta_criar.status_code == 201
    regra_id = resposta_criar.json()["id"]
    assert resposta_criar.json()["ativo"] is True

    resposta_listar = client.get(f"/empresas/{empresa_id}/regras")
    assert resposta_listar.status_code == 200
    assert len(resposta_listar.json()) == 1

    resposta_atualizar = client.patch(
        f"/empresas/{empresa_id}/regras/{regra_id}",
        json={
            "conta_id": conta_id_, "lado_alvo": "RECEBEDOR",
            "documento_fiscal": "12345678000195", "tipo_documento": None,
            "valor_min": None, "valor_max": None, "palavra_chave_nome": None,
            "ativo": False,
        },
    )
    assert resposta_atualizar.status_code == 200
    assert resposta_atualizar.json()["ativo"] is False

    resposta_deletar = client.delete(f"/empresas/{empresa_id}/regras/{regra_id}")
    assert resposta_deletar.status_code == 204
    assert client.get(f"/empresas/{empresa_id}/regras").json() == []


def test_criar_regra_sem_condicoes_retorna_400(client, conta_id):
    empresa_id, conta_id_ = conta_id

    resposta = client.post(
        f"/empresas/{empresa_id}/regras",
        json={
            "conta_id": conta_id_, "lado_alvo": None, "documento_fiscal": None,
            "tipo_documento": None, "valor_min": None, "valor_max": None,
            "palavra_chave_nome": None,
        },
    )
    assert resposta.status_code == 400


def test_criar_regra_com_conta_inexistente_retorna_404(client):
    empresa_id = client.post(
        "/empresas", json={"razao_social": "Tesserato", "nome_fantasia": None, "cnpj": "12345678000199"}
    ).json()["id"]

    resposta = client.post(
        f"/empresas/{empresa_id}/regras",
        json={
            "conta_id": 999, "lado_alvo": "RECEBEDOR", "documento_fiscal": "12345678000195",
            "tipo_documento": None, "valor_min": None, "valor_max": None,
            "palavra_chave_nome": None,
        },
    )
    assert resposta.status_code == 404
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/integration/test_regras_api.py -v`
Expected: FAIL — rota `/empresas/{empresa_id}/regras` não existe ainda (404 do FastAPI para rota não registrada).

- [ ] **Step 3: Escrever os schemas**

`backend/app/api/schemas/regra_schemas.py`:

```python
from decimal import Decimal

from pydantic import BaseModel

from app.domain.enums import LadoRegra, TipoDocumento


class RegraCreateIn(BaseModel):
    conta_id: int
    lado_alvo: LadoRegra | None = None
    documento_fiscal: str | None = None
    tipo_documento: TipoDocumento | None = None
    valor_min: Decimal | None = None
    valor_max: Decimal | None = None
    palavra_chave_nome: str | None = None


class RegraUpdateIn(RegraCreateIn):
    ativo: bool = True


class RegraOut(BaseModel):
    id: int
    empresa_id: int
    conta_id: int
    lado_alvo: LadoRegra | None
    documento_fiscal: str | None
    tipo_documento: TipoDocumento | None
    valor_min: str | None
    valor_max: str | None
    palavra_chave_nome: str | None
    ativo: bool

    @classmethod
    def from_regra(cls, regra) -> "RegraOut":
        return cls(
            id=regra.id,
            empresa_id=regra.empresa_id,
            conta_id=regra.conta_id,
            lado_alvo=regra.lado_alvo,
            documento_fiscal=regra.documento_fiscal,
            tipo_documento=regra.tipo_documento,
            valor_min=str(regra.valor_min) if regra.valor_min is not None else None,
            valor_max=str(regra.valor_max) if regra.valor_max is not None else None,
            palavra_chave_nome=regra.palavra_chave_nome,
            ativo=regra.ativo,
        )
```

- [ ] **Step 4: Escrever o router**

`backend/app/api/routers/regras_router.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.schemas.regra_schemas import RegraCreateIn, RegraOut, RegraUpdateIn
from app.application.dto import AtualizarRegraDTO, CriarRegraDTO
from app.application.use_cases.regra_use_cases import (
    AtualizarRegraUseCase,
    CriarRegraUseCase,
    DeletarRegraUseCase,
    ListarRegrasUseCase,
)
from app.core.exceptions import (
    ContaNaoAnalitica,
    ContaNaoEncontrada,
    ContaNaoPertenceAEmpresa,
    RegraNaoEncontrada,
    RegraSemCondicoes,
    RegraSemLadoAlvo,
)
from app.infrastructure.repositories.sqlalchemy_conta_repository import (
    SqlAlchemyContaRepository,
)
from app.infrastructure.repositories.sqlalchemy_plano_contas_repository import (
    SqlAlchemyPlanoContasRepository,
)
from app.infrastructure.repositories.sqlalchemy_regra_repository import (
    SqlAlchemyRegraRepository,
)

router = APIRouter(tags=["regras"])


def _dto_criar(payload: RegraCreateIn) -> CriarRegraDTO:
    return CriarRegraDTO(
        conta_id=payload.conta_id,
        lado_alvo=payload.lado_alvo.value if payload.lado_alvo else None,
        documento_fiscal=payload.documento_fiscal,
        tipo_documento=payload.tipo_documento.value if payload.tipo_documento else None,
        valor_min=payload.valor_min,
        valor_max=payload.valor_max,
        palavra_chave_nome=payload.palavra_chave_nome,
    )


@router.post(
    "/empresas/{empresa_id}/regras", response_model=RegraOut, status_code=status.HTTP_201_CREATED
)
def criar_regra(empresa_id: int, payload: RegraCreateIn, db: Session = Depends(get_db)):
    regra_repo = SqlAlchemyRegraRepository(db)
    conta_repo = SqlAlchemyContaRepository(db)
    plano_repo = SqlAlchemyPlanoContasRepository(db)
    try:
        regra = CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(
            empresa_id, _dto_criar(payload)
        )
    except ContaNaoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ContaNaoPertenceAEmpresa, ContaNaoAnalitica, RegraSemCondicoes, RegraSemLadoAlvo) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RegraOut.from_regra(regra)


@router.get("/empresas/{empresa_id}/regras", response_model=list[RegraOut])
def listar_regras(empresa_id: int, db: Session = Depends(get_db)):
    repo = SqlAlchemyRegraRepository(db)
    regras = ListarRegrasUseCase(repo).executar(empresa_id)
    return [RegraOut.from_regra(r) for r in regras]


@router.patch("/empresas/{empresa_id}/regras/{regra_id}", response_model=RegraOut)
def atualizar_regra(
    empresa_id: int, regra_id: int, payload: RegraUpdateIn, db: Session = Depends(get_db)
):
    regra_repo = SqlAlchemyRegraRepository(db)
    conta_repo = SqlAlchemyContaRepository(db)
    plano_repo = SqlAlchemyPlanoContasRepository(db)
    dto = AtualizarRegraDTO(
        conta_id=payload.conta_id,
        lado_alvo=payload.lado_alvo.value if payload.lado_alvo else None,
        documento_fiscal=payload.documento_fiscal,
        tipo_documento=payload.tipo_documento.value if payload.tipo_documento else None,
        valor_min=payload.valor_min,
        valor_max=payload.valor_max,
        palavra_chave_nome=payload.palavra_chave_nome,
        ativo=payload.ativo,
    )
    try:
        regra = AtualizarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(
            empresa_id, regra_id, dto
        )
    except (RegraNaoEncontrada, ContaNaoEncontrada) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ContaNaoPertenceAEmpresa, ContaNaoAnalitica, RegraSemCondicoes, RegraSemLadoAlvo) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RegraOut.from_regra(regra)


@router.delete("/empresas/{empresa_id}/regras/{regra_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_regra(empresa_id: int, regra_id: int, db: Session = Depends(get_db)):
    repo = SqlAlchemyRegraRepository(db)
    try:
        DeletarRegraUseCase(repo).executar(empresa_id, regra_id)
    except RegraNaoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

- [ ] **Step 5: Registrar o router**

Em `backend/app/main.py`, atualizar o import do topo de:

```python
from app.api.routers.contas_router import router as contas_router
from app.api.routers.documentos_router import router as documentos_router
from app.api.routers.empresas_router import router as empresas_router
from app.api.routers.lotes_router import router as lotes_router
from app.api.routers.planos_contas_router import router as planos_contas_router
```

para:

```python
from app.api.routers.contas_router import router as contas_router
from app.api.routers.documentos_router import router as documentos_router
from app.api.routers.empresas_router import router as empresas_router
from app.api.routers.lotes_router import router as lotes_router
from app.api.routers.planos_contas_router import router as planos_contas_router
from app.api.routers.regras_router import router as regras_router
```

E adicionar, junto às demais chamadas `app.include_router(...)`:

```python
app.include_router(regras_router)
```

- [ ] **Step 6: Rodar o teste para confirmar que passa**

Run: `.venv/Scripts/python -m pytest tests/integration/test_regras_api.py -v`
Expected: PASS (3 passed)

- [ ] **Step 7: Rodar a suíte completa**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/schemas/regra_schemas.py backend/app/api/routers/regras_router.py backend/app/main.py backend/tests/integration/test_regras_api.py
git commit -m "feat: add Regra CRUD API"
```

---

### Task 10: Rodar classificação dentro do worker de OCR

**Files:**
- Modify: `backend/app/infrastructure/workers/lote_worker.py`
- Modify: `backend/tests/integration/test_lotes_api.py`

**Interfaces:**
- Consumes: `classificar_documento` (Task 7), `SqlAlchemyRegraRepository`, `SqlAlchemyClassificacaoRepository` (Task 4), `Classificacao` (Task 2).
- Produces: nenhuma interface pública nova — `processar_lote_em_background` agora também classifica e persiste uma `Classificacao` para todo documento cuja extração foi persistida com sucesso.

**Current content of `backend/app/infrastructure/workers/lote_worker.py` você está modificando** (leia o arquivo você mesmo para confirmar que ainda bate com isto antes de editar):

O corpo de `processar_lote_em_background`, dentro do `for futuro in as_completed(futuros):`, no ramo de sucesso, atualmente faz:

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

- [ ] **Step 1: Escrever o teste de integração falhando**

Adicionar este teste a `backend/tests/integration/test_lotes_api.py`, próximo a `test_processar_lote_extrai_dados_do_documento` (reusando os fixtures `client`/`empresa_id` já existentes no arquivo):

```python
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
```

Este teste depende das mudanças de Task 11 na API (`resultado["classificacao"]`) para passar completamente — assim como o teste equivalente da Fase 2 (Task 12), rode-o agora e espere falha especificamente em `resultado["classificacao"]` (`KeyError`), não no processamento do lote em si. Re-rode após a Task 11 e confirme que passa totalmente (adicione esse re-run como parte da verificação da Task 11).

- [ ] **Step 2: Rodar o teste para confirmar que falha apenas no ponto esperado**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/integration/test_lotes_api.py::test_processar_lote_classifica_documento_por_regra -v`
Expected: FAIL com `KeyError: 'classificacao'` (o lote chega em `CONCLUIDO` normalmente).

- [ ] **Step 3: Ligar a classificação no worker**

Em `backend/app/infrastructure/workers/lote_worker.py`, atualizar o import do topo de:

```python
from app.domain.entities import Extracao, OcrResultado
```

para:

```python
from app.domain.entities import Classificacao, Extracao, OcrResultado
```

Adicionar, junto ao import de `extrair_dados_documento`:

```python
from app.infrastructure.classificacao.pipeline import classificar_documento
```

Dentro de `processar_lote_em_background`, adicionar os dois novos repositórios junto aos já construídos no topo da função:

```python
        documento_repo = SqlAlchemyDocumentoRepository(session)
        resultado_repo = SqlAlchemyOcrResultadoRepository(session)
        extracao_repo = SqlAlchemyExtracaoRepository(session)
        lote_repo = SqlAlchemyLoteProcessamentoRepository(session)
        storage = LocalFileStorageService(Path(storage_root))
```

vira:

```python
        documento_repo = SqlAlchemyDocumentoRepository(session)
        resultado_repo = SqlAlchemyOcrResultadoRepository(session)
        extracao_repo = SqlAlchemyExtracaoRepository(session)
        regra_repo = SqlAlchemyRegraRepository(session)
        classificacao_repo = SqlAlchemyClassificacaoRepository(session)
        lote_repo = SqlAlchemyLoteProcessamentoRepository(session)
        storage = LocalFileStorageService(Path(storage_root))
```

Adicionar os imports dos novos repositórios, junto aos demais imports de repositórios da função (o bloco que começa com `from app.infrastructure.repositories.sqlalchemy_documento_repository import (`):

```python
    from app.infrastructure.repositories.sqlalchemy_regra_repository import (
        SqlAlchemyRegraRepository,
    )
    from app.infrastructure.repositories.sqlalchemy_classificacao_repository import (
        SqlAlchemyClassificacaoRepository,
    )
```

Alterar o ramo de sucesso do laço `as_completed` de:

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

para:

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

                    regras = regra_repo.listar_por_empresa(documento.empresa_id)
                    historico_fuzzy = []
                    for classificacao_existente in classificacao_repo.listar_por_empresa(
                        documento.empresa_id
                    ):
                        extracao_historica = extracao_repo.obter_por_documento_id(
                            classificacao_existente.documento_id
                        )
                        if extracao_historica is None:
                            continue
                        nome_historico = (
                            extracao_historica.recebedor_nome or extracao_historica.pagador_nome
                        )
                        if nome_historico is None:
                            continue
                        historico_fuzzy.append(
                            (
                                nome_historico,
                                classificacao_existente.conta_id,
                                classificacao_existente.created_at,
                            )
                        )

                    resultado_classificacao = classificar_documento(
                        extracao_criada, regras, historico_fuzzy
                    )
                    if resultado_classificacao is not None:
                        classificacao_repo.criar(
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
                documento_repo.atualizar(documento)
```

Nota: assim como a extração (Fase 2, Task 12), este bloco fica dentro do MESMO `try/except` externo que já envolve todo o corpo do worker — uma exceção dentro da classificação (teoricamente rara, já que é lógica pura sobre dados já em memória) leva o lote inteiro a `FALHOU`, mesma decisão de severidade já usada para a extração. Não adicione um `try/except` mais estreito ao redor só da classificação.

- [ ] **Step 4: Rodar o teste para confirmar que ainda falha só no ponto esperado**

Run: `.venv/Scripts/python -m pytest tests/integration/test_lotes_api.py::test_processar_lote_classifica_documento_por_regra -v`
Expected: ainda FAIL com `KeyError: 'classificacao'` — o worker agora cria a `Classificacao`, mas a API não devolve o campo até a Task 11.

- [ ] **Step 5: Rodar a suíte completa**

Run: `.venv/Scripts/python -m pytest -v`
Expected: todos os testes previamente passando continuam passando; o novo teste falha apenas como descrito acima (esperado e aceitável neste ponto do plano).

- [ ] **Step 6: Commit**

```bash
git add backend/app/infrastructure/workers/lote_worker.py backend/tests/integration/test_lotes_api.py
git commit -m "feat: run classification after extraction in the background worker"
```

---

### Task 11: Estender `GET /documentos/{id}/resultado` com a classificação

**Files:**
- Modify: `backend/app/api/schemas/documento_schemas.py`
- Modify: `backend/app/api/routers/documentos_router.py`
- Modify: `backend/app/application/use_cases/documento_use_cases.py`
- Test: `backend/tests/unit/test_documento_use_cases.py`
- Test: `backend/tests/integration/test_documentos_api.py`

**Interfaces:**
- Consumes: `ClassificacaoRepository` (Task 3), `SqlAlchemyClassificacaoRepository` (Task 4), `Classificacao` (Task 2), `ContaRepository`/`SqlAlchemyContaRepository` (já existentes).
- Produces: `ClassificacaoOut` schema. `ObterResultadoUseCase.executar` agora retorna uma 4-tupla `tuple[Documento, OcrResultado | None, Extracao | None, Classificacao | None]` (era 3-tupla) — mudança de assinatura no único call site existente (`documentos_router.py`), mesmo padrão da Fase 2 (Task 13).

- [ ] **Step 1: Escrever o teste unitário falhando para a mudança de assinatura**

Em `backend/tests/unit/test_documento_use_cases.py`, atualizar o teste EXISTENTE `test_obter_resultado_documento_inexistente_falha` — seu corpo atual é:

```python
def test_obter_resultado_documento_inexistente_falha():
    documento_repo = FakeDocumentoRepository()
    resultado_repo = FakeOcrResultadoRepository()
    extracao_repo = FakeExtracaoRepository()

    with pytest.raises(DocumentoNaoEncontrado):
        ObterResultadoUseCase(documento_repo, resultado_repo, extracao_repo).executar(999)
```

Mudar para também construir um `FakeClassificacaoRepository` e passá-lo como quarto argumento do construtor:

```python
def test_obter_resultado_documento_inexistente_falha():
    documento_repo = FakeDocumentoRepository()
    resultado_repo = FakeOcrResultadoRepository()
    extracao_repo = FakeExtracaoRepository()
    classificacao_repo = FakeClassificacaoRepository()

    with pytest.raises(DocumentoNaoEncontrado):
        ObterResultadoUseCase(
            documento_repo, resultado_repo, extracao_repo, classificacao_repo
        ).executar(999)
```

Atualizar os dois testes existentes `test_obter_resultado_retorna_extracao_quando_existe` e `test_obter_resultado_extracao_none_quando_nao_existe` para também construir e passar `classificacao_repo = FakeClassificacaoRepository()` como quarto argumento e desempacotar 4 valores (`documento, resultado, extracao, classificacao = ObterResultadoUseCase(...).executar(...)`, ignorando `classificacao` com `_` onde não for usado).

Adicionar estes dois testes NOVOS próximos aos demais:

```python
def test_obter_resultado_retorna_classificacao_quando_existe():
    documento_repo = FakeDocumentoRepository()
    resultado_repo = FakeOcrResultadoRepository()
    extracao_repo = FakeExtracaoRepository()
    classificacao_repo = FakeClassificacaoRepository()
    empresa_repo = FakeEmpresaRepository()
    empresa = _empresa(empresa_repo)
    storage = FakeArmazenamentoArquivos()
    resultados_upload = UploadarDocumentosUseCase(documento_repo, empresa_repo, storage).executar(
        empresa.id, [ArquivoUploadDTO(nome_original="a.pdf", conteudo=b"x")]
    )
    documento_id = resultados_upload[0].documento.id
    classificacao_repo.criar(
        Classificacao(
            id=None, empresa_id=empresa.id, documento_id=documento_id, conta_id=10,
            origem=OrigemClassificacao.REGRA, regra_id=1,
        )
    )

    _, _, _, classificacao = ObterResultadoUseCase(
        documento_repo, resultado_repo, extracao_repo, classificacao_repo
    ).executar(documento_id)

    assert classificacao is not None
    assert classificacao.conta_id == 10


def test_obter_resultado_classificacao_none_quando_nao_existe():
    documento_repo = FakeDocumentoRepository()
    resultado_repo = FakeOcrResultadoRepository()
    extracao_repo = FakeExtracaoRepository()
    classificacao_repo = FakeClassificacaoRepository()
    empresa_repo = FakeEmpresaRepository()
    empresa = _empresa(empresa_repo)
    storage = FakeArmazenamentoArquivos()
    resultados_upload = UploadarDocumentosUseCase(documento_repo, empresa_repo, storage).executar(
        empresa.id, [ArquivoUploadDTO(nome_original="a.pdf", conteudo=b"x")]
    )
    documento_id = resultados_upload[0].documento.id

    _, _, _, classificacao = ObterResultadoUseCase(
        documento_repo, resultado_repo, extracao_repo, classificacao_repo
    ).executar(documento_id)

    assert classificacao is None
```

Adicionar `FakeClassificacaoRepository` ao import existente de `tests.fakes`, e `Classificacao`, `OrigemClassificacao` aos imports existentes de `app.domain.entities`/`app.domain.enums` no topo do arquivo (não duplique as linhas de import já existentes — estenda-as).

- [ ] **Step 2: Rodar o teste para confirmar que falha**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_documento_use_cases.py -v`
Expected: FAIL — `ObterResultadoUseCase.__init__` ainda não aceita um quarto argumento.

- [ ] **Step 3: Atualizar `ObterResultadoUseCase`**

Em `backend/app/application/use_cases/documento_use_cases.py`, atualizar o import do topo de:

```python
from app.application.repositories import (
    DocumentoRepository,
    EmpresaRepository,
    ExtracaoRepository,
    OcrResultadoRepository,
)
```

para:

```python
from app.application.repositories import (
    ClassificacaoRepository,
    DocumentoRepository,
    EmpresaRepository,
    ExtracaoRepository,
    OcrResultadoRepository,
)
```

e:

```python
from app.domain.entities import Documento, Extracao, OcrResultado
```

para:

```python
from app.domain.entities import Classificacao, Documento, Extracao, OcrResultado
```

Substituir a classe `ObterResultadoUseCase` por:

```python
class ObterResultadoUseCase:
    def __init__(
        self,
        documento_repo: DocumentoRepository,
        resultado_repo: OcrResultadoRepository,
        extracao_repo: ExtracaoRepository,
        classificacao_repo: ClassificacaoRepository,
    ):
        self._documento_repo = documento_repo
        self._resultado_repo = resultado_repo
        self._extracao_repo = extracao_repo
        self._classificacao_repo = classificacao_repo

    def executar(
        self, documento_id: int
    ) -> tuple[Documento, OcrResultado | None, Extracao | None, Classificacao | None]:
        documento = self._documento_repo.obter_por_id(documento_id)
        if documento is None:
            raise DocumentoNaoEncontrado(documento_id)
        resultado = self._resultado_repo.obter_por_documento_id(documento_id)
        extracao = self._extracao_repo.obter_por_documento_id(documento_id)
        classificacao = self._classificacao_repo.obter_por_documento_id(documento_id)
        return documento, resultado, extracao, classificacao
```

- [ ] **Step 4: Rodar o teste para confirmar que passa**

Run: `.venv/Scripts/python -m pytest tests/unit/test_documento_use_cases.py -v`
Expected: PASS.

- [ ] **Step 5: Adicionar o schema `ClassificacaoOut`**

Em `backend/app/api/schemas/documento_schemas.py`, atualizar o import do topo de:

```python
from app.domain.enums import MetodoOcr, StatusDocumento, TipoDocumento
```

para:

```python
from app.domain.enums import MetodoOcr, OrigemClassificacao, StatusDocumento, TipoDocumento
```

Adicionar, depois de `ExtracaoOut`:

```python
class ClassificacaoOut(BaseModel):
    conta_id: int
    conta_codigo: str
    conta_descricao: str
    origem: OrigemClassificacao
    regra_id: int | None
    score_similaridade: float | None

    @classmethod
    def from_classificacao(cls, classificacao, conta) -> "ClassificacaoOut":
        return cls(
            conta_id=classificacao.conta_id,
            conta_codigo=conta.codigo,
            conta_descricao=conta.descricao,
            origem=classificacao.origem,
            regra_id=classificacao.regra_id,
            score_similaridade=classificacao.score_similaridade,
        )
```

Atualizar `DocumentoResultadoOut` de:

```python
class DocumentoResultadoOut(BaseModel):
    documento: DocumentoOut
    resultado: OcrResultadoOut | None
    extracao: ExtracaoOut | None
```

para:

```python
class DocumentoResultadoOut(BaseModel):
    documento: DocumentoOut
    resultado: OcrResultadoOut | None
    extracao: ExtracaoOut | None
    classificacao: ClassificacaoOut | None
```

Nota de design: `ClassificacaoOut` embute o código e a descrição da conta (via um lookup adicional feito no router, não no use case) em vez de expor só `conta_id` — isso evita o frontend precisar resolver `conta_id` contra uma lista de contas separadamente carregada, o que seria frágil já que o painel de documentos não necessariamente tem o plano de contas certo selecionado no estado local.

- [ ] **Step 6: Atualizar o router**

Em `backend/app/api/routers/documentos_router.py`, atualizar o import de:

```python
from app.api.schemas.documento_schemas import (
    DocumentoOut,
    DocumentoResultadoOut,
    ExtracaoOut,
    OcrResultadoOut,
    UploadItemOut,
)
```

para:

```python
from app.api.schemas.documento_schemas import (
    ClassificacaoOut,
    DocumentoOut,
    DocumentoResultadoOut,
    ExtracaoOut,
    OcrResultadoOut,
    UploadItemOut,
)
```

Adicionar aos imports:

```python
from app.infrastructure.repositories.sqlalchemy_classificacao_repository import (
    SqlAlchemyClassificacaoRepository,
)
from app.infrastructure.repositories.sqlalchemy_conta_repository import (
    SqlAlchemyContaRepository,
)
```

Substituir a função `obter_resultado` por:

```python
@router.get("/documentos/{documento_id}/resultado", response_model=DocumentoResultadoOut)
def obter_resultado(documento_id: int, db: Session = Depends(get_db)):
    documento_repo = SqlAlchemyDocumentoRepository(db)
    resultado_repo = SqlAlchemyOcrResultadoRepository(db)
    extracao_repo = SqlAlchemyExtracaoRepository(db)
    classificacao_repo = SqlAlchemyClassificacaoRepository(db)
    conta_repo = SqlAlchemyContaRepository(db)
    try:
        documento, resultado, extracao, classificacao = ObterResultadoUseCase(
            documento_repo, resultado_repo, extracao_repo, classificacao_repo
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
    classificacao_out = None
    if classificacao:
        conta = conta_repo.obter_por_id(classificacao.conta_id)
        classificacao_out = ClassificacaoOut.from_classificacao(classificacao, conta)
    return DocumentoResultadoOut(
        documento=documento, resultado=resultado_out, extracao=extracao_out,
        classificacao=classificacao_out,
    )
```

- [ ] **Step 7: Estender o teste de integração da API de documentos**

Em `backend/tests/integration/test_documentos_api.py`, na função `test_upload_lista_e_obtem_resultado_de_documento`, adicionar a asserção do novo campo logo junto das já existentes:

```python
    assert body["resultado"] is None
    assert body["extracao"] is None
```

vira:

```python
    assert body["resultado"] is None
    assert body["extracao"] is None
    assert body["classificacao"] is None
```

- [ ] **Step 8: Rodar o teste de classificação da Task 10 (agora deve passar totalmente)**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/integration/test_lotes_api.py::test_processar_lote_classifica_documento_por_regra -v`
Expected: PASS agora (era o teste deliberadamente deixado incompleto na Task 10).

- [ ] **Step 9: Rodar a suíte completa**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add backend/app/api/schemas/documento_schemas.py backend/app/api/routers/documentos_router.py backend/app/application/use_cases/documento_use_cases.py backend/tests/unit/test_documento_use_cases.py backend/tests/integration/test_documentos_api.py
git commit -m "feat: expose classification via GET /documentos/{id}/resultado"
```

---

### Task 12: Frontend — tipos de `Regra` + cliente de API

**Files:**
- Create: `frontend/src/types/regra.ts`
- Modify: `frontend/src/api/client.ts`

**Interfaces:**
- Consumes: `TipoDocumento` (já existe em `frontend/src/types/documento.ts`).
- Produces: `Regra`, `RegraCreateInput`, `RegraUpdateInput`, `LadoRegra` em `frontend/src/types/regra.ts`. `api.regras.{list,create,update,remove}` em `frontend/src/api/client.ts`.

- [ ] **Step 1: Criar o arquivo de tipos**

`frontend/src/types/regra.ts`:

```ts
import type { TipoDocumento } from "./documento";

export type LadoRegra = "PAGADOR" | "RECEBEDOR";

export interface Regra {
  id: number;
  empresa_id: number;
  conta_id: number;
  lado_alvo: LadoRegra | null;
  documento_fiscal: string | null;
  tipo_documento: TipoDocumento | null;
  valor_min: string | null;
  valor_max: string | null;
  palavra_chave_nome: string | null;
  ativo: boolean;
}

export interface RegraCreateInput {
  conta_id: number;
  lado_alvo: LadoRegra | null;
  documento_fiscal: string | null;
  tipo_documento: TipoDocumento | null;
  valor_min: string | null;
  valor_max: string | null;
  palavra_chave_nome: string | null;
}

export interface RegraUpdateInput extends RegraCreateInput {
  ativo: boolean;
}
```

- [ ] **Step 2: Adicionar os métodos ao cliente de API**

Em `frontend/src/api/client.ts`, adicionar ao import do topo:

```ts
import type { Regra, RegraCreateInput, RegraUpdateInput } from "../types/regra";
```

Adicionar, dentro do objeto `api`, junto aos demais recursos (ex: depois de `lotes: {...}`):

```ts
  regras: {
    list: (empresaId: number) => request<Regra[]>(`/empresas/${empresaId}/regras`),
    create: (empresaId: number, input: RegraCreateInput) =>
      request<Regra>(`/empresas/${empresaId}/regras`, {
        method: "POST",
        body: JSON.stringify(input),
      }),
    update: (empresaId: number, regraId: number, input: RegraUpdateInput) =>
      request<Regra>(`/empresas/${empresaId}/regras/${regraId}`, {
        method: "PATCH",
        body: JSON.stringify(input),
      }),
    remove: (empresaId: number, regraId: number) =>
      request<void>(`/empresas/${empresaId}/regras/${regraId}`, { method: "DELETE" }),
  },
```

- [ ] **Step 3: Verificar tipos**

Run: `cd "D:/DEV/Teste Lançamentos/frontend" && npx tsc --noEmit`
Expected: sucesso, sem erros (nada ainda consome `api.regras`, então isto só confirma que os tipos são consistentes).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/regra.ts frontend/src/api/client.ts
git commit -m "feat: add Regra types and API client methods"
```

---

### Task 13: Frontend — componentes `RegraForm` e `RegraList`

**Files:**
- Create: `frontend/src/components/RegraForm.tsx`
- Create: `frontend/src/components/RegraList.tsx`

**Interfaces:**
- Consumes: `Regra`, `RegraCreateInput`, `LadoRegra` (Task 12), `Conta` (`frontend/src/types/planoContas.ts`, já existe), `TipoDocumento` (`frontend/src/types/documento.ts`, já existe), `api.regras` (Task 12).
- Produces: `RegraForm` (props: `empresaId: number`, `contas: Conta[]`, `onCreated: (regra: Regra) => void`). `RegraList` (props: `empresaId: number`, `regras: Regra[]`, `contas: Conta[]`, `onChanged: (regras: Regra[]) => void`).

- [ ] **Step 1: Criar o formulário**

`frontend/src/components/RegraForm.tsx`:

```tsx
import { useState } from "react";
import { api } from "../api/client";
import type { TipoDocumento } from "../types/documento";
import type { Conta } from "../types/planoContas";
import type { LadoRegra, Regra } from "../types/regra";

const TIPOS_DOCUMENTO: TipoDocumento[] = ["PIX", "TED", "DOC", "BOLETO", "OUTRO"];

export function RegraForm({
  empresaId,
  contas,
  onCreated,
}: {
  empresaId: number;
  contas: Conta[];
  onCreated: (regra: Regra) => void;
}) {
  const [contaId, setContaId] = useState<number | "">("");
  const [ladoAlvo, setLadoAlvo] = useState<LadoRegra | "">("");
  const [documentoFiscal, setDocumentoFiscal] = useState("");
  const [tipoDocumento, setTipoDocumento] = useState<TipoDocumento | "">("");
  const [valorMin, setValorMin] = useState("");
  const [valorMax, setValorMax] = useState("");
  const [palavraChave, setPalavraChave] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    if (contaId === "") return;
    try {
      const regra = await api.regras.create(empresaId, {
        conta_id: contaId,
        lado_alvo: ladoAlvo || null,
        documento_fiscal: documentoFiscal || null,
        tipo_documento: tipoDocumento || null,
        valor_min: valorMin || null,
        valor_max: valorMax || null,
        palavra_chave_nome: palavraChave || null,
      });
      setContaId("");
      setLadoAlvo("");
      setDocumentoFiscal("");
      setTipoDocumento("");
      setValorMin("");
      setValorMax("");
      setPalavraChave("");
      onCreated(regra);
    } catch (err) {
      setErro((err as Error).message);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-2 rounded border border-slate-200 p-4">
      <label className="text-sm font-medium text-slate-700">
        Conta
        <select
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
          value={contaId}
          onChange={(e) => setContaId(e.target.value ? Number(e.target.value) : "")}
          required
        >
          <option value="">Selecione...</option>
          {contas.map((conta) => (
            <option key={conta.id} value={conta.id}>
              {conta.codigo} — {conta.descricao}
            </option>
          ))}
        </select>
      </label>
      <label className="text-sm font-medium text-slate-700">
        Lado alvo (CNPJ/palavra-chave)
        <select
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
          value={ladoAlvo}
          onChange={(e) => setLadoAlvo(e.target.value as LadoRegra | "")}
        >
          <option value="">Nenhum</option>
          <option value="PAGADOR">Pagador</option>
          <option value="RECEBEDOR">Recebedor</option>
        </select>
      </label>
      <label className="text-sm font-medium text-slate-700">
        CNPJ/CPF
        <input
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
          value={documentoFiscal}
          onChange={(e) => setDocumentoFiscal(e.target.value)}
          placeholder="Somente dígitos"
        />
      </label>
      <label className="text-sm font-medium text-slate-700">
        Tipo de documento
        <select
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
          value={tipoDocumento}
          onChange={(e) => setTipoDocumento(e.target.value as TipoDocumento | "")}
        >
          <option value="">Qualquer</option>
          {TIPOS_DOCUMENTO.map((tipo) => (
            <option key={tipo} value={tipo}>
              {tipo}
            </option>
          ))}
        </select>
      </label>
      <div className="flex gap-2">
        <label className="flex-1 text-sm font-medium text-slate-700">
          Valor mínimo
          <input
            className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
            value={valorMin}
            onChange={(e) => setValorMin(e.target.value)}
            placeholder="0.00"
          />
        </label>
        <label className="flex-1 text-sm font-medium text-slate-700">
          Valor máximo
          <input
            className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
            value={valorMax}
            onChange={(e) => setValorMax(e.target.value)}
            placeholder="0.00"
          />
        </label>
      </div>
      <label className="text-sm font-medium text-slate-700">
        Palavra-chave no nome
        <input
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
          value={palavraChave}
          onChange={(e) => setPalavraChave(e.target.value)}
        />
      </label>
      {erro && <p className="text-sm text-red-600">{erro}</p>}
      <button type="submit" className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white">
        Cadastrar Regra
      </button>
    </form>
  );
}
```

- [ ] **Step 2: Criar a lista**

`frontend/src/components/RegraList.tsx`:

```tsx
import { api } from "../api/client";
import type { Conta } from "../types/planoContas";
import type { Regra } from "../types/regra";

function descricaoConta(contas: Conta[], contaId: number): string {
  const conta = contas.find((c) => c.id === contaId);
  return conta ? `${conta.codigo} — ${conta.descricao}` : `Conta ${contaId}`;
}

function resumoCondicoes(regra: Regra): string {
  const partes: string[] = [];
  if (regra.documento_fiscal) partes.push(`CNPJ/CPF ${regra.lado_alvo}: ${regra.documento_fiscal}`);
  if (regra.tipo_documento) partes.push(`Tipo: ${regra.tipo_documento}`);
  if (regra.valor_min || regra.valor_max) {
    partes.push(`Valor: ${regra.valor_min ?? "0"} a ${regra.valor_max ?? "∞"}`);
  }
  if (regra.palavra_chave_nome) {
    partes.push(`Palavra-chave (${regra.lado_alvo}): "${regra.palavra_chave_nome}"`);
  }
  return partes.join(" · ");
}

export function RegraList({
  empresaId,
  regras,
  contas,
  onChanged,
}: {
  empresaId: number;
  regras: Regra[];
  contas: Conta[];
  onChanged: (regras: Regra[]) => void;
}) {
  async function alternarAtivo(regra: Regra) {
    const atualizada = await api.regras.update(empresaId, regra.id, {
      conta_id: regra.conta_id,
      lado_alvo: regra.lado_alvo,
      documento_fiscal: regra.documento_fiscal,
      tipo_documento: regra.tipo_documento,
      valor_min: regra.valor_min,
      valor_max: regra.valor_max,
      palavra_chave_nome: regra.palavra_chave_nome,
      ativo: !regra.ativo,
    });
    onChanged(regras.map((r) => (r.id === atualizada.id ? atualizada : r)));
  }

  async function apagar(regraId: number) {
    await api.regras.remove(empresaId, regraId);
    onChanged(regras.filter((r) => r.id !== regraId));
  }

  if (regras.length === 0) {
    return <p className="text-sm text-slate-500">Nenhuma regra cadastrada ainda.</p>;
  }

  return (
    <ul className="flex flex-col gap-1">
      {regras.map((regra) => (
        <li
          key={regra.id}
          className="flex items-center justify-between gap-2 rounded border border-slate-200 px-3 py-1.5 text-sm"
        >
          <div>
            <p className="font-medium text-slate-800">{descricaoConta(contas, regra.conta_id)}</p>
            <p className="text-xs text-slate-500">{resumoCondicoes(regra)}</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => alternarAtivo(regra)}
              className={`rounded px-2 py-0.5 text-xs ${
                regra.ativo ? "bg-green-100 text-green-800" : "bg-slate-200 text-slate-600"
              }`}
            >
              {regra.ativo ? "Ativa" : "Inativa"}
            </button>
            <button
              onClick={() => apagar(regra.id)}
              className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-700"
            >
              Apagar
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 3: Verificar tipos**

Run: `cd "D:/DEV/Teste Lançamentos/frontend" && npx tsc --noEmit`
Expected: sucesso (os componentes ainda não são importados por nenhuma página, mas devem compilar isoladamente).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/RegraForm.tsx frontend/src/components/RegraList.tsx
git commit -m "feat: add RegraForm and RegraList components"
```

---

### Task 14: Frontend — seção de regras na página da empresa

**Files:**
- Modify: `frontend/src/pages/EmpresasPage.tsx`

**Interfaces:**
- Consumes: `RegraForm`, `RegraList` (Task 13), `api.regras` (Task 12), estado `contas`/`empresaSelecionadaId` já existente em `EmpresasPage`.

- [ ] **Step 1: Adicionar o estado e o carregamento de regras**

Em `frontend/src/pages/EmpresasPage.tsx`, adicionar aos imports do topo:

```tsx
import { RegraForm } from "../components/RegraForm";
import { RegraList } from "../components/RegraList";
import type { Regra } from "../types/regra";
```

Adicionar, junto às demais declarações de estado (perto de `const [contas, setContas] = useState<Conta[]>([]);`):

```tsx
  const [regras, setRegras] = useState<Regra[]>([]);
```

Adicionar um `useEffect` que recarrega as regras sempre que a empresa selecionada mudar, próximo ao `useEffect` que já recarrega `documentos`:

```tsx
  useEffect(() => {
    if (empresaSelecionadaId === null) {
      setRegras([]);
      return;
    }
    api.regras.list(empresaSelecionadaId).then(setRegras);
  }, [empresaSelecionadaId]);
```

- [ ] **Step 2: Renderizar a seção de regras**

Adicionar uma nova `<section>`, logo após a seção de "Contas" existente (o bloco que começa com `{planoSelecionadoId !== null && (`), ainda dentro do `return (...)` de `EmpresasPage`:

```tsx
      {empresaSelecionadaId !== null && (
        <section className="grid grid-cols-2 gap-4 border-t border-slate-200 pt-4">
          <RegraForm
            empresaId={empresaSelecionadaId}
            contas={contas}
            onCreated={(regra) => setRegras((atual) => [...atual, regra])}
          />
          <div>
            <h2 className="mb-2 text-sm font-semibold text-slate-700">Regras de Classificação</h2>
            <RegraList
              empresaId={empresaSelecionadaId}
              regras={regras}
              contas={contas}
              onChanged={setRegras}
            />
          </div>
        </section>
      )}
```

Nota: esta seção usa o mesmo estado `contas` já carregado para o plano selecionado — se nenhum plano estiver selecionado, `contas` fica vazio e o formulário mostra a lista de contas vazia (comportamento aceitável para esta fase; o usuário precisa ter um plano de contas selecionado antes de cadastrar regras, mesma dependência lógica que já existe entre planos e contas nesta página).

- [ ] **Step 3: Verificar tipos e build**

Run: `cd "D:/DEV/Teste Lançamentos/frontend" && npx tsc --noEmit && npm run build`
Expected: ambos sucesso.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/EmpresasPage.tsx
git commit -m "feat: add regras section to EmpresasPage"
```

---

### Task 15: Frontend — exibir classificação no resultado + verificação manual

**Files:**
- Modify: `frontend/src/types/documento.ts`
- Modify: `frontend/src/components/DocumentoList.tsx`

**Interfaces:**
- Consumes: `ClassificacaoOut` (Task 11).
- Produces: `Classificacao` TS interface. `DocumentoResultado.classificacao: Classificacao | null`.

- [ ] **Step 1: Adicionar o tipo**

Em `frontend/src/types/documento.ts`, adicionar após a interface `Extracao`:

```ts
export type OrigemClassificacao = "REGRA" | "FUZZY";

export interface Classificacao {
  conta_id: number;
  conta_codigo: string;
  conta_descricao: string;
  origem: OrigemClassificacao;
  regra_id: number | null;
  score_similaridade: number | null;
}
```

Atualizar `DocumentoResultado` de:

```ts
export interface DocumentoResultado {
  documento: Documento;
  resultado: OcrResultadoDetalhe | null;
  extracao: Extracao | null;
}
```

para:

```ts
export interface DocumentoResultado {
  documento: Documento;
  resultado: OcrResultadoDetalhe | null;
  extracao: Extracao | null;
  classificacao: Classificacao | null;
}
```

- [ ] **Step 2: Renderizar a classificação**

Em `frontend/src/components/DocumentoList.tsx`, adicionar um bloco de classificação dentro do `<div>` de `resultadoAberto`, logo após o `<div>` de campos extraídos (`{resultadoAberto.extracao && (...)}`)  e antes do parágrafo de "Método:":

```tsx
          <div className="mb-3 rounded border border-slate-200 bg-white p-2">
            <span className="font-semibold">Classificação: </span>
            {resultadoAberto.classificacao ? (
              <span>
                {resultadoAberto.classificacao.conta_codigo} —{" "}
                {resultadoAberto.classificacao.conta_descricao} (
                {resultadoAberto.classificacao.origem === "REGRA" ? "por regra" : "sugestão por similaridade"}
                {resultadoAberto.classificacao.score_similaridade !== null &&
                  ` — ${Math.round(resultadoAberto.classificacao.score_similaridade * 100)}%`}
                )
              </span>
            ) : (
              <span>SEM CLASSIFICAÇÃO</span>
            )}
          </div>
```

- [ ] **Step 3: Verificar tipos e build**

Run: `cd "D:/DEV/Teste Lançamentos/frontend" && npx tsc --noEmit && npm run build`
Expected: ambos sucesso.

- [ ] **Step 4: Rodar a suíte de backend mais uma vez**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest -v`
Expected: all pass. Esta é a Fase 3 completa, backend + frontend.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/documento.ts frontend/src/components/DocumentoList.tsx
git commit -m "feat: display classification in the results panel"
```

- [ ] **Step 6: Verificação manual end-to-end (feita pelo controller com ferramentas de navegador, não por um implementador subagente sem elas)**

Com o backend rodando (`uvicorn app.main:app --reload` a partir de `backend/`, depois de `alembic upgrade head`) e o frontend rodando (`npm run dev` a partir de `frontend/`):

1. Abrir `http://localhost:5173`, selecionar ou criar uma empresa.
2. Criar um plano de contas e uma conta analítica (ex: código `1`, descrição "Energia Elétrica", natureza DESPESA).
3. Na nova seção "Regras de Classificação", cadastrar uma regra: lado alvo Recebedor, CNPJ de um fornecedor de teste (ex: `12345678000195`), apontando para a conta criada.
4. Fazer upload de um PDF sintético (mesmo processo usado na Fase 2 — script curto com PyMuPDF) com texto incluindo `"Favorecido: Fornecedor Teste\nCNPJ: 12.345.678/0001-95\nValor: R$ 100,00"`.
5. Clicar "Processar", esperar `CONCLUIDO`.
6. Clicar "Ver texto" e confirmar que a linha de Classificação mostra a conta cadastrada com "(por regra)".
7. Cadastrar um segundo documento com um CNPJ de fornecedor DIFERENTE (sem regra cadastrada para ele) mas nome de fornecedor parecido com o primeiro (ex: "Fornecedor Teste Ltda" variando o CNPJ) e confirmar que a classificação cai para "(sugestão por similaridade)" com um percentual mostrado.
8. Fazer upload de um terceiro documento sem nenhum campo reconhecível e confirmar que a linha de Classificação mostra "SEM CLASSIFICAÇÃO".

---

## Post-Plan Notes

- Fase 3 está completa quando todas as 15 tarefas estiverem commitadas e a verificação manual da Task 15 passar.
- O próximo spec (`Fase 4 — Camada de IA + Aprendizado`) deve ser brainstormado separadamente, seguindo `superpowers:brainstorming`. Vai consumir as classificações desta fase como ponto de partida para aprendizado a partir de correções manuais do usuário (tabela `aprendizado`, ainda stub).
- A renomeação de `nome_exibicao` para o formato "Tipo - Data" (adiada da Fase 1 para "o início da Fase 3" nas notas da Fase 2) NÃO foi incluída neste plano — é uma mudança isolada e ortogonal ao motor de regras/busca semântica; deve ser tratada como uma tarefa avulsa antes ou depois deste plano, à critério do usuário, não como parte deste ciclo design → plano → implementação.
