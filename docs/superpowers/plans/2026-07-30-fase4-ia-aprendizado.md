# Fase 4 — Camada de IA + Aprendizado Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Estender a cadeia de classificação da Fase 3 (REGRA → FUZZY) com um fallback por IA local (Ollama) no meio — REGRA → IA → FUZZY — e adicionar uma ação mínima de correção manual no painel de resultado que aprende automaticamente criando/atualizando uma `Regra` (Fase 3) a cada correção.

**Architecture:** Um módulo novo de infraestrutura (`app/infrastructure/ia/ollama_classificador.py`) faz uma chamada HTTP resiliente (nunca lança exceção) ao servidor Ollama local, com um prompt fechado (escolher entre códigos de conta oferecidos) e parsing estrito da resposta. O pipeline de classificação da Fase 3 ganha essa etapa no meio. Um novo use case (`CorrigirClassificacaoUseCase`) trata a correção manual, criando/atualizando uma `Regra` pelo CNPJ/CPF do recebedor (fallback pagador) e registrando um log de auditoria na tabela `aprendizado` (ganha colunas reais nesta fase).

**Tech Stack:** Python/FastAPI/SQLAlchemy/Alembic (backend), React/TS/Vite/Tailwind (frontend), `httpx` (já é dependência do projeto) para chamar a API REST do Ollama local, sem biblioteca cliente nova.

## Global Constraints

- 100% gratuito/open-source, sem serviços pagos. O Ollama já está instalado e rodando
  localmente nesta máquina (`http://localhost:11434`), com o modelo `llama3.2` já baixado
  (`ollama pull llama3.2`) — não é necessário fazer setup do Ollama nesta implementação.
- Sem autenticação nesta fase.
- Execução local em Windows via terminal, sem Docker.
- SQLite agora, schema portável para PostgreSQL no futuro.
- **A chamada à IA NUNCA pode derrubar o lote/documento.** É uma exceção deliberada à
  regra geral de "sem try/except mais estreito" das Fases 2/3 — a IA é uma dependência
  externa OPCIONAL (pode não estar disponível), não um bug de lógica da aplicação. A
  função que chama o Ollama captura toda exceção internamente (conexão recusada, timeout,
  resposta malformada) e retorna `None` — nunca propaga. Se falhar, a cadeia cai
  automaticamente pro fuzzy.
- Cadeia de classificação final: **REGRA → IA → FUZZY**. IA só é tentada se nenhuma
  regra bateu; fuzzy só é tentado se a IA não deu uma resposta utilizável.
- O prompt da IA é FECHADO (escolher um código de conta entre os oferecidos, ou
  `NENHUMA`) — nunca geração de texto livre. O parsing da resposta é estrito: só aceita
  se o texto bater EXATAMENTE com um dos códigos oferecidos (após `strip()` e
  normalização de case); qualquer outra coisa (incluindo `NENHUMA`) vira `None`.
- Correção manual: `PATCH /documentos/{documento_id}/classificacao` recebe `conta_id`.
  Sempre registra um log em `aprendizado`. Se o documento tiver `recebedor_documento`
  identificado, cria/atualiza uma `Regra` (`lado_alvo=RECEBEDOR`); senão, tenta
  `pagador_documento` (`lado_alvo=PAGADOR`); se nenhum dos dois, não cria/atualiza regra
  nenhuma (só corrige a classificação deste documento).
- Se já existir uma regra pro mesmo `documento_fiscal` + `lado_alvo` na empresa, a
  correção ATUALIZA essa regra (não cria uma duplicada).
- `conta_id` da correção precisa ser uma conta analítica de um plano de contas da mesma
  empresa do documento — mesma validação já usada na Fase 3 (`ContaNaoEncontrada`,
  `ContaNaoPertenceAEmpresa`, `ContaNaoAnalitica`).
- Integration test DB fixtures must go through `app.infrastructure.db.session.get_engine()`
  — este projeto já regrediu nessa lição várias vezes (Fases 0, 1 e por pouco na 3).

---

## File Structure

```
backend/
  app/
    core/
      config.py                                       # MODIFY: ollama_host, ollama_model, ollama_timeout_segundos
    domain/
      enums.py                                         # MODIFY: OrigemClassificacao ganha IA, MANUAL
      entities.py                                       # MODIFY: Aprendizado
    application/
      repositories.py                                   # MODIFY: AprendizadoRepository, ClassificacaoRepository.atualizar
      use_cases/
        classificacao_use_cases.py                       # CREATE: CorrigirClassificacaoUseCase
    infrastructure/
      db/
        models.py                                        # MODIFY: AprendizadoModel real
      repositories/
        sqlalchemy_aprendizado_repository.py              # CREATE
        sqlalchemy_classificacao_repository.py            # MODIFY: atualizar()
      ia/
        __init__.py                                       # CREATE
        ollama_classificador.py                           # CREATE
      classificacao/
        pipeline.py                                       # MODIFY: chama classificar_por_ia
      workers/
        lote_worker.py                                     # MODIFY: carrega contas_disponiveis, passa ao pipeline
    api/
      schemas/
        documento_schemas.py                              # MODIFY: CorrigirClassificacaoIn
      routers/
        documentos_router.py                              # MODIFY: PATCH /documentos/{id}/classificacao
  alembic/versions/
    0005_fase4_ia_aprendizado.py                          # CREATE
  tests/
    fakes.py                                              # MODIFY: FakeAprendizadoRepository, FakeClassificacaoRepository.atualizar
    unit/
      test_ollama_classificador.py                        # CREATE
      test_classificacao_pipeline.py                       # MODIFY
      test_classificacao_use_cases.py                      # CREATE
    integration/
      test_fase4_migration.py                              # CREATE
      test_sqlalchemy_aprendizado_repository.py             # CREATE
      test_sqlalchemy_classificacao_repository.py           # MODIFY
      test_documentos_api.py                                # MODIFY
frontend/
  src/
    types/
      documento.ts                                         # MODIFY: OrigemClassificacao ganha IA, MANUAL
    api/
      client.ts                                             # MODIFY: api.documentos.corrigirClassificacao
    components/
      DocumentoList.tsx                                     # MODIFY: seletor de correção + rótulos de origem
    pages/
      EmpresasPage.tsx                                      # MODIFY: passa contas pro DocumentoList
```

---

### Task 1: Schema — enum `OrigemClassificacao` + `aprendizado` real + config Ollama

**Files:**
- Modify: `backend/app/domain/enums.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/infrastructure/db/models.py`
- Create: `backend/alembic/versions/0005_fase4_ia_aprendizado.py`
- Test: `backend/tests/integration/test_fase4_migration.py`

**Interfaces:**
- Produces: `OrigemClassificacao.IA`, `OrigemClassificacao.MANUAL` em `app.domain.enums`. `AprendizadoModel` (colunas reais) em `app.infrastructure.db.models`. `settings.ollama_host`, `settings.ollama_model`, `settings.ollama_timeout_segundos` em `app.core.config`.

- [ ] **Step 1: Adicionar os valores novos ao enum**

Em `backend/app/domain/enums.py`, alterar:
```python
class OrigemClassificacao(str, Enum):
    REGRA = "REGRA"
    FUZZY = "FUZZY"
```
para:
```python
class OrigemClassificacao(str, Enum):
    REGRA = "REGRA"
    FUZZY = "FUZZY"
    IA = "IA"
    MANUAL = "MANUAL"
```
Nota: `classificacoes.origem` já é uma coluna `String(20)` sem constraint de enum no banco — adicionar novos valores ao enum Python não exige migration nenhuma.

- [ ] **Step 2: Adicionar a configuração do Ollama**

Em `backend/app/core/config.py`, adicionar ao `Settings`:
```python
    # Ollama local (Fase 4 — classificação por IA). Assume que o servidor já está
    # rodando e o modelo já foi baixado (`ollama pull <modelo>`) manualmente.
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    ollama_timeout_segundos: int = 15
```

- [ ] **Step 3: Escrever o teste de migration (falhando)**

`backend/tests/integration/test_fase4_migration.py`:
```python
from sqlalchemy import create_engine, inspect
from alembic import command
from alembic.config import Config


def test_migration_cria_aprendizado_real(tmp_path):
    db_path = tmp_path / "test_fase4_migration.db"
    db_url = f"sqlite:///{db_path}"

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(db_url)
    inspector = inspect(engine)

    aprendizado_cols = {c["name"] for c in inspector.get_columns("aprendizado")}
    assert aprendizado_cols == {
        "id", "empresa_id", "documento_id", "conta_anterior_id", "origem_anterior",
        "conta_corrigida_id", "regra_id", "created_at",
    }
    aprendizado_indexes = {idx["name"] for idx in inspector.get_indexes("aprendizado")}
    assert "ix_aprendizado_empresa_id" in aprendizado_indexes

    # downgrade must be symmetric
    command.downgrade(alembic_cfg, "0004")
    inspector = inspect(engine)
    aprendizado_cols = {c["name"] for c in inspector.get_columns("aprendizado")}
    assert aprendizado_cols == {"id", "empresa_id", "created_at"}
```

