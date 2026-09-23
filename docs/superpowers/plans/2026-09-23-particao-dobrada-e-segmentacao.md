# Partida Dobrada + Correção da Segmentação de Boletos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer o sistema reconhecer corretamente cada página de boleto como um comprovante
separado (mesmo sem CNPJ impresso) e gerar um lançamento contábil de partida dobrada
(débito + crédito) para cada comprovante, em vez de uma única conta.

**Architecture:** Parte 1 adiciona um segundo sinal de limite de comprovante
(`agrupamento.py`) baseado na presença de "Código de Barras" na página. Parte 2 adiciona dois
campos novos a `Classificacao` (conta bancária resolvida + direção do lançamento), um módulo
puro novo (`lancamento_contabil.py`) que decide direção/conta bancária/lados do lançamento a
partir de dados já existentes (CNPJ da empresa, banco extraído, plano de contas), integra isso
no worker logo após a classificação de contrapartida (que não muda), e propaga através de
Fila de Revisão, API, exportação e frontend.

**Tech Stack:** Backend Python/FastAPI/SQLAlchemy/Alembic (SQLite). Frontend React/TypeScript.

**Spec:** `docs/superpowers/specs/2026-09-23-particao-dobrada-e-segmentacao-boleto-design.md`

## Global Constraints

- A classificação de contrapartida (REGRA → IA → FUZZY → correção manual) não muda de
  mecanismo nem de nome de campo (`Classificacao.conta_id` continua sendo essa conta).
- Direção do lançamento: `Empresa.cnpj` comparado (só dígitos) contra
  `Extracao.pagador_documento`/`recebedor_documento`. Empresa é pagador → `PAGAMENTO`. Empresa
  é recebedor → `RECEBIMENTO`. Nenhum dos dois, ou os dois ao mesmo tempo → `None`.
- Empresa paga: Débito = conta de contrapartida, Crédito = conta bancária.
- Empresa recebe: Débito = conta bancária, Crédito = conta de contrapartida.
- Conta bancária: match de substring (case-insensitive, sem acento) entre `banco_nome`
  extraído e `Conta.descricao`, restrito a contas analíticas com `natureza == ATIVO`. Zero ou
  mais de uma correspondência → sem conta bancária resolvida (fica `None`).
- Lançamento incompleto (`direcao is None` ou `conta_bancaria_id is None`) entra na Fila de
  Revisão, mesmo que a conta de contrapartida já tenha uma origem confiável.
- Sinal de novo comprovante na segmentação: `valor is not None and (tem_documento_fiscal or
  pagina_tem_codigo_barras)` — substitui a condição atual que só olhava documento fiscal.
- Migration Alembic usa `batch_alter_table` do SQLite com nome de constraint FK explícito
  (`fk_classificacoes_conta_bancaria_id`), seguindo o padrão de
  `backend/alembic/versions/0006_documentos_unificados.py`.
- Nenhuma mudança na lógica de extração (`extrair_dados_documento`) nem no motor de regras.

## Review Focus

- **Comprovante com `banco_nome` extraído mas nenhuma conta do plano contém esse texto na
  descrição** — usuário abre a Fila de Revisão esperando ver esse item; se
  `resolver_conta_bancaria` não devolver `None` de forma limpa (ex: estourar exceção em vez de
  devolver `None`), o lote inteiro trava. Coberto no Task 3 (teste de zero correspondências) e
  Task 4 (não deixa a exceção escapar do worker).
- **CNPJ da empresa aparece tanto como pagador quanto como recebedor** (extração ruim de um
  texto degenerado/fundido) — o usuário espera que isso vá para revisão manual, não que o
  sistema "escolha" uma direção arbitrária. Coberto no Task 3
  (`test_ambos_documentos_batem_com_cnpj_da_empresa_e_ambiguo`).
- **Correção manual da conta de contrapartida em um documento que já tinha conta bancária e
  direção resolvidas** — usuário espera que só a contrapartida mude, sem perder o resto do
  lançamento. Coberto no Task 2 (teste do repositório) e Task 6 (endpoint existente não deve
  zerar os campos novos).
- **Export com um documento cuja `Classificacao` é `None`** (nunca chegou a classificar) —
  colunas de débito/crédito devem ficar vazias sem quebrar a geração da planilha, não devem
  aparecer como texto "None". Coberto no Task 7.
- **Arquivo de boleto onde a variação de grafia do OCR é "Cod. Barras" ou "CODIGO DE BARRAS"
  em maiúsculas** — o usuário não vai reprocessar o arquivo pra descobrir que um acento ou
  capitalização quebrou a detecção. Coberto no Task 1 com casos parametrizados de grafia.

---

## Parte 1 — Segmentação reconhece boletos sem CNPJ

### Task 1: Sinal de "Código de Barras" no agrupamento de páginas

**Files:**
- Modify: `backend/app/infrastructure/extracao/agrupamento.py`
- Test: `backend/tests/unit/test_agrupamento.py`

**Interfaces:**
- Consumes: nada de tarefas anteriores (primeira tarefa do plano).
- Produces: `agrupar_paginas_em_comprovantes(textos_por_pagina: list[str]) -> list[list[int]]`
  continua com a mesma assinatura — só muda o critério interno de início de segmento. Tarefas
  seguintes (worker) continuam chamando exatamente como hoje, nenhuma mudança de interface.

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `backend/tests/unit/test_agrupamento.py` (o arquivo já existe com 7
testes usando as fixtures `_COMPLETA`/`_INCOMPLETA` no topo — não duplicar essas fixtures,
só adicionar os testes abaixo depois do último teste existente):

```python
_BOLETO_SEM_CNPJ_COM_BARRAS = (
    "COMPROVANTE DE PAGAMENTO\nConvenio VIVO FIXO/BRASIL\n"
    "Codigo de Barras   84670000000-9   92620082089-8\n"
    "Data do pagamento   17/08/2026\nValor Total   92,62"
)
_BOLETO_SEM_CNPJ_SEM_BARRAS = (
    "COMPROVANTE DE PAGAMENTO\nData do pagamento   17/08/2026\nValor Total   92,62"
)


def test_pagina_com_codigo_barras_mas_sem_cnpj_inicia_novo_segmento():
    resultado = agrupar_paginas_em_comprovantes([_COMPLETA, _BOLETO_SEM_CNPJ_COM_BARRAS])
    assert resultado == [[0], [1]]


def test_pagina_sem_codigo_barras_e_sem_cnpj_continua_fundida():
    resultado = agrupar_paginas_em_comprovantes([_COMPLETA, _BOLETO_SEM_CNPJ_SEM_BARRAS])
    assert resultado == [[0, 1]]


@pytest.mark.parametrize(
    "grafia",
    [
        "Codigo de Barras   84670000000-9",
        "Código de Barras   84670000000-9",
        "CODIGO DE BARRAS   84670000000-9",
        "Cod. de Barras   84670000000-9",
        "cod. barras   84670000000-9",
    ],
)
def test_variacoes_de_grafia_do_codigo_de_barras_sao_reconhecidas(grafia):
    texto = f"COMPROVANTE DE PAGAMENTO\n{grafia}\nData do pagamento   17/08/2026\nValor Total   92,62"
    resultado = agrupar_paginas_em_comprovantes([_COMPLETA, texto])
    assert resultado == [[0], [1]]


def test_pagina_com_codigo_barras_mas_sem_valor_nao_inicia_segmento():
    texto_sem_valor = "COMPROVANTE DE PAGAMENTO\nCodigo de Barras   84670000000-9"
    resultado = agrupar_paginas_em_comprovantes([_COMPLETA, texto_sem_valor])
    assert resultado == [[0, 1]]
```

Adicionar `import pytest` no topo do arquivo (junto com o import existente de
`agrupar_paginas_em_comprovantes`).

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_agrupamento.py -v`
Expected: os 5 testes novos FALHAM (a função ainda não reconhece código de barras); os 7
testes existentes continuam passando.

- [ ] **Step 3: Implementar o sinal de código de barras**

Substituir o conteúdo de `backend/app/infrastructure/extracao/agrupamento.py` por:

```python
import re

from app.infrastructure.extracao.pipeline import extrair_dados_documento

_CODIGO_BARRAS_RE = re.compile(
    r"c[oó]digo\s+de\s+barras|cod\.?\s+(de\s+)?barras", re.IGNORECASE
)


def _pagina_tem_codigo_barras(texto: str) -> bool:
    return _CODIGO_BARRAS_RE.search(texto) is not None


def _pagina_inicia_novo_comprovante(texto: str) -> bool:
    dados = extrair_dados_documento(texto)
    if dados.valor is None:
        return False
    tem_documento_fiscal = dados.pagador_documento is not None or dados.recebedor_documento is not None
    return tem_documento_fiscal or _pagina_tem_codigo_barras(texto)


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

O regex cobre "Codigo de Barras", "Código de Barras" (com/sem acento), "Cod. de Barras",
"Cod Barras", "cod. barras" — todas as variações de capitalização (flag `IGNORECASE`).