- [ ] **Step 4: Rodar o teste para confirmar que falha**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/integration/test_fase4_migration.py -v`
Expected: FAIL — a migration "0005" ainda não existe.

- [ ] **Step 5: Criar a migration**

`backend/alembic/versions/0005_fase4_ia_aprendizado.py`:
```python
"""fase4 IA + aprendizado: tabela aprendizado real

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("aprendizado")
    op.create_table(
        "aprendizado",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("documento_id", sa.Integer, sa.ForeignKey("documentos.id"), nullable=False),
        sa.Column("conta_anterior_id", sa.Integer, sa.ForeignKey("contas.id"), nullable=True),
        sa.Column("origem_anterior", sa.String(20), nullable=True),
        sa.Column(
            "conta_corrigida_id", sa.Integer, sa.ForeignKey("contas.id"), nullable=False
        ),
        sa.Column("regra_id", sa.Integer, sa.ForeignKey("regras.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_aprendizado_empresa_id", "aprendizado", ["empresa_id"])


def downgrade() -> None:
    op.drop_index("ix_aprendizado_empresa_id", table_name="aprendizado")
    op.drop_table("aprendizado")
    op.create_table(
        "aprendizado",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
```

- [ ] **Step 6: Rodar o teste para confirmar que passa**

Run: `.venv/Scripts/python -m pytest tests/integration/test_fase4_migration.py -v`
Expected: PASS (1 passed)

- [ ] **Step 7: Adicionar o model SQLAlchemy**

Em `backend/app/infrastructure/db/models.py`, substituir o `AprendizadoModel` stub existente:
```python
class AprendizadoModel(Base):
    __tablename__ = "aprendizado"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
```
por:
```python
class AprendizadoModel(Base):
    __tablename__ = "aprendizado"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(
        ForeignKey("empresas.id"), nullable=False, index=True
    )
    documento_id: Mapped[int] = mapped_column(ForeignKey("documentos.id"), nullable=False)
    conta_anterior_id: Mapped[int | None] = mapped_column(
        ForeignKey("contas.id"), nullable=True
    )
    origem_anterior: Mapped[str | None] = mapped_column(String(20), nullable=True)
    conta_corrigida_id: Mapped[int] = mapped_column(
        ForeignKey("contas.id"), nullable=False
    )
    regra_id: Mapped[int | None] = mapped_column(ForeignKey("regras.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
```

- [ ] **Step 8: Rodar a suíte completa**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add backend/app/domain/enums.py backend/app/core/config.py backend/app/infrastructure/db/models.py backend/alembic/versions/0005_fase4_ia_aprendizado.py backend/tests/integration/test_fase4_migration.py
git commit -m "feat: add IA/MANUAL classification origins, real aprendizado table, ollama config"
```

---

### Task 2: Domain entity `Aprendizado`

**Files:**
- Modify: `backend/app/domain/entities.py`
- Test: `backend/tests/unit/test_aprendizado_domain.py`

**Interfaces:**
- Consumes: `OrigemClassificacao` (Task 1).
- Produces: `Aprendizado` dataclass em `app.domain.entities`.

- [ ] **Step 1: Escrever o teste (falhando)**

`backend/tests/unit/test_aprendizado_domain.py`:
```python
from app.domain.entities import Aprendizado
from app.domain.enums import OrigemClassificacao


def test_aprendizado_sem_classificacao_anterior():
    aprendizado = Aprendizado(
        id=None, empresa_id=1, documento_id=1, conta_anterior_id=None,
        origem_anterior=None, conta_corrigida_id=10,
    )
    assert aprendizado.conta_anterior_id is None
    assert aprendizado.regra_id is None


def test_aprendizado_com_classificacao_anterior_e_regra():
    aprendizado = Aprendizado(
        id=None, empresa_id=1, documento_id=1, conta_anterior_id=5,
        origem_anterior=OrigemClassificacao.FUZZY, conta_corrigida_id=10, regra_id=3,
    )
    assert aprendizado.conta_anterior_id == 5
    assert aprendizado.origem_anterior == OrigemClassificacao.FUZZY
    assert aprendizado.regra_id == 3
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_aprendizado_domain.py -v`
Expected: FAIL com `ImportError`.

- [ ] **Step 3: Adicionar a entidade**

Em `backend/app/domain/entities.py`, adicionar ao final do arquivo:
```python
@dataclass
class Aprendizado:
    id: int | None
    empresa_id: int
    documento_id: int
    conta_anterior_id: int | None
    origem_anterior: OrigemClassificacao | None
    conta_corrigida_id: int
    regra_id: int | None = None
    created_at: datetime | None = None
```

- [ ] **Step 4: Rodar o teste para confirmar que passa**

Run: `.venv/Scripts/python -m pytest tests/unit/test_aprendizado_domain.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Rodar a suíte completa**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/entities.py backend/tests/unit/test_aprendizado_domain.py
git commit -m "feat: add Aprendizado domain entity"
```

---

### Task 3: Repository interfaces + fakes — `AprendizadoRepository` + `ClassificacaoRepository.atualizar`

**Files:**
- Modify: `backend/app/application/repositories.py`
- Modify: `backend/tests/fakes.py`

**Interfaces:**
- Consumes: `Aprendizado` (Task 2).
- Produces: `AprendizadoRepository` (`criar`, `listar_por_empresa`) em `app.application.repositories`. `ClassificacaoRepository` ganha `atualizar`. `FakeAprendizadoRepository` em `tests.fakes`; `FakeClassificacaoRepository` ganha `atualizar`.

- [ ] **Step 1: Adicionar `atualizar` à interface `ClassificacaoRepository`**

Em `backend/app/application/repositories.py`, atualizar o import do topo de:
```python
from app.domain.entities import (
    Classificacao, Conta, Documento, Empresa, Extracao, LoteProcessamento, OcrResultado,
    PlanoContas, Regra,
)
```
para:
```python
from app.domain.entities import (
    Aprendizado, Classificacao, Conta, Documento, Empresa, Extracao, LoteProcessamento,
    OcrResultado, PlanoContas, Regra,
)
```

Alterar a classe `ClassificacaoRepository` de:
```python
class ClassificacaoRepository(ABC):
    @abstractmethod
    def criar(self, classificacao: Classificacao) -> Classificacao: ...

    @abstractmethod
    def obter_por_documento_id(self, documento_id: int) -> Classificacao | None: ...

    @abstractmethod
    def listar_por_empresa(self, empresa_id: int) -> list[Classificacao]: ...
```
para:
```python
class ClassificacaoRepository(ABC):
    @abstractmethod
    def criar(self, classificacao: Classificacao) -> Classificacao: ...

    @abstractmethod
    def obter_por_documento_id(self, documento_id: int) -> Classificacao | None: ...

    @abstractmethod
    def listar_por_empresa(self, empresa_id: int) -> list[Classificacao]: ...

    @abstractmethod
    def atualizar(self, classificacao: Classificacao) -> Classificacao: ...
```

Adicionar ao final do arquivo:
```python
class AprendizadoRepository(ABC):
    @abstractmethod
    def criar(self, aprendizado: Aprendizado) -> Aprendizado: ...

    @abstractmethod
    def listar_por_empresa(self, empresa_id: int) -> list[Aprendizado]: ...
```

- [ ] **Step 2: Adicionar `atualizar` ao `FakeClassificacaoRepository` e criar `FakeAprendizadoRepository`**

Em `backend/tests/fakes.py`, atualizar os imports do topo de:
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
para:
```python
from app.application.repositories import (
    AprendizadoRepository,
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
    Aprendizado, Classificacao, Conta, Documento, Empresa, Extracao, LoteProcessamento,
    OcrResultado, PlanoContas, Regra,
)
```

Adicionar `atualizar` ao `FakeClassificacaoRepository` existente:
```python
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

    def atualizar(self, classificacao: Classificacao) -> Classificacao:
        self._items[classificacao.id] = classificacao
        return classificacao
```

Adicionar ao final do arquivo:
```python
class FakeAprendizadoRepository(AprendizadoRepository):
    def __init__(self):
        self._items: dict[int, Aprendizado] = {}
        self._next_id = 1

    def criar(self, aprendizado: Aprendizado) -> Aprendizado:
        aprendizado.id = self._next_id
        self._items[self._next_id] = aprendizado
        self._next_id += 1
        return aprendizado

    def listar_por_empresa(self, empresa_id: int) -> list[Aprendizado]:
        return [a for a in self._items.values() if a.empresa_id == empresa_id]
```

- [ ] **Step 3: Verificar que os fakes satisfazem a interface**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -c "from tests.fakes import FakeAprendizadoRepository, FakeClassificacaoRepository; FakeAprendizadoRepository(); FakeClassificacaoRepository(); print('ok')"`
Expected: prints `ok`.

- [ ] **Step 4: Rodar a suíte completa**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/application/repositories.py backend/tests/fakes.py
git commit -m "feat: add AprendizadoRepository and ClassificacaoRepository.atualizar"
```

---

### Task 4: SQLAlchemy repositories — `AprendizadoRepository` + `ClassificacaoRepository.atualizar`

**Files:**
- Create: `backend/app/infrastructure/repositories/sqlalchemy_aprendizado_repository.py`
- Modify: `backend/app/infrastructure/repositories/sqlalchemy_classificacao_repository.py`
- Test: `backend/tests/integration/test_sqlalchemy_aprendizado_repository.py`
- Test: `backend/tests/integration/test_sqlalchemy_classificacao_repository.py` (modify)

**Interfaces:**
- Consumes: `AprendizadoRepository`, `ClassificacaoRepository` (Task 3), `AprendizadoModel` (Task 1), `Aprendizado`, `Classificacao` (Task 2), o fixture `db_session`.
- Produces: `SqlAlchemyAprendizadoRepository(session)`. `SqlAlchemyClassificacaoRepository.atualizar`.

- [ ] **Step 1: Escrever os testes falhando**

`backend/tests/integration/test_sqlalchemy_aprendizado_repository.py`:
```python
from app.domain.entities import Aprendizado, Conta, Documento, Empresa, PlanoContas
from app.domain.enums import NaturezaConta, OrigemClassificacao
from app.infrastructure.repositories.sqlalchemy_aprendizado_repository import (
    SqlAlchemyAprendizadoRepository,
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


def test_criar_aprendizado_sem_classificacao_anterior(db_session):
    empresa, conta, documento = _empresa_conta_documento(db_session)
    repo = SqlAlchemyAprendizadoRepository(db_session)

    criado = repo.criar(
        Aprendizado(
            id=None, empresa_id=empresa.id, documento_id=documento.id,
            conta_anterior_id=None, origem_anterior=None, conta_corrigida_id=conta.id,
        )
    )
    db_session.commit()

    encontrados = repo.listar_por_empresa(empresa.id)
    assert len(encontrados) == 1
    assert encontrados[0].id == criado.id
    assert encontrados[0].conta_anterior_id is None
    assert encontrados[0].origem_anterior is None


def test_criar_aprendizado_com_classificacao_anterior_e_regra(db_session):
    empresa, conta, documento = _empresa_conta_documento(db_session)
    repo = SqlAlchemyAprendizadoRepository(db_session)

    repo.criar(
        Aprendizado(
            id=None, empresa_id=empresa.id, documento_id=documento.id,
            conta_anterior_id=conta.id, origem_anterior=OrigemClassificacao.FUZZY,
            conta_corrigida_id=conta.id, regra_id=None,
        )
    )
    db_session.commit()

    encontrados = repo.listar_por_empresa(empresa.id)
    assert encontrados[0].origem_anterior == OrigemClassificacao.FUZZY
```

Estender `backend/tests/integration/test_sqlalchemy_classificacao_repository.py` com um teste novo (reusar o helper `_empresa_conta_documento` já existente nesse arquivo):
```python
def test_atualizar_classificacao(db_session):
    empresa, conta, documento = _empresa_conta_documento(db_session)
    repo = SqlAlchemyClassificacaoRepository(db_session)
    criada = repo.criar(
        Classificacao(
            id=None, empresa_id=empresa.id, documento_id=documento.id, conta_id=conta.id,
            origem=OrigemClassificacao.FUZZY, regra_id=None, score_similaridade=0.7,
        )
    )
    db_session.commit()

    criada.origem = OrigemClassificacao.MANUAL
    criada.score_similaridade = None
    repo.atualizar(criada)
    db_session.commit()

    atualizada = repo.obter_por_documento_id(documento.id)
    assert atualizada.origem == OrigemClassificacao.MANUAL
    assert atualizada.score_similaridade is None
```

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/integration/test_sqlalchemy_aprendizado_repository.py tests/integration/test_sqlalchemy_classificacao_repository.py -v`
Expected: FAIL — `SqlAlchemyAprendizadoRepository` não existe; `atualizar` do `SqlAlchemyClassificacaoRepository` não existe.

- [ ] **Step 3: Escrever `SqlAlchemyAprendizadoRepository`**

`backend/app/infrastructure/repositories/sqlalchemy_aprendizado_repository.py`:
```python
from sqlalchemy.orm import Session

from app.application.repositories import AprendizadoRepository
from app.domain.entities import Aprendizado
from app.domain.enums import OrigemClassificacao
from app.infrastructure.db.models import AprendizadoModel


def _to_entity(model: AprendizadoModel) -> Aprendizado:
    return Aprendizado(
        id=model.id,
        empresa_id=model.empresa_id,
        documento_id=model.documento_id,
        conta_anterior_id=model.conta_anterior_id,
        origem_anterior=(
            OrigemClassificacao(model.origem_anterior) if model.origem_anterior else None
        ),
        conta_corrigida_id=model.conta_corrigida_id,
        regra_id=model.regra_id,
        created_at=model.created_at,
    )


class SqlAlchemyAprendizadoRepository(AprendizadoRepository):
    def __init__(self, session: Session):
        self._session = session

    def criar(self, aprendizado: Aprendizado) -> Aprendizado:
        model = AprendizadoModel(
            empresa_id=aprendizado.empresa_id,
            documento_id=aprendizado.documento_id,
            conta_anterior_id=aprendizado.conta_anterior_id,
            origem_anterior=(
                aprendizado.origem_anterior.value if aprendizado.origem_anterior else None
            ),
            conta_corrigida_id=aprendizado.conta_corrigida_id,
            regra_id=aprendizado.regra_id,
        )
        self._session.add(model)
        self._session.flush()
        return _to_entity(model)

    def listar_por_empresa(self, empresa_id: int) -> list[Aprendizado]:
        models = (
            self._session.query(AprendizadoModel).filter_by(empresa_id=empresa_id).all()
        )
        return [_to_entity(m) for m in models]
```

- [ ] **Step 4: Adicionar `atualizar` ao `SqlAlchemyClassificacaoRepository`**

Em `backend/app/infrastructure/repositories/sqlalchemy_classificacao_repository.py`, adicionar ao final da classe `SqlAlchemyClassificacaoRepository`:
```python
    def atualizar(self, classificacao: Classificacao) -> Classificacao:
        model = self._session.get(ClassificacaoModel, classificacao.id)
        model.conta_id = classificacao.conta_id
        model.origem = classificacao.origem.value
        model.regra_id = classificacao.regra_id
        model.score_similaridade = classificacao.score_similaridade
        self._session.flush()
        return _to_entity(model)
```

- [ ] **Step 5: Rodar os testes para confirmar que passam**

Run: `.venv/Scripts/python -m pytest tests/integration/test_sqlalchemy_aprendizado_repository.py tests/integration/test_sqlalchemy_classificacao_repository.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: Rodar a suíte completa**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/infrastructure/repositories/sqlalchemy_aprendizado_repository.py backend/app/infrastructure/repositories/sqlalchemy_classificacao_repository.py backend/tests/integration/test_sqlalchemy_aprendizado_repository.py backend/tests/integration/test_sqlalchemy_classificacao_repository.py
git commit -m "feat: add SqlAlchemyAprendizadoRepository and ClassificacaoRepository.atualizar"
```

---

### Task 5: Classificador por IA (Ollama)

**Files:**
- Create: `backend/app/infrastructure/ia/__init__.py`
- Create: `backend/app/infrastructure/ia/ollama_classificador.py`
- Test: `backend/tests/unit/test_ollama_classificador.py`

**Interfaces:**
- Consumes: `Extracao`, `Conta` (`app.domain.entities`), `settings.ollama_host`/`ollama_model`/`ollama_timeout_segundos` (Task 1).
- Produces: `classificar_por_ia(extracao: Extracao, contas: list[Conta]) -> int | None` — NUNCA lança exceção; retorna `None` se a IA não deu uma resposta utilizável (indisponível, timeout, resposta fora das opções).

Esta é a função com o requisito de resiliência mais importante do plano — leia o Global
Constraints antes de implementar: qualquer falha na chamada ao Ollama deve virar `None`,
nunca uma exceção propagada.

- [ ] **Step 1: Escrever os testes falhando**

`backend/tests/unit/test_ollama_classificador.py`:
```python
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.domain.entities import Conta, Extracao
from app.domain.enums import NaturezaConta, TipoDocumento
from app.infrastructure.ia.ollama_classificador import classificar_por_ia


def _extracao(**overrides):
    base = dict(
        id=1, documento_id=1, pagador_nome="JOAO", pagador_documento="12345678900",
        recebedor_nome="ENERGISA", recebedor_documento="12345678000195",
        valor=Decimal("150.00"), data_pagamento=None, tipo_documento=TipoDocumento.PIX,
        banco_nome=None,
    )
    base.update(overrides)
    return Extracao(**base)


def _conta(id_, codigo, descricao="Conta Teste"):
    return Conta(
        id=id_, plano_conta_id=1, codigo=codigo, descricao=descricao,
        natureza=NaturezaConta.DESPESA, conta_analitica=True,
    )


def test_classifica_com_resposta_valida():
    contas = [_conta(1, "1"), _conta(2, "2")]
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "2"}
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.infrastructure.ia.ollama_classificador.httpx.post", return_value=mock_response
    ):
        assert classificar_por_ia(_extracao(), contas) == 2


def test_resposta_nenhuma_retorna_none():
    contas = [_conta(1, "1")]
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "NENHUMA"}
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.infrastructure.ia.ollama_classificador.httpx.post", return_value=mock_response
    ):
        assert classificar_por_ia(_extracao(), contas) is None


def test_resposta_com_codigo_inexistente_retorna_none():
    contas = [_conta(1, "1")]
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "99"}
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.infrastructure.ia.ollama_classificador.httpx.post", return_value=mock_response
    ):
        assert classificar_por_ia(_extracao(), contas) is None


def test_falha_de_conexao_retorna_none_sem_lancar():
    contas = [_conta(1, "1")]
    with patch(
        "app.infrastructure.ia.ollama_classificador.httpx.post",
        side_effect=Exception("conexão recusada"),
    ):
        assert classificar_por_ia(_extracao(), contas) is None


def test_sem_contas_disponiveis_retorna_none():
    assert classificar_por_ia(_extracao(), []) is None


def test_resposta_com_espacos_e_case_diferente_ainda_casa():
    contas = [_conta(1, "10")]
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "  10  \n"}
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.infrastructure.ia.ollama_classificador.httpx.post", return_value=mock_response
    ):
        assert classificar_por_ia(_extracao(), contas) == 1
```

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_ollama_classificador.py -v`
Expected: FAIL com `ModuleNotFoundError`.

- [ ] **Step 3: Escrever o classificador**

`backend/app/infrastructure/ia/__init__.py`: arquivo vazio.

`backend/app/infrastructure/ia/ollama_classificador.py`:
```python
import logging

import httpx

from app.core.config import settings
from app.domain.entities import Conta, Extracao

logger = logging.getLogger(__name__)


def _montar_prompt(extracao: Extracao, contas: list[Conta]) -> str:
    linhas_contas = "\n".join(f"{conta.codigo} — {conta.descricao}" for conta in contas)
    return (
        "Você é um assistente de classificação contábil. Dado um comprovante de "
        "pagamento e uma lista de contas, responda APENAS o código de uma das contas "
        "listadas que melhor representa a natureza deste pagamento, ou a palavra "
        "NENHUMA se nenhuma parecer adequada. Não escreva mais nada além do código "
        "ou da palavra NENHUMA.\n\n"
        f"Tipo de documento: {extracao.tipo_documento.value}\n"
        f"Pagador: {extracao.pagador_nome or 'não identificado'}\n"
        f"Recebedor: {extracao.recebedor_nome or 'não identificado'}\n"
        f"Valor: {extracao.valor if extracao.valor is not None else 'não identificado'}\n"
        f"Banco: {extracao.banco_nome or 'não identificado'}\n\n"
        "Contas disponíveis:\n"
        f"{linhas_contas}\n"
    )


def classificar_por_ia(extracao: Extracao, contas: list[Conta]) -> int | None:
    """Tenta classificar via IA local (Ollama). Nunca lança exceção — qualquer

    falha (servidor indisponível, timeout, resposta fora das opções oferecidas)
    vira `None`, para que a cadeia de classificação caia pro fuzzy sem quebrar
    o processamento do documento/lote.
    """
    if not contas:
        return None

    prompt = _montar_prompt(extracao, contas)
    try:
        resposta = httpx.post(
            f"{settings.ollama_host}/api/generate",
            json={"model": settings.ollama_model, "prompt": prompt, "stream": False},
            timeout=settings.ollama_timeout_segundos,
        )
        resposta.raise_for_status()
        texto = resposta.json().get("response", "").strip()
    except Exception:
        logger.warning("Falha ao consultar a IA (Ollama) para classificação.", exc_info=True)
        return None

    for conta in contas:
        if texto.upper() == conta.codigo.upper():
            return conta.id
    return None
```

- [ ] **Step 4: Rodar os testes para confirmar que passam**

Run: `.venv/Scripts/python -m pytest tests/unit/test_ollama_classificador.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Rodar a suíte completa**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/infrastructure/ia backend/tests/unit/test_ollama_classificador.py
git commit -m "feat: add Ollama-based classificador por IA (resilient, never raises)"
```

---

### Task 6: Ligar a IA ao pipeline de classificação

**Files:**
- Modify: `backend/app/infrastructure/classificacao/pipeline.py`
- Modify: `backend/tests/unit/test_classificacao_pipeline.py`

**Interfaces:**
- Consumes: `classificar_por_ia` (Task 5).
- Produces: `classificar_documento` agora recebe um parâmetro novo `contas_disponiveis: list[Conta]` (breaking change de assinatura — 3 argumentos posicionais além de `extracao` viram 4). Ordem final: REGRA → IA → FUZZY.

- [ ] **Step 1: Atualizar o teste (com o novo parâmetro)**

Substituir `backend/tests/unit/test_classificacao_pipeline.py` inteiro por:
```python
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from app.domain.entities import Conta, Extracao, Regra
from app.domain.enums import LadoRegra, NaturezaConta, OrigemClassificacao, TipoDocumento
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


def _conta(id_=1, codigo="1"):
    return Conta(
        id=id_, plano_conta_id=1, codigo=codigo, descricao="Conta",
        natureza=NaturezaConta.DESPESA, conta_analitica=True,
    )


def test_classifica_por_regra_quando_bate():
    regra = Regra(
        id=1, empresa_id=1, conta_id=10, lado_alvo=LadoRegra.RECEBEDOR,
        documento_fiscal="12345678000195", tipo_documento=None,
        valor_min=None, valor_max=None, palavra_chave_nome=None, ativo=True,
    )
    resultado = classificar_documento(_extracao(), [regra], [_conta()], [])
    assert resultado.origem == OrigemClassificacao.REGRA
    assert resultado.conta_id == 10
    assert resultado.regra_id == 1
    assert resultado.score_similaridade is None


def test_classifica_por_ia_quando_nenhuma_regra_bate_e_ia_responde():
    with patch(
        "app.infrastructure.classificacao.pipeline.classificar_por_ia", return_value=20
    ):
        resultado = classificar_documento(_extracao(), [], [_conta(20, "2")], [])
    assert resultado.origem == OrigemClassificacao.IA
    assert resultado.conta_id == 20
    assert resultado.regra_id is None
    assert resultado.score_similaridade is None


def test_cai_para_fuzzy_quando_nenhuma_regra_e_ia_nao_responde():
    historico = [("ENERGISA CEARA", 20, datetime(2026, 1, 1, tzinfo=timezone.utc))]
    with patch(
        "app.infrastructure.classificacao.pipeline.classificar_por_ia", return_value=None
    ):
        resultado = classificar_documento(_extracao(), [], [_conta()], historico)
    assert resultado.origem == OrigemClassificacao.FUZZY
    assert resultado.conta_id == 20
    assert resultado.regra_id is None
    assert resultado.score_similaridade is not None


def test_sem_regra_ia_e_historico_retorna_none():
    with patch(
        "app.infrastructure.classificacao.pipeline.classificar_por_ia", return_value=None
    ):
        assert classificar_documento(_extracao(), [], [_conta()], []) is None


def test_usa_pagador_quando_recebedor_ausente_no_fuzzy():
    historico = [("JOAO", 30, datetime(2026, 1, 1, tzinfo=timezone.utc))]
    with patch(
        "app.infrastructure.classificacao.pipeline.classificar_por_ia", return_value=None
    ):
        resultado = classificar_documento(
            _extracao(recebedor_nome=None), [], [_conta()], historico
        )
    assert resultado.conta_id == 30
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_classificacao_pipeline.py -v`
Expected: FAIL — `classificar_documento` ainda tem a assinatura antiga (3 argumentos).

- [ ] **Step 3: Atualizar o pipeline**

Substituir `backend/app/infrastructure/classificacao/pipeline.py` inteiro por:
```python
from dataclasses import dataclass
from datetime import datetime

from app.domain.entities import Conta, Extracao, Regra
from app.domain.enums import OrigemClassificacao
from app.infrastructure.classificacao.busca_fuzzy import buscar_conta_por_similaridade
from app.infrastructure.classificacao.motor_regras import encontrar_regra_mais_especifica
from app.infrastructure.ia.ollama_classificador import classificar_por_ia


@dataclass
class ResultadoClassificacao:
    conta_id: int
    origem: OrigemClassificacao
    regra_id: int | None
    score_similaridade: float | None


def classificar_documento(
    extracao: Extracao,
    regras: list[Regra],
    contas_disponiveis: list[Conta],
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

    conta_id_ia = classificar_por_ia(extracao, contas_disponiveis)
    if conta_id_ia is not None:
        return ResultadoClassificacao(
            conta_id=conta_id_ia,
            origem=OrigemClassificacao.IA,
            regra_id=None,
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
Expected: PASS (5 passed)

- [ ] **Step 5: Rodar a suíte completa**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all pass (esta mudança quebra a chamada no worker até a Task 7 — os testes de integração do lote vão falhar até lá; se isso acontecer, é esperado neste ponto do plano, confirme que a falha é especificamente por causa da assinatura de `classificar_documento` e não outra coisa, e prossiga pra Task 7 imediatamente).

- [ ] **Step 6: Commit**

```bash
git add backend/app/infrastructure/classificacao/pipeline.py backend/tests/unit/test_classificacao_pipeline.py
git commit -m "feat: wire IA classifier into REGRA -> IA -> FUZZY chain"
```

---

### Task 7: Ligar `contas_disponiveis` ao worker

**Files:**
- Modify: `backend/app/infrastructure/workers/lote_worker.py`

**Interfaces:**
- Consumes: `classificar_documento` (nova assinatura, Task 6), `ContaRepository`/`SqlAlchemyContaRepository`, `PlanoContasRepository`/`SqlAlchemyPlanoContasRepository` (já existentes).
- Produces: nenhuma interface pública nova — `processar_lote_em_background` agora carrega as contas analíticas da empresa uma vez por lote e passa pro pipeline de classificação.

**Current content relevante de `backend/app/infrastructure/workers/lote_worker.py`** (leia o arquivo você mesmo para confirmar que ainda bate com isto antes de editar — foi reestruturado na Fase 3 pra processar resultados em ordem de submissão, com `regras`/`historico_fuzzy` carregados uma vez antes do laço principal):

```python
            regras = regra_repo.listar_por_empresa(empresa_id_lote) if empresa_id_lote is not None else []
            historico_fuzzy: list[tuple[str, int, "datetime"]] = []
            if empresa_id_lote is not None:
                for classificacao_existente in classificacao_repo.listar_por_empresa(empresa_id_lote):
                    ...
```//

- [ ] **Step 1: Adicionar os repositórios necessários**

Adicionar aos imports da função (junto ao bloco que já importa `SqlAlchemyRegraRepository`/`SqlAlchemyClassificacaoRepository`):
```python
    from app.infrastructure.repositories.sqlalchemy_conta_repository import (
        SqlAlchemyContaRepository,
    )
    from app.infrastructure.repositories.sqlalchemy_plano_contas_repository import (
        SqlAlchemyPlanoContasRepository,
    )
```

Adicionar à construção de repositórios no topo da função (junto a `regra_repo`/`classificacao_repo`):
```python
        conta_repo = SqlAlchemyContaRepository(session)
        plano_repo = SqlAlchemyPlanoContasRepository(session)
```

- [ ] **Step 2: Adicionar o helper de contas analíticas**

Adicionar esta função no módulo, próxima às outras funções auxiliares no topo do arquivo (ex: logo antes de `_marcar_lote_como_falhou`):
```python
def _listar_contas_analiticas(conta_repo, plano_repo, empresa_id: int) -> list:
    """Contas analíticas de todos os planos de contas da empresa — usadas como

    as opções oferecidas à IA (Fase 4) na classificação por fallback.
    """
    contas = []
    for plano in plano_repo.listar_por_empresa(empresa_id):
        contas.extend(c for c in conta_repo.listar_por_plano(plano.id) if c.conta_analitica)
    return contas
```

- [ ] **Step 3: Carregar `contas_disponiveis` uma vez por lote e passar ao pipeline**

Onde `regras`/`historico_fuzzy` são carregados uma vez antes do laço de resultados (bloco já reestruturado na Fase 3), adicionar:
```python
            contas_disponiveis = (
                _listar_contas_analiticas(conta_repo, plano_repo, empresa_id_lote)
                if empresa_id_lote is not None
                else []
            )
```
(pode ficar logo depois da linha `regras = regra_repo.listar_por_empresa(...)`).

Alterar a chamada existente:
```python
                    resultado_classificacao = classificar_documento(
                        extracao_criada, regras, historico_fuzzy
                    )
```
para:
```python
                    resultado_classificacao = classificar_documento(
                        extracao_criada, regras, contas_disponiveis, historico_fuzzy
                    )
```

- [ ] **Step 4: Rodar a suíte de testes de lote**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/integration/test_lotes_api.py -v`
Expected: all pass (os testes que ficaram quebrados na Task 6 por causa da assinatura devem voltar a passar agora).

- [ ] **Step 5: Rodar a suíte completa**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/infrastructure/workers/lote_worker.py
git commit -m "feat: load contas analiticas once per lote for IA classification"
```

---

### Task 8: Caso de uso de correção manual + aprendizado

**Files:**
- Create: `backend/app/application/use_cases/classificacao_use_cases.py`
- Test: `backend/tests/unit/test_classificacao_use_cases.py`

**Interfaces:**
- Consumes: `DocumentoRepository`, `ExtracaoRepository`, `ClassificacaoRepository`, `RegraRepository`, `AprendizadoRepository`, `ContaRepository`, `PlanoContasRepository` (já existentes/Task 3), `Aprendizado`, `Classificacao`, `Regra` (Task 2/existentes), `LadoRegra`, `OrigemClassificacao`.
- Produces: `CorrigirClassificacaoUseCase.executar(documento_id: int, conta_id: int) -> Classificacao`.

- [ ] **Step 1: Escrever os testes falhando**

`backend/tests/unit/test_classificacao_use_cases.py`:
```python
import pytest

from app.application.use_cases.classificacao_use_cases import CorrigirClassificacaoUseCase
from app.core.exceptions import (
    ContaNaoAnalitica,
    ContaNaoEncontrada,
    ContaNaoPertenceAEmpresa,
    DocumentoNaoEncontrado,
)
from app.domain.entities import (
    Classificacao, Conta, Documento, Empresa, Extracao, PlanoContas, Regra,
)
from app.domain.enums import LadoRegra, NaturezaConta, OrigemClassificacao, TipoDocumento
from tests.fakes import (
    FakeAprendizadoRepository,
    FakeClassificacaoRepository,
    FakeContaRepository,
    FakeDocumentoRepository,
    FakeExtracaoRepository,
    FakePlanoContasRepository,
    FakeRegraRepository,
)


def _ambiente(conta_analitica=True):
    documento_repo = FakeDocumentoRepository()
    extracao_repo = FakeExtracaoRepository()
    classificacao_repo = FakeClassificacaoRepository()
    regra_repo = FakeRegraRepository()
    aprendizado_repo = FakeAprendizadoRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()

    documento = documento_repo.criar(
        Documento(
            id=None, empresa_id=1, nome_arquivo="a.pdf", nome_exibicao="a.pdf",
            caminho_arquivo="x/a.pdf", extensao=".pdf", tamanho_bytes=10,
        )
    )
    plano = plano_repo.criar(PlanoContas(id=None, empresa_id=1, nome="Plano"))
    conta = conta_repo.criar(
        Conta(
            id=None, plano_conta_id=plano.id, codigo="1", descricao="Energia",
            natureza=NaturezaConta.DESPESA, conta_analitica=conta_analitica,
        )
    )
    return {
        "documento_repo": documento_repo, "extracao_repo": extracao_repo,
        "classificacao_repo": classificacao_repo, "regra_repo": regra_repo,
        "aprendizado_repo": aprendizado_repo, "conta_repo": conta_repo,
        "plano_repo": plano_repo, "documento": documento, "conta": conta,
    }


def _use_case(ambiente):
    return CorrigirClassificacaoUseCase(
        ambiente["documento_repo"], ambiente["extracao_repo"], ambiente["classificacao_repo"],
        ambiente["regra_repo"], ambiente["aprendizado_repo"], ambiente["conta_repo"],
        ambiente["plano_repo"],
    )


def test_corrigir_cria_regra_nova_pelo_recebedor():
    ambiente = _ambiente()
    ambiente["extracao_repo"].criar(
        Extracao(
            id=None, documento_id=ambiente["documento"].id, pagador_nome=None,
            pagador_documento=None, recebedor_nome="ENERGISA",
            recebedor_documento="12345678000195", valor=None, data_pagamento=None,
            tipo_documento=TipoDocumento.OUTRO, banco_nome=None,
        )
    )

    classificacao = _use_case(ambiente).executar(ambiente["documento"].id, ambiente["conta"].id)

    assert classificacao.origem == OrigemClassificacao.MANUAL
    assert classificacao.conta_id == ambiente["conta"].id
    regras = ambiente["regra_repo"].listar_por_empresa(1)
    assert len(regras) == 1
    assert regras[0].documento_fiscal == "12345678000195"
    assert regras[0].lado_alvo == LadoRegra.RECEBEDOR
    assert regras[0].conta_id == ambiente["conta"].id


def test_corrigir_usa_pagador_quando_recebedor_ausente():
    ambiente = _ambiente()
    ambiente["extracao_repo"].criar(
        Extracao(
            id=None, documento_id=ambiente["documento"].id, pagador_nome="JOAO",
            pagador_documento="12345678900", recebedor_nome=None, recebedor_documento=None,
            valor=None, data_pagamento=None, tipo_documento=TipoDocumento.OUTRO, banco_nome=None,
        )
    )

    _use_case(ambiente).executar(ambiente["documento"].id, ambiente["conta"].id)

    regras = ambiente["regra_repo"].listar_por_empresa(1)
    assert regras[0].documento_fiscal == "12345678900"
    assert regras[0].lado_alvo == LadoRegra.PAGADOR


def test_corrigir_atualiza_regra_existente_em_vez_de_duplicar():
    ambiente = _ambiente()
    outra_conta = ambiente["conta_repo"].criar(
        Conta(
            id=None, plano_conta_id=1, codigo="2", descricao="Outra",
            natureza=NaturezaConta.DESPESA, conta_analitica=True,
        )
    )
    regra_antiga = ambiente["regra_repo"].criar(
        Regra(
            id=None, empresa_id=1, conta_id=outra_conta.id, lado_alvo=LadoRegra.RECEBEDOR,
            documento_fiscal="12345678000195", tipo_documento=None, valor_min=None,
            valor_max=None, palavra_chave_nome=None, ativo=True,
        )
    )
    ambiente["extracao_repo"].criar(
        Extracao(
            id=None, documento_id=ambiente["documento"].id, pagador_nome=None,
            pagador_documento=None, recebedor_nome="ENERGISA",
            recebedor_documento="12345678000195", valor=None, data_pagamento=None,
            tipo_documento=TipoDocumento.OUTRO, banco_nome=None,
        )
    )

    _use_case(ambiente).executar(ambiente["documento"].id, ambiente["conta"].id)

    regras = ambiente["regra_repo"].listar_por_empresa(1)
    assert len(regras) == 1
    assert regras[0].id == regra_antiga.id
    assert regras[0].conta_id == ambiente["conta"].id


def test_corrigir_sem_documento_fiscal_nao_cria_regra():
    ambiente = _ambiente()
    ambiente["extracao_repo"].criar(
        Extracao(
            id=None, documento_id=ambiente["documento"].id, pagador_nome=None,
            pagador_documento=None, recebedor_nome=None, recebedor_documento=None,
            valor=None, data_pagamento=None, tipo_documento=TipoDocumento.OUTRO, banco_nome=None,
        )
    )

    classificacao = _use_case(ambiente).executar(ambiente["documento"].id, ambiente["conta"].id)

    assert classificacao.regra_id is None
    assert ambiente["regra_repo"].listar_por_empresa(1) == []


def test_corrigir_documento_ja_classificado_atualiza_e_registra_aprendizado():
    ambiente = _ambiente()
    outra_conta = ambiente["conta_repo"].criar(
        Conta(
            id=None, plano_conta_id=1, codigo="2", descricao="Outra",
            natureza=NaturezaConta.DESPESA, conta_analitica=True,
        )
    )
    classificacao_existente = ambiente["classificacao_repo"].criar(
        Classificacao(
            id=None, empresa_id=1, documento_id=ambiente["documento"].id,
            conta_id=outra_conta.id, origem=OrigemClassificacao.FUZZY,
            score_similaridade=0.6,
        )
    )
    ambiente["extracao_repo"].criar(
        Extracao(
            id=None, documento_id=ambiente["documento"].id, pagador_nome=None,
            pagador_documento=None, recebedor_nome=None, recebedor_documento=None,
            valor=None, data_pagamento=None, tipo_documento=TipoDocumento.OUTRO, banco_nome=None,
        )
    )

    classificacao = _use_case(ambiente).executar(ambiente["documento"].id, ambiente["conta"].id)

    assert classificacao.id == classificacao_existente.id
    assert classificacao.origem == OrigemClassificacao.MANUAL
    assert classificacao.score_similaridade is None

    aprendizados = ambiente["aprendizado_repo"].listar_por_empresa(1)
    assert len(aprendizados) == 1
    assert aprendizados[0].conta_anterior_id == outra_conta.id
    assert aprendizados[0].origem_anterior == OrigemClassificacao.FUZZY
    assert aprendizados[0].conta_corrigida_id == ambiente["conta"].id


def test_corrigir_documento_sem_classificacao_anterior_cria():
    ambiente = _ambiente()
    ambiente["extracao_repo"].criar(
        Extracao(
            id=None, documento_id=ambiente["documento"].id, pagador_nome=None,
            pagador_documento=None, recebedor_nome=None, recebedor_documento=None,
            valor=None, data_pagamento=None, tipo_documento=TipoDocumento.OUTRO, banco_nome=None,
        )
    )

    classificacao = _use_case(ambiente).executar(ambiente["documento"].id, ambiente["conta"].id)

    assert classificacao.id is not None
    aprendizados = ambiente["aprendizado_repo"].listar_por_empresa(1)
    assert aprendizados[0].conta_anterior_id is None
    assert aprendizados[0].origem_anterior is None


def test_corrigir_documento_inexistente_falha():
    ambiente = _ambiente()
    with pytest.raises(DocumentoNaoEncontrado):
        _use_case(ambiente).executar(999, ambiente["conta"].id)


def test_corrigir_com_conta_inexistente_falha():
    ambiente = _ambiente()
    with pytest.raises(ContaNaoEncontrada):
        _use_case(ambiente).executar(ambiente["documento"].id, 999)


def test_corrigir_com_conta_sintetica_falha():
    ambiente = _ambiente(conta_analitica=False)
    with pytest.raises(ContaNaoAnalitica):
        _use_case(ambiente).executar(ambiente["documento"].id, ambiente["conta"].id)
```

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/unit/test_classificacao_use_cases.py -v`
Expected: FAIL com `ModuleNotFoundError`.

- [ ] **Step 3: Escrever o use case**

`backend/app/application/use_cases/classificacao_use_cases.py`:
```python
from app.application.repositories import (
    AprendizadoRepository,
    ClassificacaoRepository,
    ContaRepository,
    DocumentoRepository,
    ExtracaoRepository,
    PlanoContasRepository,
    RegraRepository,
)
from app.core.exceptions import (
    ContaNaoAnalitica,
    ContaNaoEncontrada,
    ContaNaoPertenceAEmpresa,
    DocumentoNaoEncontrado,
)
from app.domain.entities import Aprendizado, Classificacao, Regra
from app.domain.enums import LadoRegra, OrigemClassificacao


def _validar_conta(conta_repo, plano_repo, conta_id: int, empresa_id: int) -> None:
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


class CorrigirClassificacaoUseCase:
    def __init__(
        self,
        documento_repo: DocumentoRepository,
        extracao_repo: ExtracaoRepository,
        classificacao_repo: ClassificacaoRepository,
        regra_repo: RegraRepository,
        aprendizado_repo: AprendizadoRepository,
        conta_repo: ContaRepository,
        plano_repo: PlanoContasRepository,
    ):
        self._documento_repo = documento_repo
        self._extracao_repo = extracao_repo
        self._classificacao_repo = classificacao_repo
        self._regra_repo = regra_repo
        self._aprendizado_repo = aprendizado_repo
        self._conta_repo = conta_repo
        self._plano_repo = plano_repo

    def executar(self, documento_id: int, conta_id: int) -> Classificacao:
        documento = self._documento_repo.obter_por_id(documento_id)
        if documento is None:
            raise DocumentoNaoEncontrado(documento_id)
        _validar_conta(self._conta_repo, self._plano_repo, conta_id, documento.empresa_id)

        classificacao_existente = self._classificacao_repo.obter_por_documento_id(documento_id)
        conta_anterior_id = classificacao_existente.conta_id if classificacao_existente else None
        origem_anterior = classificacao_existente.origem if classificacao_existente else None

        documento_fiscal, lado_alvo = self._documento_fiscal_do_recebedor_ou_pagador(
            documento_id
        )

        regra_id = None
        if documento_fiscal is not None:
            regra_id = self._criar_ou_atualizar_regra(
                documento.empresa_id, conta_id, documento_fiscal, lado_alvo
            )

        if classificacao_existente is not None:
            classificacao_existente.conta_id = conta_id
            classificacao_existente.origem = OrigemClassificacao.MANUAL
            classificacao_existente.regra_id = regra_id
            classificacao_existente.score_similaridade = None
            classificacao_final = self._classificacao_repo.atualizar(classificacao_existente)
        else:
            classificacao_final = self._classificacao_repo.criar(
                Classificacao(
                    id=None, empresa_id=documento.empresa_id, documento_id=documento_id,
                    conta_id=conta_id, origem=OrigemClassificacao.MANUAL, regra_id=regra_id,
                    score_similaridade=None,
                )
            )

        self._aprendizado_repo.criar(
            Aprendizado(
                id=None, empresa_id=documento.empresa_id, documento_id=documento_id,
                conta_anterior_id=conta_anterior_id, origem_anterior=origem_anterior,
                conta_corrigida_id=conta_id, regra_id=regra_id,
            )
        )
        return classificacao_final

    def _documento_fiscal_do_recebedor_ou_pagador(
        self, documento_id: int
    ) -> tuple[str | None, LadoRegra | None]:
        extracao = self._extracao_repo.obter_por_documento_id(documento_id)
        if extracao is None:
            return None, None
        if extracao.recebedor_documento is not None:
            return extracao.recebedor_documento, LadoRegra.RECEBEDOR
        if extracao.pagador_documento is not None:
            return extracao.pagador_documento, LadoRegra.PAGADOR
        return None, None

    def _criar_ou_atualizar_regra(
        self, empresa_id: int, conta_id: int, documento_fiscal: str, lado_alvo: LadoRegra
    ) -> int:
        regra_existente = next(
            (
                r for r in self._regra_repo.listar_por_empresa(empresa_id)
                if r.documento_fiscal == documento_fiscal and r.lado_alvo == lado_alvo
            ),
            None,
        )
        if regra_existente is not None:
            regra_existente.conta_id = conta_id
            regra_atualizada = self._regra_repo.atualizar(regra_existente)
            return regra_atualizada.id

        nova_regra = self._regra_repo.criar(
            Regra(
                id=None, empresa_id=empresa_id, conta_id=conta_id, lado_alvo=lado_alvo,
                documento_fiscal=documento_fiscal, tipo_documento=None, valor_min=None,
                valor_max=None, palavra_chave_nome=None, ativo=True,
            )
        )
        return nova_regra.id
```

- [ ] **Step 4: Rodar os testes para confirmar que passam**

Run: `.venv/Scripts/python -m pytest tests/unit/test_classificacao_use_cases.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Rodar a suíte completa**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/application/use_cases/classificacao_use_cases.py backend/tests/unit/test_classificacao_use_cases.py
git commit -m "feat: add CorrigirClassificacaoUseCase (correction + rule learning)"
```

---

### Task 9: API de correção manual

**Files:**
- Modify: `backend/app/api/schemas/documento_schemas.py`
- Modify: `backend/app/api/routers/documentos_router.py`
- Test: `backend/tests/integration/test_documentos_api.py`

**Interfaces:**
- Consumes: `CorrigirClassificacaoUseCase` (Task 8), `SqlAlchemyAprendizadoRepository` (Task 4), `SqlAlchemyRegraRepository`, `SqlAlchemyPlanoContasRepository` (já existentes).
- Produces: `CorrigirClassificacaoIn` schema. `PATCH /documentos/{documento_id}/classificacao`.

- [ ] **Step 1: Adicionar o schema de entrada**

Em `backend/app/api/schemas/documento_schemas.py`, adicionar ao final do arquivo:
```python
class CorrigirClassificacaoIn(BaseModel):
    conta_id: int
```

- [ ] **Step 2: Escrever o teste falhando**

Adicionar a `backend/tests/integration/test_documentos_api.py` (reusar os fixtures `client`/`empresa_id` já existentes):
```python
def test_corrigir_classificacao_cria_regra_e_atualiza_documento(client, empresa_id):
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
    documento_id = client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("a.pdf", b"conteudo", "application/pdf")},
    ).json()[0]["documento"]["id"]

    resposta = client.patch(
        f"/documentos/{documento_id}/classificacao", json={"conta_id": conta_id}
    )

    assert resposta.status_code == 200
    body = resposta.json()
    assert body["conta_id"] == conta_id
    assert body["origem"] == "MANUAL"

    resultado = client.get(f"/documentos/{documento_id}/resultado").json()
    assert resultado["classificacao"]["origem"] == "MANUAL"
    assert resultado["classificacao"]["conta_id"] == conta_id


def test_corrigir_classificacao_documento_inexistente_retorna_404(client, empresa_id):
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

    resposta = client.patch("/documentos/999/classificacao", json={"conta_id": conta_id})
    assert resposta.status_code == 404
```

- [ ] **Step 3: Rodar o teste para confirmar que falha**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest tests/integration/test_documentos_api.py -v -k corrigir`
Expected: FAIL — rota `PATCH /documentos/{id}/classificacao` não existe ainda.

- [ ] **Step 4: Adicionar a rota**

Em `backend/app/api/routers/documentos_router.py`, atualizar o import de:
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
para:
```python
from app.api.schemas.documento_schemas import (
    ClassificacaoOut,
    CorrigirClassificacaoIn,
    DocumentoOut,
    DocumentoResultadoOut,
    ExtracaoOut,
    OcrResultadoOut,
    UploadItemOut,
)
```
Adicionar aos imports:
```python
from app.application.use_cases.classificacao_use_cases import CorrigirClassificacaoUseCase
from app.core.exceptions import ContaNaoAnalitica, ContaNaoEncontrada, ContaNaoPertenceAEmpresa
from app.infrastructure.repositories.sqlalchemy_aprendizado_repository import (
    SqlAlchemyAprendizadoRepository,
)
from app.infrastructure.repositories.sqlalchemy_plano_contas_repository import (
    SqlAlchemyPlanoContasRepository,
)
from app.infrastructure.repositories.sqlalchemy_regra_repository import (
    SqlAlchemyRegraRepository,
)
```
(note: `ContaNaoEncontrada` já pode estar importado de `app.core.exceptions` na linha existente — não duplique, apenas estenda o import já presente junto com `DocumentoNaoEncontrado`/`EmpresaNaoEncontrada`.)

Adicionar ao final do arquivo:
```python
@router.patch("/documentos/{documento_id}/classificacao", response_model=ClassificacaoOut)
def corrigir_classificacao(
    documento_id: int, payload: CorrigirClassificacaoIn, db: Session = Depends(get_db)
):
    documento_repo = SqlAlchemyDocumentoRepository(db)
    extracao_repo = SqlAlchemyExtracaoRepository(db)
    classificacao_repo = SqlAlchemyClassificacaoRepository(db)
    regra_repo = SqlAlchemyRegraRepository(db)
    aprendizado_repo = SqlAlchemyAprendizadoRepository(db)
    conta_repo = SqlAlchemyContaRepository(db)
    plano_repo = SqlAlchemyPlanoContasRepository(db)
    try:
        classificacao = CorrigirClassificacaoUseCase(
            documento_repo, extracao_repo, classificacao_repo, regra_repo,
            aprendizado_repo, conta_repo, plano_repo,
        ).executar(documento_id, payload.conta_id)
    except DocumentoNaoEncontrado as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ContaNaoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ContaNaoPertenceAEmpresa, ContaNaoAnalitica) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    conta = conta_repo.obter_por_id(classificacao.conta_id)
    return ClassificacaoOut.from_classificacao(classificacao, conta)
```

- [ ] **Step 5: Rodar o teste para confirmar que passa**

Run: `.venv/Scripts/python -m pytest tests/integration/test_documentos_api.py -v -k corrigir`
Expected: PASS (2 passed)

- [ ] **Step 6: Rodar a suíte completa**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/schemas/documento_schemas.py backend/app/api/routers/documentos_router.py backend/tests/integration/test_documentos_api.py
git commit -m "feat: add PATCH /documentos/{id}/classificacao correction endpoint"
```

---

### Task 10: Frontend — tipos + cliente de API

**Files:**
- Modify: `frontend/src/types/documento.ts`
- Modify: `frontend/src/api/client.ts`

**Interfaces:**
- Produces: `OrigemClassificacao` ganha `"IA"`, `"MANUAL"`. `api.documentos.corrigirClassificacao`.

- [ ] **Step 1: Atualizar o tipo**

Em `frontend/src/types/documento.ts`, alterar:
```ts
export type OrigemClassificacao = "REGRA" | "FUZZY";
```
para:
```ts
export type OrigemClassificacao = "REGRA" | "FUZZY" | "IA" | "MANUAL";
```

- [ ] **Step 2: Adicionar o método ao cliente de API**

Em `frontend/src/api/client.ts`, dentro do objeto `documentos`, adicionar junto a `resultado`:
```ts
    corrigirClassificacao: (documentoId: number, contaId: number) =>
      request<Classificacao>(`/documentos/${documentoId}/classificacao`, {
        method: "PATCH",
        body: JSON.stringify({ conta_id: contaId }),
      }),
```
Atualizar o import do topo de:
```ts
import type { Documento, DocumentoResultado, Lote, UploadItemResultado } from "../types/documento";
```
para:
```ts
import type {
  Classificacao, Documento, DocumentoResultado, Lote, UploadItemResultado,
} from "../types/documento";
```

- [ ] **Step 3: Verificar tipos**

Run: `cd "D:/DEV/Teste Lançamentos/frontend" && npx tsc --noEmit`
Expected: sucesso.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/documento.ts frontend/src/api/client.ts
git commit -m "feat: add IA/MANUAL classification origins and correction API client method"
```

---

### Task 11: Frontend — correção manual no painel de resultado

**Files:**
- Modify: `frontend/src/components/DocumentoList.tsx`
- Modify: `frontend/src/pages/EmpresasPage.tsx`

**Interfaces:**
- Consumes: `api.documentos.corrigirClassificacao` (Task 10), `Conta` (`frontend/src/types/planoContas.ts`, já existe).
- Produces: `DocumentoList` ganha uma prop nova `contas: Conta[]` e uma ação de correção.

- [ ] **Step 1: Atualizar o rótulo de origem e adicionar a correção**

Em `frontend/src/components/DocumentoList.tsx`, atualizar o import do topo de:
```tsx
import { useState } from "react";
import { api } from "../api/client";
import type { Documento, DocumentoResultado } from "../types/documento";
```
para:
```tsx
import { useState } from "react";
import { api } from "../api/client";
import type { Documento, DocumentoResultado, OrigemClassificacao } from "../types/documento";
import type { Conta } from "../types/planoContas";
```

Adicionar esta função auxiliar próxima a `corStatus`:
```tsx
function rotuloOrigem(origem: OrigemClassificacao): string {
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
```

Alterar a assinatura do componente de:
```tsx
export function DocumentoList({ documentos }: { documentos: Documento[] }) {
```
para:
```tsx
export function DocumentoList({
  documentos,
  contas,
}: {
  documentos: Documento[];
  contas: Conta[];
}) {
```

Adicionar, junto ao `useState` de `resultadoAberto`, um estado pro seletor de correção:
```tsx
  const [contaCorrecaoId, setContaCorrecaoId] = useState<number | "">("");
```

Adicionar esta função, próxima a `verResultado`:
```tsx
  async function corrigirClassificacao() {
    if (resultadoAberto === null || contaCorrecaoId === "") return;
    const classificacao = await api.documentos.corrigirClassificacao(
      resultadoAberto.documento.id,
      contaCorrecaoId,
    );
    setResultadoAberto({ ...resultadoAberto, classificacao });
    setContaCorrecaoId("");
  }
```

Substituir o bloco de exibição da classificação de:
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
por:
```tsx
          <div className="mb-3 rounded border border-slate-200 bg-white p-2">
            <span className="font-semibold">Classificação: </span>
            {resultadoAberto.classificacao ? (
              <span>
                {resultadoAberto.classificacao.conta_codigo} —{" "}
                {resultadoAberto.classificacao.conta_descricao} (
                {rotuloOrigem(resultadoAberto.classificacao.origem)}
                {resultadoAberto.classificacao.score_similaridade !== null &&
                  ` — ${Math.round(resultadoAberto.classificacao.score_similaridade * 100)}%`}
                )
              </span>
            ) : (
              <span>SEM CLASSIFICAÇÃO</span>
            )}
            <div className="mt-2 flex items-center gap-2">
              <select
                className="rounded border border-slate-300 px-2 py-1 text-xs"
                value={contaCorrecaoId}
                onChange={(e) =>
                  setContaCorrecaoId(e.target.value ? Number(e.target.value) : "")
                }
              >
                <option value="">Corrigir para...</option>
                {contas.map((conta) => (
                  <option key={conta.id} value={conta.id}>
                    {conta.codigo} — {conta.descricao}
                  </option>
                ))}
              </select>
              <button
                onClick={corrigirClassificacao}
                disabled={contaCorrecaoId === ""}
                className="rounded bg-slate-800 px-2 py-1 text-xs text-white disabled:opacity-50"
              >
                Corrigir
              </button>
            </div>
          </div>
```

- [ ] **Step 2: Passar `contas` de `EmpresasPage`**

Em `frontend/src/pages/EmpresasPage.tsx`, alterar:
```tsx
          <DocumentoList documentos={documentos} />
```
para:
```tsx
          <DocumentoList documentos={documentos} contas={contas} />
```
(reusa o mesmo estado `contas` já carregado pra seção de Regras — mesma limitação já aceita na Fase 3: só populado quando um plano de contas está selecionado.)

- [ ] **Step 3: Verificar tipos e build**

Run: `cd "D:/DEV/Teste Lançamentos/frontend" && npx tsc --noEmit && npm run build`
Expected: ambos sucesso.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/DocumentoList.tsx frontend/src/pages/EmpresasPage.tsx
git commit -m "feat: add manual classification correction UI to results panel"
```

---

### Task 12: Verificação manual end-to-end (com Ollama real)

**Files:** nenhum arquivo novo — apenas verificação.

- [ ] **Step 1: Confirmar que o Ollama está rodando e o modelo disponível**

Run: `ollama list`
Expected: lista incluindo `llama3.2` (já confirmado disponível nesta máquina antes deste plano ser escrito).

- [ ] **Step 2: Rodar a suíte completa do backend uma última vez**

Run: `cd "D:/DEV/Teste Lançamentos/backend" && .venv/Scripts/python -m pytest -v`
Expected: all pass. Esta é a Fase 4 completa, backend + frontend.

- [ ] **Step 3: Verificação manual no navegador (feita pelo controller com ferramentas de navegador)**

Com o backend rodando (`uvicorn app.main:app --reload` a partir de `backend/`, depois de `alembic upgrade head`), o frontend rodando (`npm run dev` a partir de `frontend/`), e o Ollama já rodando (confirmado no Step 1):

1. Abrir a aplicação, selecionar/criar uma empresa, criar um plano de contas com pelo menos
   2 contas analíticas com descrições claramente diferentes (ex: "Energia Elétrica" e
   "Serviços de Internet").
2. Fazer upload de um PDF sintético (script curto com PyMuPDF, mesmo processo das fases
   anteriores) com um fornecedor NOVO — sem nenhuma regra cadastrada pra ele e sem
   nenhuma classificação histórica na empresa — mas com texto que deixe claro pra qual
   das duas contas o documento deveria ir (ex: menção a "energia"/"conta de luz" no
   texto, mesmo que o extrator não capture isso como campo estruturado — a IA lê o texto
   completo do prompt, que inclui os nomes de pagador/recebedor e o contexto).
3. Processar o lote, esperar `CONCLUIDO`.
4. Abrir o resultado do documento e confirmar que a classificação aparece com
   `(sugestão por IA)` — prova que a chamada real ao Ollama funcionou e escolheu uma
   conta válida (não caiu pro fuzzy, já que não há histórico nenhum ainda).
5. Usar o seletor de correção pra mudar a classificação pra OUTRA conta. Confirmar que a
   UI atualiza pra mostrar `(corrigida manualmente)`.
6. Cadastrar/consultar as regras da empresa (tela já existente da Fase 3) e confirmar que
   uma regra nova foi criada automaticamente pelo CNPJ/CPF do documento, apontando pra a
   conta que você escolheu na correção.
7. Fazer upload de um SEGUNDO documento do MESMO fornecedor (mesmo CNPJ/CPF) e processar.
   Confirmar que a classificação agora vem `(por regra)` — prova que o aprendizado por
   correção funcionou de ponta a ponta.
8. (Opcional, só se quiser testar o caminho de falha) Parar o serviço do Ollama
   (`Stop-Process -Name ollama -Force` ou fechar o app na bandeja do sistema) e processar
   um terceiro documento de um fornecedor totalmente novo, sem regra e sem histórico
   fuzzy nenhum — confirmar que o documento ainda é processado normalmente e termina como
   "SEM CLASSIFICAÇÃO" (não `ERRO`, não lote `FALHOU`) — prova que a resiliência da IA
   está funcionando. Religar o Ollama depois (`ollama serve` ou reabrir o app).

---

## Post-Plan Notes

- Fase 4 está completa quando todas as 12 tarefas estiverem commitadas e a verificação
  manual da Task 12 passar (incluindo pelo menos uma classificação real por IA e um ciclo
  completo de correção → regra criada → próximo documento do mesmo fornecedor batendo
  direto na regra).
- O próximo spec (`Fase 5 — Interface de Revisão/Edição`) deve ser brainstormado
  separadamente, seguindo `superpowers:brainstorming`. Vai construir a fila de revisão em
  lote, atalhos de teclado, etc. — a correção pontual desta fase (um documento por vez, no
  painel de resultado) continua funcionando como está, sem ser substituída.
- Lembrete explícito (pedido do usuário durante o brainstorming desta fase): a exportação
  de planilha (Excel/CSV) com os documentos analisados fica para a Fase 6 (Relatórios),
  não foi incluída neste plano.