- [ ] **Step 4: Rodar os testes para confirmar que passam**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_agrupamento.py -v`
Expected: 12 passed (7 existentes + 5 novos).

- [ ] **Step 5: Rodar a suíte completa (regressão)**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: todos os testes passam, sem regressão (baseline antes desta tarefa: confirmar com
`git stash` + rodar antes de começar, ou usar o número reportado no ambiente do executor).

- [ ] **Step 6: Commit**

```bash
git add backend/app/infrastructure/extracao/agrupamento.py backend/tests/unit/test_agrupamento.py
git commit -m "feat: recognize boleto pages without CNPJ via codigo de barras signal"
```

---

## Parte 2 — Partida dobrada

### Task 2: Schema — enum, entidade, migration, model, repositório

**Files:**
- Modify: `backend/app/domain/enums.py`
- Modify: `backend/app/domain/entities.py`
- Create: `backend/alembic/versions/0007_partida_dobrada.py`
- Modify: `backend/app/infrastructure/db/models.py`
- Modify: `backend/app/infrastructure/repositories/sqlalchemy_classificacao_repository.py`
- Test: `backend/tests/integration/test_sqlalchemy_classificacao_repository.py`
- Test: `backend/tests/integration/test_fase1_migration.py` (verificar se precisa de ajuste)

**Interfaces:**
- Consumes: nada de tarefas anteriores (independente da Parte 1).
- Produces: `DirecaoLancamento` (enum: `PAGAMENTO`, `RECEBIMENTO`).
  `Classificacao.conta_bancaria_id: int | None = None`,
  `Classificacao.direcao: DirecaoLancamento | None = None`. Tarefas seguintes (Task 3, 4, 6)
  usam esses dois campos e o enum.

- [ ] **Step 1: Adicionar o enum**

Em `backend/app/domain/enums.py`, adicionar ao final do arquivo:

```python
class DirecaoLancamento(str, Enum):
    PAGAMENTO = "PAGAMENTO"
    RECEBIMENTO = "RECEBIMENTO"
```

- [ ] **Step 2: Adicionar os campos na entidade**

Em `backend/app/domain/entities.py`, importar `DirecaoLancamento` na linha do import de
`app.domain.enums` (já existe um import agrupado no topo — adicionar `DirecaoLancamento` à
lista) e mudar a classe `Classificacao` de:

```python
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

para:

```python
@dataclass
class Classificacao:
    id: int | None
    empresa_id: int
    documento_id: int
    conta_id: int
    origem: OrigemClassificacao
    regra_id: int | None = None
    score_similaridade: float | None = None
    conta_bancaria_id: int | None = None
    direcao: DirecaoLancamento | None = None
    created_at: datetime | None = None
```

(`created_at` continua por último — os dois campos novos entram antes dele, mantendo
`created_at` como o último argumento posicional/nomeado, igual ao padrão já usado por
`documento_origem_id` em `Documento`.)

- [ ] **Step 3: Escrever o teste de migration que falha**

Adicionar a `backend/tests/integration/test_sqlalchemy_classificacao_repository.py` (depois
do último teste existente, `test_atualizar_classificacao`):

```python
def test_criar_classificacao_com_conta_bancaria_e_direcao(db_session):
    empresa, conta, documento = _empresa_conta_documento(db_session)
    conta_bancaria = SqlAlchemyContaRepository(db_session).criar(
        Conta(
            id=None, plano_conta_id=conta.plano_conta_id, codigo="1.1.01.002.00001",
            descricao="Banco do Brasil S.A.", natureza=NaturezaConta.ATIVO,
            conta_analitica=True,
        )
    )
    db_session.commit()
    repo = SqlAlchemyClassificacaoRepository(db_session)

    criada = repo.criar(
        Classificacao(
            id=None, empresa_id=empresa.id, documento_id=documento.id, conta_id=conta.id,
            origem=OrigemClassificacao.REGRA, regra_id=None, score_similaridade=None,
            conta_bancaria_id=conta_bancaria.id, direcao=DirecaoLancamento.PAGAMENTO,
        )
    )
    db_session.commit()

    encontrada = repo.obter_por_documento_id(documento.id)
    assert encontrada.conta_bancaria_id == conta_bancaria.id
    assert encontrada.direcao == DirecaoLancamento.PAGAMENTO


def test_atualizar_preserva_conta_bancaria_e_direcao_quando_so_conta_id_muda(db_session):
    empresa, conta, documento = _empresa_conta_documento(db_session)
    conta_bancaria = SqlAlchemyContaRepository(db_session).criar(
        Conta(
            id=None, plano_conta_id=conta.plano_conta_id, codigo="1.1.01.002.00001",
            descricao="Banco do Brasil S.A.", natureza=NaturezaConta.ATIVO,
            conta_analitica=True,
        )
    )
    db_session.commit()
    repo = SqlAlchemyClassificacaoRepository(db_session)
    criada = repo.criar(
        Classificacao(
            id=None, empresa_id=empresa.id, documento_id=documento.id, conta_id=conta.id,
            origem=OrigemClassificacao.FUZZY, score_similaridade=0.7,
            conta_bancaria_id=conta_bancaria.id, direcao=DirecaoLancamento.RECEBIMENTO,
        )
    )
    db_session.commit()

    criada.conta_id = conta.id
    criada.origem = OrigemClassificacao.MANUAL
    criada.score_similaridade = None
    repo.atualizar(criada)
    db_session.commit()

    atualizada = repo.obter_por_documento_id(documento.id)
    assert atualizada.origem == OrigemClassificacao.MANUAL
    assert atualizada.conta_bancaria_id == conta_bancaria.id
    assert atualizada.direcao == DirecaoLancamento.RECEBIMENTO
```

Adicionar `DirecaoLancamento` ao import de `app.domain.enums` no topo do arquivo de teste
(junto com `NaturezaConta, OrigemClassificacao`).

- [ ] **Step 4: Rodar os testes para confirmar que falham**

Run: `cd backend && .venv/Scripts/python -m pytest tests/integration/test_sqlalchemy_classificacao_repository.py -v`
Expected: os 2 testes novos FALHAM com `TypeError` (a entidade `Classificacao` ainda não
aceita `conta_bancaria_id`/`direcao` — na verdade a entidade já aceita depois do Step 2, então
o erro real vai ser o `ClassificacaoModel`/repositório ainda não persistirem esses campos, ou
a coluna não existir no banco de teste em memória. Confirme a mensagem de erro exata antes de
prosseguir e ajuste sua expectativa, mas o resultado — falha — é o que importa aqui).

- [ ] **Step 5: Criar a migration**

Criar `backend/alembic/versions/0007_partida_dobrada.py`:

```python
"""partida dobrada: conta_bancaria_id e direcao em classificacoes

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("classificacoes") as batch_op:
        batch_op.add_column(sa.Column("conta_bancaria_id", sa.Integer, nullable=True))
        batch_op.add_column(sa.Column("direcao", sa.String(20), nullable=True))
        batch_op.create_foreign_key(
            "fk_classificacoes_conta_bancaria_id", "contas", ["conta_bancaria_id"], ["id"]
        )
    op.create_index(
        "ix_classificacoes_conta_bancaria_id", "classificacoes", ["conta_bancaria_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_classificacoes_conta_bancaria_id", table_name="classificacoes")
    with op.batch_alter_table("classificacoes") as batch_op:
        batch_op.drop_constraint("fk_classificacoes_conta_bancaria_id", type_="foreignkey")
        batch_op.drop_column("direcao")
        batch_op.drop_column("conta_bancaria_id")
```

Nota importante sobre `create_foreign_key`: o alvo é a tabela `contas` (não `classificacoes` —
diferente do padrão de `0006`, onde a FK era auto-referenciada na mesma tabela). Confirme que
o quarto argumento posicional (`referent_table`) está correto: `"contas"`.

- [ ] **Step 6: Atualizar `ClassificacaoModel`**

Em `backend/app/infrastructure/db/models.py`, mudar a classe `ClassificacaoModel` (linhas
172-188 no estado atual) de:

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

para (adicionando as duas colunas novas antes de `created_at`):

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
    conta_bancaria_id: Mapped[int | None] = mapped_column(
        ForeignKey("contas.id"), nullable=True, index=True
    )
    direcao: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
```

- [ ] **Step 7: Atualizar o repositório**

Em `backend/app/infrastructure/repositories/sqlalchemy_classificacao_repository.py`,
substituir o arquivo inteiro por:

```python
from sqlalchemy.orm import Session

from app.application.repositories import ClassificacaoRepository
from app.domain.entities import Classificacao
from app.domain.enums import DirecaoLancamento, OrigemClassificacao
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
        conta_bancaria_id=model.conta_bancaria_id,
        direcao=DirecaoLancamento(model.direcao) if model.direcao is not None else None,
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
            conta_bancaria_id=classificacao.conta_bancaria_id,
            direcao=classificacao.direcao.value if classificacao.direcao is not None else None,
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

    def atualizar(self, classificacao: Classificacao) -> Classificacao:
        model = self._session.get(ClassificacaoModel, classificacao.id)
        model.conta_id = classificacao.conta_id
        model.origem = classificacao.origem.value
        model.regra_id = classificacao.regra_id
        model.score_similaridade = classificacao.score_similaridade
        model.conta_bancaria_id = classificacao.conta_bancaria_id
        model.direcao = classificacao.direcao.value if classificacao.direcao is not None else None
        self._session.flush()
        return _to_entity(model)
```

`atualizar()` agora sincroniza TODOS os campos da entidade passada (incluindo os dois novos),
não só os quatro de antes. Isso é o que faz o teste do Step 3
(`test_atualizar_preserva_conta_bancaria_e_direcao_quando_so_conta_id_muda`) passar: quem
chama `atualizar()` depois de só mudar `conta_id`/`origem` (como
`CorrigirClassificacaoUseCase` já faz hoje) preserva `conta_bancaria_id`/`direcao` porque eles
foram lidos do banco pela mesma instância de entidade antes de serem re-gravados — não porque
o repositório os ignora.

- [ ] **Step 8: Rodar os testes para confirmar que passam**

Run:
```bash
cd backend
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m pytest tests/integration/test_sqlalchemy_classificacao_repository.py -v
```
Expected: 6 passed (4 existentes + 2 novos).

- [ ] **Step 9: Verificar e ajustar `test_fase1_migration.py` se necessário**

Abrir `backend/tests/integration/test_fase1_migration.py`. Se ele tiver algum assert de
conjunto exato de colunas para a tabela `classificacoes` (não tinha antes desta feature — o
teste original só cobre `documentos`, `ocr_resultados`, `lotes_processamento` — mas confirme
lendo o arquivo, já que uma tarefa anterior de outra fase pode ter mudado isso), adicione
`"conta_bancaria_id"` e `"direcao"` ao conjunto esperado. Se o teste não menciona
`classificacoes`, nenhuma mudança é necessária aqui.

- [ ] **Step 10: Rodar a suíte completa**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: todos os testes passam, sem regressão.

- [ ] **Step 11: Commit**

```bash
git add backend/app/domain/enums.py backend/app/domain/entities.py \
  backend/alembic/versions/0007_partida_dobrada.py backend/app/infrastructure/db/models.py \
  backend/app/infrastructure/repositories/sqlalchemy_classificacao_repository.py \
  backend/tests/integration/test_sqlalchemy_classificacao_repository.py
git commit -m "feat: add conta_bancaria_id and direcao to Classificacao schema"
```

---

### Task 3: Módulo `lancamento_contabil.py` — resolução de direção, conta bancária e lados

**Files:**
- Create: `backend/app/infrastructure/classificacao/lancamento_contabil.py`
- Test: `backend/tests/unit/test_lancamento_contabil.py`

**Interfaces:**
- Consumes: `DirecaoLancamento` (Task 2, `app.domain.enums`). `Conta`, `Extracao` (entidades
  já existentes, `app.domain.entities` — `Conta.natureza`, `Conta.descricao`,
  `Extracao.pagador_documento`, `Extracao.recebedor_documento`).
- Produces:
  - `resolver_direcao(empresa_cnpj: str, extracao: Extracao) -> DirecaoLancamento | None`
  - `resolver_conta_bancaria(banco_nome: str | None, contas_bancarias: list[Conta]) -> int | None`
  - `resolver_lados_lancamento(direcao: DirecaoLancamento | None, conta_contrapartida: Conta, conta_bancaria: Conta | None) -> tuple[Conta | None, Conta | None]`
  (retorna `(conta_debito, conta_credito)`)

  Task 4 (worker) usa `resolver_direcao` e `resolver_conta_bancaria`. Task 6 (API) e Task 7
  (exportação) usam `resolver_lados_lancamento`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `backend/tests/unit/test_lancamento_contabil.py`:

```python
from app.domain.entities import Conta, Extracao
from app.domain.enums import DirecaoLancamento, NaturezaConta, TipoDocumento
from app.infrastructure.classificacao.lancamento_contabil import (
    resolver_conta_bancaria,
    resolver_direcao,
    resolver_lados_lancamento,
)

_CNPJ_EMPRESA = "12.345.678/0001-99"


def _extracao(pagador_documento=None, recebedor_documento=None) -> Extracao:
    return Extracao(
        id=None, documento_id=1, pagador_nome=None, pagador_documento=pagador_documento,
        recebedor_nome=None, recebedor_documento=recebedor_documento, valor=None,
        data_pagamento=None, tipo_documento=TipoDocumento.PIX, banco_nome=None,
    )


def test_empresa_e_pagador_direcao_pagamento():
    extracao = _extracao(pagador_documento="12345678000199", recebedor_documento="99988877000166")
    assert resolver_direcao(_CNPJ_EMPRESA, extracao) == DirecaoLancamento.PAGAMENTO


def test_empresa_e_recebedor_direcao_recebimento():
    extracao = _extracao(pagador_documento="99988877000166", recebedor_documento="12345678000199")
    assert resolver_direcao(_CNPJ_EMPRESA, extracao) == DirecaoLancamento.RECEBIMENTO


def test_nenhum_documento_bate_com_cnpj_da_empresa_direcao_none():
    extracao = _extracao(pagador_documento="11111111000100", recebedor_documento="22222222000100")
    assert resolver_direcao(_CNPJ_EMPRESA, extracao) is None


def test_ambos_documentos_batem_com_cnpj_da_empresa_e_ambiguo():
    extracao = _extracao(pagador_documento="12345678000199", recebedor_documento="12.345.678/0001-99")
    assert resolver_direcao(_CNPJ_EMPRESA, extracao) is None


def test_nenhum_documento_extraido_direcao_none():
    extracao = _extracao(pagador_documento=None, recebedor_documento=None)
    assert resolver_direcao(_CNPJ_EMPRESA, extracao) is None


def _conta_banco(descricao: str, id_: int = 1) -> Conta:
    return Conta(
        id=id_, plano_conta_id=1, codigo=f"1.1.01.002.{id_:05d}", descricao=descricao,
        natureza=NaturezaConta.ATIVO, conta_analitica=True,
    )


def test_uma_correspondencia_de_banco_resolve():
    contas = [_conta_banco("Banco do Brasil S.A. AG 94-9", id_=1)]
    assert resolver_conta_bancaria("Banco do Brasil", contas) == 1


def test_banco_nome_none_nao_resolve():
    contas = [_conta_banco("Banco do Brasil S.A.", id_=1)]
    assert resolver_conta_bancaria(None, contas) is None


def test_zero_correspondencias_nao_resolve():
    contas = [_conta_banco("Banco Itaú S.A.", id_=1)]
    assert resolver_conta_bancaria("Banco do Brasil", contas) is None


def test_multiplas_correspondencias_nao_resolve():
    contas = [
        _conta_banco("Banco Santander AG 1054 C/C 13.000844-0", id_=1),
        _conta_banco("Banco Santander AG 1054 C/C 13.000990-8 - Filial", id_=2),
    ]
    assert resolver_conta_bancaria("Santander", contas) is None


def test_match_ignora_acento_e_maiuscula():
    contas = [_conta_banco("Banco Itaú S.A.", id_=1)]
    assert resolver_conta_bancaria("ITAU", contas) == 1


def _conta_contrapartida() -> Conta:
    return Conta(
        id=10, plano_conta_id=1, codigo="3.2.01", descricao="Despesa Teste",
        natureza=NaturezaConta.DESPESA, conta_analitica=True,
    )


def test_lados_lancamento_pagamento_debita_contrapartida_credita_banco():
    contrapartida = _conta_contrapartida()
    banco = _conta_banco("Banco do Brasil")
    debito, credito = resolver_lados_lancamento(DirecaoLancamento.PAGAMENTO, contrapartida, banco)
    assert debito is contrapartida
    assert credito is banco


def test_lados_lancamento_recebimento_debita_banco_credita_contrapartida():
    contrapartida = _conta_contrapartida()
    banco = _conta_banco("Banco do Brasil")
    debito, credito = resolver_lados_lancamento(DirecaoLancamento.RECEBIMENTO, contrapartida, banco)
    assert debito is banco
    assert credito is contrapartida


def test_lados_lancamento_direcao_none_ambos_none():
    contrapartida = _conta_contrapartida()
    banco = _conta_banco("Banco do Brasil")
    debito, credito = resolver_lados_lancamento(None, contrapartida, banco)
    assert debito is None
    assert credito is None


def test_lados_lancamento_banco_none_mas_direcao_conhecida_mostra_contrapartida():
    contrapartida = _conta_contrapartida()
    debito, credito = resolver_lados_lancamento(DirecaoLancamento.PAGAMENTO, contrapartida, None)
    assert debito is contrapartida
    assert credito is None
```

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_lancamento_contabil.py -v`
Expected: FAIL com `ModuleNotFoundError` (o módulo ainda não existe).

- [ ] **Step 3: Implementar o módulo**

Criar `backend/app/infrastructure/classificacao/lancamento_contabil.py`:

```python
import re
import unicodedata

from app.domain.entities import Conta, Extracao
from app.domain.enums import DirecaoLancamento


def _somente_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto)


def resolver_direcao(empresa_cnpj: str, extracao: Extracao) -> DirecaoLancamento | None:
    """Compara o CNPJ da empresa contra pagador/recebedor extraídos (só dígitos).

    None quando nenhum dos dois bate, ou quando os dois batem ao mesmo tempo
    (extração ambígua/degenerada) — os dois casos caem pra revisão manual.
    """
    cnpj_empresa = _somente_digitos(empresa_cnpj)
    pagador = _somente_digitos(extracao.pagador_documento) if extracao.pagador_documento else None
    recebedor = _somente_digitos(extracao.recebedor_documento) if extracao.recebedor_documento else None

    empresa_e_pagador = pagador == cnpj_empresa
    empresa_e_recebedor = recebedor == cnpj_empresa

    if empresa_e_pagador and empresa_e_recebedor:
        return None
    if empresa_e_pagador:
        return DirecaoLancamento.PAGAMENTO
    if empresa_e_recebedor:
        return DirecaoLancamento.RECEBIMENTO
    return None


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sem_acento.upper()


def resolver_conta_bancaria(banco_nome: str | None, contas_bancarias: list[Conta]) -> int | None:
    """Casa `banco_nome` (extraído do comprovante) contra a descrição das contas
    bancárias do plano (substring, sem acento, case-insensitive).

    None quando o banco não foi identificado na extração, quando nenhuma conta
    bate, ou quando mais de uma bate (ambiguidade entre agências/filiais do
    mesmo banco) — todos os casos caem pra revisão manual.
    """
    if banco_nome is None:
        return None
    alvo = _normalizar(banco_nome)
    correspondencias = [
        conta for conta in contas_bancarias if alvo in _normalizar(conta.descricao)
    ]
    if len(correspondencias) != 1:
        return None
    return correspondencias[0].id


def resolver_lados_lancamento(
    direcao: DirecaoLancamento | None,
    conta_contrapartida: Conta,
    conta_bancaria: Conta | None,
) -> tuple[Conta | None, Conta | None]:
    """Devolve (conta_debito, conta_credito) a partir da direção já resolvida.

    Se a direção não foi resolvida, não dá pra saber de que lado a
    contrapartida entra — os dois lados vêm None. Se a direção é conhecida mas
    a conta bancária não foi resolvida, a contrapartida ainda aparece no lado
    certo; só o lado do banco fica None.
    """
    if direcao is None:
        return None, None
    if direcao == DirecaoLancamento.PAGAMENTO:
        return conta_contrapartida, conta_bancaria
    return conta_bancaria, conta_contrapartida
```

- [ ] **Step 4: Rodar os testes para confirmar que passam**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_lancamento_contabil.py -v`
Expected: 15 passed.

- [ ] **Step 5: Rodar a suíte completa**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: todos os testes passam, sem regressão.

- [ ] **Step 6: Commit**

```bash
git add backend/app/infrastructure/classificacao/lancamento_contabil.py \
  backend/tests/unit/test_lancamento_contabil.py
git commit -m "feat: add lancamento_contabil module for direction/bank account resolution"
```

---

### Task 4: Integração no worker

**Files:**
- Modify: `backend/app/infrastructure/workers/lote_worker.py`
- Test: `backend/tests/integration/test_lote_worker_documentos_unificados.py` (novos testes
  no mesmo arquivo, não um arquivo separado — o setup `ambiente_com_worker` já existe lá e é
  exatamente o que estas tarefas precisam)

**Interfaces:**
- Consumes: `resolver_direcao`, `resolver_conta_bancaria` (Task 3).
  `Classificacao.conta_bancaria_id`, `Classificacao.direcao` (Task 2).
  `agrupar_paginas_em_comprovantes` com o sinal de código de barras (Task 1, mas não é
  chamado diretamente por esta tarefa — só se beneficia da correção quando o worker roda com
  arquivos reais).
- Produces: `_processar_comprovante` passa a persistir `conta_bancaria_id`/`direcao` em toda
  `Classificacao` criada pelo worker (caminho de 1 segmento e de N segmentos, sem distinção —
  mesmo helper compartilhado de sempre).

- [ ] **Step 1: Escrever os testes de integração que falham**

Adicionar ao final de `backend/tests/integration/test_lote_worker_documentos_unificados.py`
(o arquivo já tem o fixture `ambiente_com_worker`, o helper `_pdf_com_paginas` e
`_processar_e_aguardar` no topo — reaproveitar, não duplicar):

```python
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
        "CNPJ DO PAGADOR: 12.345.678/0001-99\nCNPJ: 99.988.877/0001-66\n"
        "BANCO DO BRASIL S.A.\nValor: R$ 150,00"
    )
    documento_id = client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("comprovante.pdf", conteudo, "application/pdf")},
    ).json()[0]["documento"]["id"]

    status_final = _processar_e_aguardar(client, empresa_id)
    assert status_final["status"] == "CONCLUIDO"

    resultado = client.get(f"/documentos/{documento_id}/resultado").json()
    assert resultado["classificacao"]["direcao"] == "PAGAMENTO"
    assert resultado["classificacao"]["debito_codigo"] == "3.2.01"
    assert resultado["classificacao"]["credito_codigo"] == "1.1.01.002.00001"


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
        "CNPJ DO PAGADOR: 12.345.678/0001-99\nCNPJ: 99.988.877/0001-66\nValor: R$ 150,00"
    )
    documento_id = client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("comprovante.pdf", conteudo, "application/pdf")},
    ).json()[0]["documento"]["id"]

    status_final = _processar_e_aguardar(client, empresa_id)
    assert status_final["status"] == "CONCLUIDO"

    resultado = client.get(f"/documentos/{documento_id}/resultado").json()
    assert resultado["classificacao"]["direcao"] == "PAGAMENTO"
    assert resultado["classificacao"]["debito_codigo"] == "3.2.01"
    assert resultado["classificacao"]["credito_codigo"] is None


def test_pdf_de_uma_pagina_continua_sem_classificacao_bancaria_quando_nao_ha_cnpj_da_empresa(
    ambiente_com_worker,
):
    # Regressão do caminho de 1 segmento: quando o documento não tem nenhum
    # documento fiscal batendo com a empresa, direção fica None e as colunas
    # de débito/crédito ficam ambas None — sem quebrar o processamento.
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
```

Nota: o endpoint de criação de conta (`POST /planos-contas/{id}/contas`) e o schema exato de
entrada podem ter um formato ligeiramente diferente do usado acima (ex: nome do campo pra
conta pai) — antes de escrever este teste, leia
`backend/app/api/routers/contas_router.py` e `backend/app/api/schemas/conta_schemas.py` (ou
equivalente) pra confirmar os nomes exatos de campo do `ContaCreateIn` (ou similar) e ajuste o
payload do teste. O mesmo vale para o endpoint de criação de regra
(`POST /empresas/{id}/regras`) — confirme o schema de entrada exato em
`backend/app/api/schemas/regra_schemas.py` antes de finalizar o payload.

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `cd backend && .venv/Scripts/python -m pytest tests/integration/test_lote_worker_documentos_unificados.py -k "direcao or bancaria or nao_ha_cnpj" -v`
Expected: FAIL (`resultado["classificacao"]["direcao"]` não existe ainda — `KeyError` ou
`None` onde não deveria).

- [ ] **Step 3: Buscar o CNPJ da empresa uma vez por lote e integrar em `_processar_comprovante`**

Em `backend/app/infrastructure/workers/lote_worker.py`:

1. Adicionar aos imports do topo:
```python
from app.domain.enums import DirecaoLancamento, NaturezaConta, StatusDocumento, StatusLote
from app.infrastructure.classificacao.lancamento_contabil import (
    resolver_conta_bancaria,
    resolver_direcao,
)
```
(a linha `from app.domain.enums import StatusDocumento, StatusLote` já existe — só estender
com `DirecaoLancamento, NaturezaConta` na mesma linha, em ordem alfabética.)

2. Mudar a assinatura de `_processar_comprovante` para receber `empresa_cnpj: str`:

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
    empresa_cnpj: str,
) -> None:
```

3. Dentro de `_processar_comprovante`, mudar o bloco que cria a `Classificacao` (o `if
resultado_classificacao is not None:` atual) de:

```python
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
```

para:

```python
    if resultado_classificacao is not None:
        direcao = resolver_direcao(empresa_cnpj, extracao_criada)
        conta_bancaria_id = None
        if extracao_criada.banco_nome is not None:
            contas_bancarias = [
                conta for conta in contas_disponiveis if conta.natureza == NaturezaConta.ATIVO
            ]
            conta_bancaria_id = resolver_conta_bancaria(extracao_criada.banco_nome, contas_bancarias)
        nova_classificacao = classificacao_repo.criar(
            Classificacao(
                id=None,
                empresa_id=documento.empresa_id,
                documento_id=documento.id,
                conta_id=resultado_classificacao.conta_id,
                origem=resultado_classificacao.origem,
                regra_id=resultado_classificacao.regra_id,
                score_similaridade=resultado_classificacao.score_similaridade,
                conta_bancaria_id=conta_bancaria_id,
                direcao=direcao,
            )
        )
```

4. Buscar o CNPJ da empresa uma vez por lote. Adicionar o import do repositório de empresa
   junto aos outros imports tardios dentro de `processar_lote_em_background` (perto de
   `SqlAlchemyDocumentoRepository`):

```python
    from app.infrastructure.repositories.sqlalchemy_empresa_repository import (
        SqlAlchemyEmpresaRepository,
    )
```

   Instanciar o repositório junto aos outros (`empresa_repo = SqlAlchemyEmpresaRepository(session)`,
   ao lado de `documento_repo = SqlAlchemyDocumentoRepository(session)`).

   Depois do bloco que resolve `regras`/`contas_disponiveis`/`historico_fuzzy` (que já lê
   `empresa_id_lote`), adicionar a resolução do CNPJ:

```python
            empresa_cnpj = ""
            if empresa_id_lote is not None:
                empresa = empresa_repo.obter_por_id(empresa_id_lote)
                if empresa is not None:
                    empresa_cnpj = empresa.cnpj
```

   (string vazia como padrão em vez de `None` — `resolver_direcao` espera `str`, e uma string
   vazia nunca bate com um CNPJ extraído de verdade, então o comportamento seguro — direção
   `None` — acontece naturalmente sem precisar de um `if empresa_cnpj:` extra dentro de
   `_processar_comprovante`.)

5. Passar `empresa_cnpj=empresa_cnpj` nas DUAS chamadas existentes de `_processar_comprovante`
   dentro do laço de consolidação (a do caminho de 1 segmento e a do caminho de N segmentos —
   ambas já passam `historico_fuzzy=historico_fuzzy` como último argumento nomeado; adicionar
   `empresa_cnpj=empresa_cnpj` logo depois, em cada uma das duas chamadas).

- [ ] **Step 4: Rodar os testes para confirmar que passam**

Run: `cd backend && .venv/Scripts/python -m pytest tests/integration/test_lote_worker_documentos_unificados.py -v`
Expected: todos os testes do arquivo passam, incluindo os 3 novos e os já existentes da
feature Documentos Unificados (regressão do caminho de 1 segmento continua intacta).

- [ ] **Step 5: Rodar a suíte completa**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: todos os testes passam. Esperado que ALGUNS testes existentes de outras suítes (ex:
`test_documentos_api.py`, `test_exportacao_api.py`, `test_fila_revisao_api.py`) possam
quebrar temporariamente se dependerem do formato antigo de `ClassificacaoOut` — isso é
esperado até a Task 6/7 rodarem; anote no relatório desta tarefa quais falharam e confirme que
são exatamente as relacionadas ao schema de saída, não a lógica do worker em si. Se a suíte
completa não estiver 100% verde ao final desta tarefa, documente exatamente isso no relatório
— não é um erro desta tarefa, é dependência esperada entre tarefas do mesmo plano.

- [ ] **Step 6: Commit**

```bash
git add backend/app/infrastructure/workers/lote_worker.py \
  backend/tests/integration/test_lote_worker_documentos_unificados.py
git commit -m "feat: resolve direcao and conta bancaria in the worker's classification step"
```

---

### Task 5: Fila de Revisão inclui lançamentos incompletos

**Files:**
- Modify: `backend/app/application/use_cases/fila_revisao_use_cases.py`
- Test: `backend/tests/unit/test_fila_revisao_use_cases.py`

**Interfaces:**
- Consumes: `Classificacao.direcao`, `Classificacao.conta_bancaria_id` (Task 2).
- Produces: `ListarFilaRevisaoUseCase.executar` continua com a mesma assinatura
  (`executar(empresa_id: int) -> list[ItemFilaRevisao]`) — só muda o critério de quais
  documentos entram. Nenhuma tarefa seguinte depende de um novo símbolo daqui.

- [ ] **Step 1: Escrever os testes que falham**

Adicionar a `backend/tests/unit/test_fila_revisao_use_cases.py` (depois do último teste
existente):

```python
from app.domain.enums import DirecaoLancamento


def test_classificacao_por_regra_com_direcao_e_conta_bancaria_faltando_entra_na_fila():
    ambiente = _ambiente()
    documento = _documento(ambiente)
    ambiente["classificacao_repo"].criar(
        Classificacao(
            id=None, empresa_id=1, documento_id=documento.id, conta_id=ambiente["conta"].id,
            origem=OrigemClassificacao.REGRA,
        )
    )

    itens = _use_case(ambiente).executar(1)

    assert len(itens) == 1
    assert itens[0].documento.id == documento.id


def test_classificacao_por_ia_com_conta_bancaria_resolvida_mas_direcao_faltando_entra_na_fila():
    ambiente = _ambiente()
    documento = _documento(ambiente)
    ambiente["classificacao_repo"].criar(
        Classificacao(
            id=None, empresa_id=1, documento_id=documento.id, conta_id=ambiente["conta"].id,
            origem=OrigemClassificacao.IA, conta_bancaria_id=99, direcao=None,
        )
    )

    itens = _use_case(ambiente).executar(1)

    assert len(itens) == 1


def test_classificacao_manual_com_lancamento_completo_nao_entra_na_fila():
    ambiente = _ambiente()
    documento = _documento(ambiente)
    ambiente["classificacao_repo"].criar(
        Classificacao(
            id=None, empresa_id=1, documento_id=documento.id, conta_id=ambiente["conta"].id,
            origem=OrigemClassificacao.MANUAL, conta_bancaria_id=99,
            direcao=DirecaoLancamento.PAGAMENTO,
        )
    )

    itens = _use_case(ambiente).executar(1)

    assert itens == []
```

Adicionar `DirecaoLancamento` ao import de `app.domain.enums` no topo do arquivo (junto com
`NaturezaConta, OrigemClassificacao, StatusDocumento, TipoDocumento`) — ou usar o import
inline mostrado acima, se preferir manter o topo do arquivo intocado; qualquer uma das duas
formas funciona, mantenha consistência com o estilo do resto do arquivo.

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_fila_revisao_use_cases.py -v`
Expected: os 2 primeiros testes novos FALHAM (`test_classificacao_por_regra_com_direcao...` e
`test_classificacao_por_ia_com_conta_bancaria...` — hoje REGRA/IA nunca entram na fila,
independente de `direcao`/`conta_bancaria_id`). O terceiro passa (já é o comportamento atual
para MANUAL, mas confirme).

- [ ] **Step 3: Implementar o critério novo**

Em `backend/app/application/use_cases/fila_revisao_use_cases.py`, mudar o corpo de
`executar` de:

```python
            classificacao = self._classificacao_repo.obter_por_documento_id(documento.id)
            if classificacao is not None and classificacao.origem != OrigemClassificacao.FUZZY:
                continue
```

para:

```python
            classificacao = self._classificacao_repo.obter_por_documento_id(documento.id)
            lancamento_incompleto = classificacao is not None and (
                classificacao.direcao is None or classificacao.conta_bancaria_id is None
            )
            ja_e_fuzzy = classificacao is not None and classificacao.origem == OrigemClassificacao.FUZZY
            if classificacao is not None and not ja_e_fuzzy and not lancamento_incompleto:
                continue
```

(o restante da função — construção de `sugestao`, busca de `extracao`, `itens.append(...)` —
não muda.)

- [ ] **Step 4: Rodar os testes para confirmar que passam**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_fila_revisao_use_cases.py -v`
Expected: todos os testes do arquivo passam (existentes + 3 novos).

- [ ] **Step 5: Rodar a suíte completa**

Run: `cd backend && .venv/Scripts/python -m pytest -q`

- [ ] **Step 6: Commit**

```bash
git add backend/app/application/use_cases/fila_revisao_use_cases.py \
  backend/tests/unit/test_fila_revisao_use_cases.py
git commit -m "feat: include incomplete double-entry classifications in Fila de Revisao"
```

---

### Task 6: API — `ClassificacaoOut` com débito/crédito + correção manual da conta bancária

**Files:**
- Modify: `backend/app/api/schemas/documento_schemas.py`
- Modify: `backend/app/core/exceptions.py`
- Create: `backend/app/application/use_cases/conta_bancaria_use_cases.py`
- Modify: `backend/app/api/routers/documentos_router.py`
- Test: `backend/tests/unit/test_conta_bancaria_use_cases.py`
- Test: `backend/tests/integration/test_documentos_api.py` (novos testes no arquivo existente)

**Interfaces:**
- Consumes: `resolver_lados_lancamento` (Task 3). `Classificacao.conta_bancaria_id`,
  `Classificacao.direcao` (Task 2).
- Produces: `ClassificacaoOut` ganha os campos `direcao`, `debito_codigo`,
  `debito_descricao`, `credito_codigo`, `credito_descricao` (todos opcionais). Novo endpoint
  `PATCH /documentos/{documento_id}/classificacao/conta-bancaria` (schema de entrada
  `CorrigirContaBancariaIn { conta_bancaria_id: int }`, resposta `ClassificacaoOut`). Task 8
  (frontend) consome os campos novos de `ClassificacaoOut` e chama esse endpoint novo.

- [ ] **Step 1: Adicionar a exceção nova**

Em `backend/app/core/exceptions.py`, adicionar (seguindo o padrão de
`DocumentoNaoEncontrado`, que já existe no arquivo):

```python
class ClassificacaoNaoEncontrada(DomainError):
    def __init__(self, documento_id: int):
        super().__init__(f"Documento {documento_id} ainda não tem uma classificação para corrigir.")
```

- [ ] **Step 2: Escrever o teste do use case que falha**

Criar `backend/tests/unit/test_conta_bancaria_use_cases.py`:

```python
import pytest

from app.application.use_cases.conta_bancaria_use_cases import CorrigirContaBancariaUseCase
from app.core.exceptions import (
    ClassificacaoNaoEncontrada,
    ContaNaoAnalitica,
    ContaNaoEncontrada,
    ContaNaoPertenceAEmpresa,
    DocumentoNaoEncontrado,
)
from app.domain.entities import Classificacao, Conta, Documento, PlanoContas
from app.domain.enums import DirecaoLancamento, NaturezaConta, OrigemClassificacao
from tests.fakes import (
    FakeClassificacaoRepository,
    FakeContaRepository,
    FakeDocumentoRepository,
    FakePlanoContasRepository,
)


def _ambiente():
    documento_repo = FakeDocumentoRepository()
    classificacao_repo = FakeClassificacaoRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    plano = plano_repo.criar(PlanoContas(id=None, empresa_id=1, nome="Plano"))
    conta_contrapartida = conta_repo.criar(
        Conta(
            id=None, plano_conta_id=plano.id, codigo="3.2.01", descricao="Despesa",
            natureza=NaturezaConta.DESPESA, conta_analitica=True,
        )
    )
    conta_banco = conta_repo.criar(
        Conta(
            id=None, plano_conta_id=plano.id, codigo="1.1.01.002.00001",
            descricao="Banco do Brasil", natureza=NaturezaConta.ATIVO, conta_analitica=True,
        )
    )
    documento = documento_repo.criar(
        Documento(
            id=None, empresa_id=1, nome_arquivo="a.pdf", nome_exibicao="a.pdf",
            caminho_arquivo="x/a.pdf", extensao=".pdf", tamanho_bytes=10,
        )
    )
    return {
        "documento_repo": documento_repo, "classificacao_repo": classificacao_repo,
        "conta_repo": conta_repo, "plano_repo": plano_repo, "documento": documento,
        "conta_contrapartida": conta_contrapartida, "conta_banco": conta_banco,
    }


def _use_case(ambiente):
    return CorrigirContaBancariaUseCase(
        ambiente["documento_repo"], ambiente["classificacao_repo"],
        ambiente["conta_repo"], ambiente["plano_repo"],
    )


def test_corrige_conta_bancaria_preservando_direcao_e_contrapartida():
    ambiente = _ambiente()
    ambiente["classificacao_repo"].criar(
        Classificacao(
            id=None, empresa_id=1, documento_id=ambiente["documento"].id,
            conta_id=ambiente["conta_contrapartida"].id, origem=OrigemClassificacao.REGRA,
            direcao=DirecaoLancamento.PAGAMENTO, conta_bancaria_id=None,
        )
    )

    resultado = _use_case(ambiente).executar(ambiente["documento"].id, ambiente["conta_banco"].id)

    assert resultado.conta_bancaria_id == ambiente["conta_banco"].id
    assert resultado.direcao == DirecaoLancamento.PAGAMENTO
    assert resultado.conta_id == ambiente["conta_contrapartida"].id
    assert resultado.origem == OrigemClassificacao.REGRA


def test_documento_inexistente_leva_a_erro():
    ambiente = _ambiente()
    with pytest.raises(DocumentoNaoEncontrado):
        _use_case(ambiente).executar(999, ambiente["conta_banco"].id)


def test_sem_classificacao_existente_leva_a_erro():
    ambiente = _ambiente()
    with pytest.raises(ClassificacaoNaoEncontrada):
        _use_case(ambiente).executar(ambiente["documento"].id, ambiente["conta_banco"].id)


def test_conta_inexistente_leva_a_erro():
    ambiente = _ambiente()
    ambiente["classificacao_repo"].criar(
        Classificacao(
            id=None, empresa_id=1, documento_id=ambiente["documento"].id,
            conta_id=ambiente["conta_contrapartida"].id, origem=OrigemClassificacao.REGRA,
        )
    )
    with pytest.raises(ContaNaoEncontrada):
        _use_case(ambiente).executar(ambiente["documento"].id, 999)
```

(Os testes de `ContaNaoPertenceAEmpresa`/`ContaNaoAnalitica` reaproveitam a mesma
`_validar_conta` já usada por `CorrigirClassificacaoUseCase` — não precisam de teste próprio
aqui, já são cobertos pela suíte existente de `test_classificacao_use_cases.py` que testa essa
função; o import deles no topo do arquivo de teste é só pra satisfazer o `except` do use
case, remova o import se seu linter reclamar de import não usado.)

- [ ] **Step 3: Rodar o teste para confirmar que falha**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_conta_bancaria_use_cases.py -v`
Expected: FAIL com `ModuleNotFoundError` (o módulo do use case ainda não existe).

- [ ] **Step 4: Implementar o use case**

Criar `backend/app/application/use_cases/conta_bancaria_use_cases.py`:

```python
from app.application.repositories import (
    ClassificacaoRepository, ContaRepository, DocumentoRepository, PlanoContasRepository,
)
from app.application.use_cases.classificacao_use_cases import _validar_conta
from app.core.exceptions import ClassificacaoNaoEncontrada, DocumentoNaoEncontrado
from app.domain.entities import Classificacao


class CorrigirContaBancariaUseCase:
    """Corrige só o lado bancário do lançamento (conta_bancaria_id), sem tocar
    na conta de contrapartida nem na direção já resolvida — é o caminho de
    revisão manual para quando `resolver_conta_bancaria` não conseguiu decidir
    sozinho (banco não identificado, ou múltiplas contas do mesmo banco).
    """

    def __init__(
        self,
        documento_repo: DocumentoRepository,
        classificacao_repo: ClassificacaoRepository,
        conta_repo: ContaRepository,
        plano_repo: PlanoContasRepository,
    ):
        self._documento_repo = documento_repo
        self._classificacao_repo = classificacao_repo
        self._conta_repo = conta_repo
        self._plano_repo = plano_repo

    def executar(self, documento_id: int, conta_bancaria_id: int) -> Classificacao:
        documento = self._documento_repo.obter_por_id(documento_id)
        if documento is None:
            raise DocumentoNaoEncontrado(documento_id)
        _validar_conta(self._conta_repo, self._plano_repo, conta_bancaria_id, documento.empresa_id)

        classificacao_existente = self._classificacao_repo.obter_por_documento_id(documento_id)
        if classificacao_existente is None:
            raise ClassificacaoNaoEncontrada(documento_id)

        classificacao_existente.conta_bancaria_id = conta_bancaria_id
        return self._classificacao_repo.atualizar(classificacao_existente)
```

(`_validar_conta` é uma função "privada" por convenção de nome, mas já é reaproveitada dentro
do mesmo pacote — importar direto de `classificacao_use_cases` é consistente com como o resto
do código já está organizado; não duplicar a lógica de validação.)

- [ ] **Step 5: Rodar o teste para confirmar que passa**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_conta_bancaria_use_cases.py -v`
Expected: 4 passed.

- [ ] **Step 6: Atualizar `ClassificacaoOut`**

Em `backend/app/api/schemas/documento_schemas.py`:

1. Adicionar `DirecaoLancamento` ao import de `app.domain.enums` no topo (linha 5 atual:
   `from app.domain.enums import MetodoOcr, OrigemClassificacao, StatusDocumento,
   TipoDocumento` → adicionar `DirecaoLancamento` em ordem alfabética).

2. Mudar `ClassificacaoOut` de:

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

para:

```python
class ClassificacaoOut(BaseModel):
    conta_id: int
    conta_codigo: str
    conta_descricao: str
    origem: OrigemClassificacao
    regra_id: int | None
    score_similaridade: float | None
    direcao: DirecaoLancamento | None
    debito_codigo: str | None
    debito_descricao: str | None
    credito_codigo: str | None
    credito_descricao: str | None

    @classmethod
    def from_classificacao(cls, classificacao, conta, conta_bancaria=None) -> "ClassificacaoOut":
        from app.infrastructure.classificacao.lancamento_contabil import resolver_lados_lancamento

        conta_debito, conta_credito = resolver_lados_lancamento(
            classificacao.direcao, conta, conta_bancaria
        )
        return cls(
            conta_id=classificacao.conta_id,
            conta_codigo=conta.codigo,
            conta_descricao=conta.descricao,
            origem=classificacao.origem,
            regra_id=classificacao.regra_id,
            score_similaridade=classificacao.score_similaridade,
            direcao=classificacao.direcao,
            debito_codigo=conta_debito.codigo if conta_debito else None,
            debito_descricao=conta_debito.descricao if conta_debito else None,
            credito_codigo=conta_credito.codigo if conta_credito else None,
            credito_descricao=conta_credito.descricao if conta_credito else None,
        )
```

   (`conta_bancaria=None` como default deixa as chamadas antigas que não passam esse
   argumento continuarem funcionando sem quebrar — mas TODAS as chamadas reais serão
   atualizadas no Step 7 para passar o valor correto.)

3. Adicionar, depois da classe `ClassificacaoOut`, o schema de entrada do endpoint novo:

```python
class CorrigirContaBancariaIn(BaseModel):
    conta_bancaria_id: int
```

- [ ] **Step 7: Atualizar os 3 call sites de `ClassificacaoOut.from_classificacao` e adicionar o endpoint novo**

Em `backend/app/api/routers/documentos_router.py`:

1. Adicionar aos imports: `CorrigirContaBancariaIn` (junto com os outros schemas já
   importados de `app.api.schemas.documento_schemas`), e
   `CorrigirContaBancariaUseCase` (de `app.application.use_cases.conta_bancaria_use_cases`,
   novo import), e `ClassificacaoNaoEncontrada` (junto com as outras exceções já importadas
   de `app.core.exceptions`).

2. Em `obter_resultado` (linhas 213-217 no estado atual), mudar:

```python
    classificacao_out = None
    if classificacao:
        conta = conta_repo.obter_por_id(classificacao.conta_id)
        if conta is not None:
            classificacao_out = ClassificacaoOut.from_classificacao(classificacao, conta)
```

para:

```python
    classificacao_out = None
    if classificacao:
        conta = conta_repo.obter_por_id(classificacao.conta_id)
        if conta is not None:
            conta_bancaria = (
                conta_repo.obter_por_id(classificacao.conta_bancaria_id)
                if classificacao.conta_bancaria_id is not None
                else None
            )
            classificacao_out = ClassificacaoOut.from_classificacao(classificacao, conta, conta_bancaria)
```

3. Em `corrigir_classificacao_em_lote` (linhas 244-247 no estado atual), aplicar a mesma
   mudança: buscar `conta_bancaria` a partir de `resultado.classificacao.conta_bancaria_id`
   antes de chamar `from_classificacao`, passando como terceiro argumento.

4. Em `corrigir_classificacao` (linhas 279-280 no estado atual), a mesma mudança: buscar
   `conta_bancaria` a partir de `classificacao.conta_bancaria_id` antes do
   `return ClassificacaoOut.from_classificacao(...)`.

5. Adicionar o endpoint novo, depois de `corrigir_classificacao` (ao final do arquivo):

```python
@router.patch(
    "/documentos/{documento_id}/classificacao/conta-bancaria", response_model=ClassificacaoOut
)
def corrigir_conta_bancaria(
    documento_id: int, payload: CorrigirContaBancariaIn, db: Session = Depends(get_db)
):
    documento_repo = SqlAlchemyDocumentoRepository(db)
    classificacao_repo = SqlAlchemyClassificacaoRepository(db)
    conta_repo = SqlAlchemyContaRepository(db)
    plano_repo = SqlAlchemyPlanoContasRepository(db)
    try:
        classificacao = CorrigirContaBancariaUseCase(
            documento_repo, classificacao_repo, conta_repo, plano_repo
        ).executar(documento_id, payload.conta_bancaria_id)
    except DocumentoNaoEncontrado as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ClassificacaoNaoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ContaNaoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ContaNaoPertenceAEmpresa, ContaNaoAnalitica) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    conta = conta_repo.obter_por_id(classificacao.conta_id)
    conta_bancaria = conta_repo.obter_por_id(classificacao.conta_bancaria_id)
    return ClassificacaoOut.from_classificacao(classificacao, conta, conta_bancaria)
```

- [ ] **Step 8: Escrever e rodar o teste de integração do endpoint novo**

Adicionar a `backend/tests/integration/test_documentos_api.py` (ler o arquivo primeiro pra
seguir exatamente o padrão de fixture/setup já usado nele — provavelmente já tem um helper
pra criar empresa+plano+conta+documento+classificação, reaproveitar em vez de duplicar):

```python
def test_corrigir_conta_bancaria_atualiza_apenas_esse_campo(client):
    # Montar empresa, plano, conta de contrapartida, conta bancária e documento
    # usando o(s) helper(s) já existentes neste arquivo de teste. Criar uma
    # Classificacao inicial com direcao=PAGAMENTO e conta_bancaria_id=None
    # (via o endpoint de correção normal ou inserindo direto, conforme o
    # padrão do arquivo). Chamar:
    resposta = client.patch(
        f"/documentos/{documento_id}/classificacao/conta-bancaria",
        json={"conta_bancaria_id": conta_banco_id},
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["credito_codigo"] is not None  # ou debito, dependendo da direção montada
```

(O corpo exato deste teste depende do helper de setup já existente no arquivo — escreva-o
seguindo o padrão local depois de ler `test_documentos_api.py` por completo; o ponto fixo é a
asserção final: depois de corrigir só a conta bancária, o lançamento fica completo.)

Run: `cd backend && .venv/Scripts/python -m pytest tests/integration/test_documentos_api.py -v`
Expected: todos os testes passam, incluindo o novo.

- [ ] **Step 9: Rodar a suíte completa**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: 100% verde agora — os testes que dependiam do formato antigo de `ClassificacaoOut`
(deixados quebrando ao final da Task 4) devem estar consertados por esta tarefa. Se algum
ainda falhar, ajuste as asserções desses testes existentes para o formato novo do schema
(campos adicionais não quebram testes que só checam os campos antigos, a menos que o teste
faça uma comparação de dicionário exato — nesse caso, adicione os campos novos esperados).

- [ ] **Step 10: Commit**

```bash
git add backend/app/api/schemas/documento_schemas.py backend/app/core/exceptions.py \
  backend/app/application/use_cases/conta_bancaria_use_cases.py \
  backend/app/api/routers/documentos_router.py \
  backend/tests/unit/test_conta_bancaria_use_cases.py \
  backend/tests/integration/test_documentos_api.py
git commit -m "feat: expose debito/credito in ClassificacaoOut and add manual bank account correction endpoint"
```

---

### Task 7: Exportação com colunas de débito e crédito

**Files:**
- Modify: `backend/app/application/use_cases/exportacao_use_cases.py`
- Modify: `backend/app/infrastructure/spreadsheet/documentos_exporter.py`
- Test: `backend/tests/unit/test_exportacao_use_cases.py`
- Test: `backend/tests/integration/test_exportacao_api.py` (verificar se precisa de ajuste)

**Interfaces:**
- Consumes: `resolver_lados_lancamento` (Task 3).
- Produces: `LinhaExportacao` ganha `debito_codigo`, `debito_descricao`, `credito_codigo`,
  `credito_descricao` no lugar de `conta_codigo`/`conta_descricao`. Nenhuma tarefa depende
  disso depois — última tarefa de código antes da verificação manual.

- [ ] **Step 1: Escrever o teste que falha**

Ler `backend/tests/unit/test_exportacao_use_cases.py` primeiro para seguir o padrão exato de
fixture já usado nele (provavelmente `FakeEmpresaRepository`/`FakeDocumentoRepository`/etc.,
igual ao padrão visto em `test_fila_revisao_use_cases.py`). Adicionar um teste que:
1. Cria uma empresa, uma conta de contrapartida, uma conta bancária (natureza ATIVO).
2. Cria um documento CONCLUIDO com uma `Extracao` e uma `Classificacao` com
   `direcao=DirecaoLancamento.PAGAMENTO` e `conta_bancaria_id` apontando pra conta bancária.
3. Chama `ExportarDocumentosUseCase(...).executar(empresa_id)`.
4. Confirma que a `LinhaExportacao` resultante tem `debito_codigo` igual ao código da conta de
   contrapartida e `credito_codigo` igual ao código da conta bancária (não mais um único
   `conta_codigo`).

Também adicionar um teste com `classificacao=None` (documento concluído mas nunca
classificado) confirmando que `debito_codigo`, `debito_descricao`, `credito_codigo`,
`credito_descricao` vêm todos `None`, sem lançar exceção.

- [ ] **Step 2: Rodar o teste para confirmar que falha**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_exportacao_use_cases.py -v`
Expected: FAIL (`LinhaExportacao` ainda não tem os campos novos).

- [ ] **Step 3: Atualizar `LinhaExportacao` e `ExportarDocumentosUseCase`**

Em `backend/app/application/use_cases/exportacao_use_cases.py`:

1. Mudar `LinhaExportacao` de:

```python
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
```

para:

```python
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
    debito_codigo: str | None
    debito_descricao: str | None
    credito_codigo: str | None
    credito_descricao: str | None
    origem: str | None
```

2. No método `executar`, mudar o bloco que resolve `conta` e monta `LinhaExportacao` de:

```python
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
```

para:

```python
            extracao = self._extracao_repo.obter_por_documento_id(documento.id)
            classificacao = self._classificacao_repo.obter_por_documento_id(documento.id)
            conta_debito = conta_credito = None
            if classificacao is not None:
                conta_contrapartida = self._conta_repo.obter_por_id(classificacao.conta_id)
                conta_bancaria = (
                    self._conta_repo.obter_por_id(classificacao.conta_bancaria_id)
                    if classificacao.conta_bancaria_id is not None
                    else None
                )
                if conta_contrapartida is not None:
                    conta_debito, conta_credito = resolver_lados_lancamento(
                        classificacao.direcao, conta_contrapartida, conta_bancaria
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
                    debito_codigo=conta_debito.codigo if conta_debito else None,
                    debito_descricao=conta_debito.descricao if conta_debito else None,
                    credito_codigo=conta_credito.codigo if conta_credito else None,
                    credito_descricao=conta_credito.descricao if conta_credito else None,
                    origem=classificacao.origem.value if classificacao else None,
                )
            )
```

3. Adicionar o import de `resolver_lados_lancamento` no topo do arquivo:
```python
from app.infrastructure.classificacao.lancamento_contabil import resolver_lados_lancamento
```

- [ ] **Step 4: Rodar o teste para confirmar que passa**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_exportacao_use_cases.py -v`

- [ ] **Step 5: Atualizar `gerar_planilha_documentos`**

Em `backend/app/infrastructure/spreadsheet/documentos_exporter.py`, mudar `_COLUNAS` de:

```python
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
```

para:

```python
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
    ("Débito (código)", 14),
    ("Débito (descrição)", 30),
    ("Crédito (código)", 14),
    ("Crédito (descrição)", 30),
    ("Origem", 10),
]
```

E mudar a lista `valores` dentro do laço de `gerar_planilha_documentos` de:

```python
        valores = [
            linha.arquivo, linha.data_pagamento, linha.valor, linha.tipo,
            linha.pagador_nome, linha.pagador_documento, linha.recebedor_nome,
            linha.recebedor_documento, linha.banco_nome, linha.conta_codigo,
            linha.conta_descricao, linha.origem,
        ]
```

para:

```python
        valores = [
            linha.arquivo, linha.data_pagamento, linha.valor, linha.tipo,
            linha.pagador_nome, linha.pagador_documento, linha.recebedor_nome,
            linha.recebedor_documento, linha.banco_nome, linha.debito_codigo,
            linha.debito_descricao, linha.credito_codigo, linha.credito_descricao,
            linha.origem,
        ]
```

(`_COLUNA_DATA = 2` e `_COLUNA_VALOR = 3` não mudam — essas colunas continuam nas mesmas
posições, só as colunas depois de "Banco" mudaram de quantidade.)

- [ ] **Step 6: Rodar e ajustar os testes de exportação existentes**

Run: `cd backend && .venv/Scripts/python -m pytest tests/unit/test_exportacao_use_cases.py tests/integration/test_exportacao_api.py -v`

Se `test_exportacao_api.py` tiver asserções sobre nomes de coluna específicos ("Conta
(código)" etc.) ou sobre `LinhaExportacao.conta_codigo`, ajuste essas asserções pros nomes
novos (`debito_codigo`/`credito_codigo`, "Débito (código)"/"Crédito (código)").

- [ ] **Step 7: Rodar a suíte completa**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: 100% verde.

- [ ] **Step 8: Commit**

```bash
git add backend/app/application/use_cases/exportacao_use_cases.py \
  backend/app/infrastructure/spreadsheet/documentos_exporter.py \
  backend/tests/unit/test_exportacao_use_cases.py backend/tests/integration/test_exportacao_api.py
git commit -m "feat: export debito/credito columns instead of a single conta column"
```

---

### Task 8: Frontend — exibição e correção de débito/crédito

**Files:**
- Modify: `frontend/src/types/documento.ts`
- Modify: `frontend/src/components/CorrecaoClassificacao.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/DocumentoList.tsx` (só se necessário passar `contas`
  filtradas — verificar no Step 3)
- Modify: `frontend/src/components/FilaRevisao.tsx` (idem)

**Interfaces:**
- Consumes: `ClassificacaoOut` (Task 6) — campos `direcao`, `debito_codigo`,
  `debito_descricao`, `credito_codigo`, `credito_descricao`. Endpoint
  `PATCH /documentos/{id}/classificacao/conta-bancaria` (Task 6).
- Produces: nenhuma tarefa depende disso depois — penúltima tarefa do plano.

- [ ] **Step 1: Atualizar `types/documento.ts`**

Mudar a interface `Classificacao` de:

```typescript
export interface Classificacao {
  conta_id: number;
  conta_codigo: string;
  conta_descricao: string;
  origem: OrigemClassificacao;
  regra_id: number | null;
  score_similaridade: number | null;
}
```

para:

```typescript
export type DirecaoLancamento = "PAGAMENTO" | "RECEBIMENTO";

export interface Classificacao {
  conta_id: number;
  conta_codigo: string;
  conta_descricao: string;
  origem: OrigemClassificacao;
  regra_id: number | null;
  score_similaridade: number | null;
  direcao: DirecaoLancamento | null;
  debito_codigo: string | null;
  debito_descricao: string | null;
  credito_codigo: string | null;
  credito_descricao: string | null;
}
```

- [ ] **Step 2: Adicionar o método de API novo em `client.ts`**

Dentro de `api.documentos` (mesmo objeto onde `corrigirClassificacao` já existe), adicionar:

```typescript
    corrigirContaBancaria: (documentoId: number, contaBancariaId: number) =>
      request<Classificacao>(`/documentos/${documentoId}/classificacao/conta-bancaria`, {
        method: "PATCH",
        body: JSON.stringify({ conta_bancaria_id: contaBancariaId }),
      }),
```

(logo depois da definição de `corrigirClassificacao` já existente, mesmo bloco.)

- [ ] **Step 3: Atualizar `CorrecaoClassificacao.tsx`**

Substituir o arquivo inteiro por:

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
  onCorrigirContaBancaria,
}: {
  classificacao: Classificacao | null;
  contas: Conta[];
  onCorrigir: (contaId: number) => Promise<void>;
  onCorrigirContaBancaria: (contaBancariaId: number) => Promise<void>;
}) {
  const [contaCorrecaoId, setContaCorrecaoId] = useState<number | "">("");
  const [contaBancariaId, setContaBancariaId] = useState<number | "">("");
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

  async function handleCorrigirContaBancaria() {
    if (contaBancariaId === "") return;
    setErro(null);
    try {
      await onCorrigirContaBancaria(contaBancariaId);
      setContaBancariaId("");
    } catch (err) {
      setErro((err as Error).message);
    }
  }

  const contasBancarias = contas.filter(
    (conta) => conta.conta_analitica && conta.natureza === "ATIVO",
  );
  const precisaDeContaBancaria = classificacao !== null && classificacao.credito_codigo === null
    && classificacao.debito_codigo === null && classificacao.direcao !== null;

  return (
    <div className="rounded border border-slate-200 bg-white p-2">
      {classificacao ? (
        <div>
          <p>
            <span className="font-semibold">Débito: </span>
            {classificacao.debito_codigo
              ? `${classificacao.debito_codigo} — ${classificacao.debito_descricao}`
              : "—"}
          </p>
          <p>
            <span className="font-semibold">Crédito: </span>
            {classificacao.credito_codigo
              ? `${classificacao.credito_codigo} — ${classificacao.credito_descricao}`
              : "—"}
          </p>
          <p className="text-slate-500">
            {rotuloOrigem(classificacao.origem)}
            {classificacao.score_similaridade !== null &&
              ` — ${Math.round(classificacao.score_similaridade * 100)}%`}
          </p>
        </div>
      ) : (
        <span className="font-semibold">SEM CLASSIFICAÇÃO</span>
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
      {precisaDeContaBancaria && (
        <div className="mt-2 flex items-center gap-2">
          <select
            className="rounded border border-slate-300 px-2 py-1 text-xs"
            value={contaBancariaId}
            onChange={(e) => setContaBancariaId(e.target.value ? Number(e.target.value) : "")}
          >
            <option value="">Conta bancária...</option>
            {contasBancarias.map((conta) => (
              <option key={conta.id} value={conta.id}>
                {conta.codigo} — {conta.descricao}
              </option>
            ))}
          </select>
          <button
            onClick={handleCorrigirContaBancaria}
            disabled={contaBancariaId === ""}
            className="rounded bg-slate-800 px-2 py-1 text-xs text-white disabled:opacity-50"
          >
            Corrigir conta bancária
          </button>
        </div>
      )}
      {erro && <p className="mt-1 text-red-600">{erro}</p>}
    </div>
  );
}
```

Nota sobre `precisaDeContaBancaria`: o segundo select só aparece quando a direção já foi
resolvida (`classificacao.direcao !== null`) mas o lançamento ainda não tem NENHUM dos dois
lados preenchidos (`debito_codigo`/`credito_codigo` ambos `null`) — que é exatamente o caso de
"direção conhecida, banco não resolvido" descrito em `resolver_lados_lancamento` (Task 3):
quando `direcao` é conhecida mas `conta_bancaria` é `None`, um dos dois lados (o da
contrapartida) SEMPRE aparece preenchido — então checar os dois `null` ao mesmo tempo não
cobre esse caso. Ajuste a condição para: `classificacao !== null && classificacao.direcao !==
null && (classificacao.debito_codigo === null || classificacao.credito_codigo === null)` —
essa é a condição correta (exatamente um dos dois lados vazio, nunca os dois quando a direção
é conhecida). Use esta versão corrigida no código acima, não a primeira.

- [ ] **Step 4: Atualizar os dois consumidores de `CorrecaoClassificacao`**

Em `frontend/src/components/DocumentoList.tsx`, adicionar uma função `corrigirContaBancaria`
ao lado da já existente `corrigirClassificacao`:

```tsx
  async function corrigirContaBancaria(contaBancariaId: number) {
    if (resultadoAberto === null) return;
    const classificacao = await api.documentos.corrigirContaBancaria(
      resultadoAberto.documento.id,
      contaBancariaId,
    );
    setResultadoAberto({ ...resultadoAberto, classificacao });
  }
```

E passar `onCorrigirContaBancaria={corrigirContaBancaria}` no JSX onde `<CorrecaoClassificacao
.../>` já é renderizado (ao lado do `onCorrigir={corrigirClassificacao}` existente).

Em `frontend/src/components/FilaRevisao.tsx`, adicionar uma função equivalente
(`confirmarContaBancaria(documentoId, contaBancariaId)`, chamando
`api.documentos.corrigirContaBancaria` e depois `carregarFila(...)` do mesmo jeito que
`confirmar` já faz hoje) e passar como `onCorrigirContaBancaria` no JSX. Note que
`paraClassificacaoView` (a função que converte `ItemFilaRevisao` pra `Classificacao` na Fila
de Revisão) precisa dos campos novos também — atualizar seu retorno pra incluir
`direcao: null, debito_codigo: null, debito_descricao: null, credito_codigo: null,
credito_descricao: null` (a Fila de Revisão usa `classificacao_sugerida`, que vem de
`ClassificacaoSugeridaOut` — um schema DIFERENTE de `ClassificacaoOut`, que NÃO ganhou campos
novos nesta tarefa; então esses campos são sempre `null` nesse contexto específico — a Fila
de Revisão mostra a sugestão fuzzy, não um lançamento resolvido).

- [ ] **Step 5: Rodar o build do frontend**

Run: `cd frontend && npm run build`
Expected: build passa sem erros de TypeScript.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/documento.ts frontend/src/components/CorrecaoClassificacao.tsx \
  frontend/src/api/client.ts frontend/src/components/DocumentoList.tsx \
  frontend/src/components/FilaRevisao.tsx
git commit -m "feat: display debito/credito and add manual bank account correction UI"
```

---

### Task 9: Verificação manual E2E

**Files:** none (verification only; no commits)

Ambiente temporário: mesmo padrão de todas as fases anteriores — backend numa porta
alternativa (ex: 8001), frontend noutra (ex: 5174), `BASE_URL`/CORS temporários revertidos com
`git checkout --` ao final. Porta 8000/5173 podem estar ocupadas por outro processo nesta
máquina — confirme com `netstat` antes de escolher a porta.

- [ ] **Step 1: Suítes automatizadas**

Run: `cd backend && .venv/Scripts/python -m pytest -q` — esperado 100% verde.
Run: `cd frontend && npm run build` — esperado sucesso.

- [ ] **Step 2: Migration no banco de dev**

Run: `cd backend && .venv/Scripts/python -m alembic upgrade head` — confirma que a migration
0007 aplica sem erro no banco de desenvolvimento real (não só no banco de teste em memória).

- [ ] **Step 3: Reprocessar o arquivo real de 70 páginas**

Usar a mesma empresa "O Melhor Atacarejo" (ou uma nova, limpa) com o plano de contas real já
importado. Confirmar que existe pelo menos uma conta bancária no plano cuja descrição contém
o nome de um banco que aparece no arquivo (ex: "Banco do Brasil", "Itaú" — o plano real já tem
essas contas, confirmado em sessões anteriores). Fazer upload do arquivo
`COMPROVANTES DE PAGAMENTOS DE BOLETOS MATRIZ (2).pdf` (copiar da rede pra um diretório local
antes, via PowerShell — o Bash não alcança caminhos UNC) e processar o lote.

- [ ] **Step 4: Verificar os resultados**

- Contagem de segmentos: deve ser substancialmente maior que os 11 anteriores (o objetivo é
  reduzir a fusão indevida — não é necessário bater exatamente com 70, mas um número muito
  mais próximo é o sinal de sucesso; qualquer coisa perto de 11 ainda indica que o sinal de
  código de barras não está pegando as variações de grafia reais do arquivo, e vale investigar
  antes de prosseguir).
- Spot-check de 3-4 comprovantes via `GET /documentos/{id}/resultado`: confirmar que
  `classificacao.direcao` bate com o esperado (pagamento, já que é um arquivo de "boletos
  pagos pela matriz"), e que `debito_codigo`/`credito_codigo` fazem sentido contábil (débito =
  a conta de despesa/fornecedor classificada, crédito = a conta bancária correspondente ao
  banco do comprovante).
- Confirmar que pelo menos um comprovante cujo banco não bate com nenhuma conta do plano (ou
  bate com mais de uma) aparece na Fila de Revisão com o segundo select de conta bancária
  visível.
- Exportar a planilha e confirmar as 4 colunas novas (Débito código/descrição, Crédito
  código/descrição) preenchidas corretamente para os comprovantes com lançamento completo, e
  vazias (não "None" como texto) para os incompletos.

- [ ] **Step 5: Restaurar o ambiente e reportar**

`git checkout -- backend/app/main.py frontend/src/api/client.ts`, confirmar `git status`
limpo relativo aos commits deste plano, parar os servidores temporários, reportar pass/fail de
cada item acima antes da revisão final do branch inteiro.
