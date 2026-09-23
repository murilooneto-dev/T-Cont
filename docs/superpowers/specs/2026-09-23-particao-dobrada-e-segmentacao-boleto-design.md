# Partida Dobrada + Correção da Segmentação de Boletos — Design

Data: 2026-09-23
Status: Aprovado pelo usuário, aguardando plano de implementação

## Contexto

Duas lacunas foram descobertas testando o sistema com dados reais (arquivo de 70 páginas
do usuário, "O Melhor Atacarejo", plano de contas real de 649 contas), depois que a
feature Documentos Unificados (multi-comprovante) já estava mergeada:

**1. A divisão de comprovantes sub-segmenta arquivos com boletos.** `agrupar_paginas_em_comprovantes`
(`backend/app/infrastructure/extracao/agrupamento.py`) só reconhece o início de um novo
comprovante quando a página tem `valor` **e** um documento fiscal (CNPJ/CPF do pagador ou
recebedor). Páginas de boleto no formato "COMPROVANTE DE PAGAMENTO DE TITULOS" (ex.: contas
de consumo pagas via convênio) não têm CNPJ impresso — só "Convênio" e "Código de Barras" —
então nunca disparam esse sinal e ficam fundidas ao comprovante anterior. No arquivo real do
usuário, isso reduziu 70 páginas a só 11 registros, um deles fundindo 15 páginas/comprovantes
de boleto distintos numa única `Extracao`/`Classificacao` (as outras ~14 transações ficam com
o texto bruto preservado no OCR, mas sem dado estruturado próprio).

Investigação confirmou: toda página de boleto do arquivo real tem a linha `Codigo de Barras`
(elemento padrão de qualquer comprovante de pagamento de boleto no Brasil, não específico do
Banco do Brasil). Isso dá um segundo sinal genérico, complementar ao CNPJ.

**2. O sistema classifica cada comprovante numa única conta, não num lançamento contábil de
partida dobrada.** Hoje `Classificacao` (domain entity, `backend/app/domain/entities.py:117`)
tem só `conta_id: int` — a cadeia REGRA → IA → FUZZY → correção manual decide UMA conta por
comprovante. Isso não é como contabilidade funciona: todo lançamento tem uma conta debitada e
uma creditada. O usuário precisa que o sistema monte o lançamento completo, usando o plano de
contas real da empresa (que já tem as contas bancárias cadastradas, ex.: "1.1.01.002.00003 —
Banco do Brasil S.A. AG 94-9 CC 82296-5 Matriz").

O usuário confirmou (brainstorming aprovado):

- A classificação atual (REGRA/IA/FUZZY/manual) continua decidindo a **conta de
  contrapartida** (despesa, fornecedor, receita, "duplicatas a receber" etc.) — nenhuma
  mudança nessa lógica.
- A **direção** do lançamento vem de comparar o CNPJ da própria empresa
  (`Empresa.cnpj`) contra `pagador_documento`/`recebedor_documento` da extração: se o CNPJ da
  empresa é o pagador, a empresa está pagando; se é o recebedor, está recebendo.
- **Empresa paga**: Débito = conta de contrapartida, Crédito = conta bancária.
- **Empresa recebe**: Débito = conta bancária, Crédito = conta de contrapartida (ex.: a conta
  que representa a liquidação de uma duplicata a receber, não uma nova receita).
- A **conta bancária** é resolvida casando o `banco_nome` já extraído contra as contas
  analíticas do plano cuja descrição contém aquele nome. Se existir **exatamente uma**
  correspondência, usa ela. Se houver **múltiplas** (ex.: duas contas do mesmo banco em
  agências diferentes) ou **nenhuma**, o lançamento fica incompleto e vai para revisão manual
  — mesmo destino de quando a direção não pode ser determinada (nenhum dos dois documentos
  bate com o CNPJ da empresa).

## Decisões de contexto herdadas das fases anteriores

- 100% gratuito/open-source, sem autenticação, execução local Windows, SQLite portável.
- A extração de dados (Fase 2) e a cadeia de classificação (Fase 3/4) não mudam de mecanismo
  — só ganham um significado mais preciso (contrapartida em vez de "a conta").
- `documento_origem_id`/`StatusDocumento.DIVIDIDO` (Documentos Unificados) não mudam.

## Parte 1 — Segmentação reconhece boletos sem CNPJ

### Sinal adicional

`agrupar_paginas_em_comprovantes` passa a iniciar um novo segmento quando a página tem
`valor` **e** (documento fiscal **ou** a página contém uma linha reconhecível de código de
barras). Isso é implementado como uma nova função de detecção de "código de barras presente"
no texto da página (regex simples sobre variações de grafia: "Codigo de Barras", "Código de
Barras", "Cod. de Barras" — o texto já vem sem acentos do OCR/extração nativa na prática, mas
a variação com acento entra por segurança), separada da extração de dados já existente (não
mexe em `extrair_dados_documento`).

### Correção do efeito colateral (bug bidirecional, achado pelo revisor final)

Hoje, quando nem `pagador_documento` nem `recebedor_documento` são achados por proximidade de
rótulo, `extrair_dados_documento` cai para "qualquer CNPJ/CPF encontrado no texto" (função
`extrair_documentos`, `backend/app/infrastructure/extracao/documento_fiscal.py`). Isso é
inofensivo quando o texto é de um comprovante só, mas dentro de um segmento fundido (ou, após
esta correção, em qualquer texto de página isolada que por acaso tenha um CNPJ solto, ex.: um
CNPJ de rodapé do banco) pode capturar um documento fiscal que não é do pagador/recebedor
reais — o mesmo mecanismo que causa tanto sub-segmentação quanto (o oposto) segmentação
indevida. Com o novo sinal de código de barras reduzindo drasticamente o tamanho dos
segmentos fundidos, esse efeito já diminui bastante; nenhuma mudança adicional na extração é
necessária nesta fase — fica registrado como uma limitação residual conhecida, não algo a
resolver agora.

## Parte 2 — Partida dobrada

### Modelo de dados

`Classificacao` ganha dois campos novos, mantendo `conta_id` como está (ele já representa a
conta de contrapartida — só passa a ser chamado assim conceitualmente, sem renomear a coluna
pra minimizar migração):

```python
@dataclass
class Classificacao:
    id: int | None
    empresa_id: int
    documento_id: int
    conta_id: int  # conta de contrapartida (o que já existe hoje, sem mudança de nome/coluna)
    origem: OrigemClassificacao
    regra_id: int | None = None
    score_similaridade: float | None = None
    conta_bancaria_id: int | None = None  # resolvida automaticamente; None = revisão manual
    direcao: DirecaoLancamento | None = None  # PAGAMENTO | RECEBIMENTO; None = revisão manual
    created_at: datetime | None = None
```

Novo enum `DirecaoLancamento` (`backend/app/domain/enums.py`): `PAGAMENTO`, `RECEBIMENTO`.

Migration Alembic nova adiciona `conta_bancaria_id` (FK nullable para `contas.id`, com nome
de constraint explícito, seguindo o padrão já estabelecido em `0006_documentos_unificados.py`
para SQLite batch mode) e `direcao` (string nullable) na tabela `classificacoes`.

### Resolução da direção e da conta bancária

Novo módulo `backend/app/infrastructure/classificacao/lancamento_contabil.py`, chamado logo
depois que a classificação de contrapartida (REGRA/IA/FUZZY) já decidiu `conta_id`:

```python
def resolver_direcao(empresa_cnpj: str, extracao: Extracao) -> DirecaoLancamento | None:
    """Compara o CNPJ da empresa contra pagador/recebedor extraídos.
    Ambos os documentos são normalizados (só dígitos) antes de comparar.
    None se nenhum dos dois bate com o CNPJ da empresa."""

def resolver_conta_bancaria(banco_nome: str | None, contas_bancarias: list[Conta]) -> int | None:
    """`contas_bancarias` = contas analíticas do plano cuja descrição contém o nome do
    banco (case-insensitive, sem acento). None se zero ou mais de uma correspondência."""
```

`contas_bancarias` é filtrado a partir das contas disponíveis já carregadas pelo worker
(`_listar_contas_analiticas`), usando `Conta.natureza == NaturezaConta.ATIVO` e um match de
substring entre `banco_nome` e `Conta.descricao` — não depende de nenhuma estrutura fixa do
plano de contas (código, posição na árvore), só do texto da descrição, pra continuar
genérico entre diferentes planos de contas de clientes diferentes.

### Onde entra no fluxo existente

`_processar_comprovante` (`lote_worker.py`) já grava a `Classificacao` depois de
`classificar_documento`. Depois dessa gravação, chama `resolver_direcao` e
`resolver_conta_bancaria` e preenche os dois campos novos antes do `classificacao_repo.criar`
(ou faz um `atualizar` logo em seguida — a decisão exata de qual fica pro plano de
implementação, mas o resultado final é a mesma linha de `Classificacao` já com os campos
preenchidos quando possível, ou `None` quando cai pra revisão manual).

### Fila de Revisão e exibição da classificação

Hoje a Fila de Revisão mostra documentos sem classificação ou com `origem=FUZZY`. Ela passa a
mostrar também documentos cuja `Classificacao` tem `direcao is None` **ou**
`conta_bancaria_id is None` — o lançamento está incompleto mesmo que a conta de contrapartida
já tenha uma origem confiável (REGRA/IA/MANUAL). A tela de correção
(`CorrecaoClassificacao.tsx`) ganha um segundo select, só pra conta bancária, ativo quando
`conta_bancaria_id` está faltando (a direção continua sem interface de correção nesta fase —
se a direção não foi resolvida automaticamente, é um sinal de extração ruim que cai pra
revisão manual do texto, não algo que o usuário escolhe manualmente; isso é uma limitação
aceita, documentada, não escondida).

Em todo lugar que hoje exibe "Classificação: código — descrição" como uma linha única
(`CorrecaoClassificacao.tsx`, usado tanto no painel "Ver texto" de `DocumentoList.tsx` quanto
na própria Fila de Revisão), passa a exibir duas linhas — "Débito: código — descrição" e
"Crédito: código — descrição" — usando o mesmo `resolver_lados_lancamento` do backend,
exposto via `ClassificacaoOut` (schema da API) com os campos adicionais necessários (código e
descrição da conta bancária, e a direção) para o frontend não precisar reimplementar a
lógica de resolução. Quando um lado não pôde ser resolvido, essa linha mostra "—" em vez de
quebrar a tela.

### Exportação de planilha

`ExportarDocumentosUseCase`/`gerar_planilha_documentos` trocam as colunas "Conta (código)" /
"Conta (descrição)" por quatro colunas: "Débito (código)", "Débito (descrição)", "Crédito
(código)", "Crédito (descrição)". O mapeamento débito/crédito a partir de
`(direcao, conta_id, conta_bancaria_id)` é uma função pura nova (`resolver_lados_lancamento`),
reaproveitada tanto pela exportação quanto pela API de resultado do documento
(`DocumentoResultadoOut`), pra não duplicar a lógica. Uma linha cuja `direcao` ou
`conta_bancaria_id` é `None` exibe as colunas de crédito ou débito correspondentes vazias
(não quebra a exportação, só fica incompleta — visível pro usuário, não escondida).

## Casos de borda e testes

- Nenhum dos dois documentos (pagador/recebedor) bate com o CNPJ da empresa → `direcao=None`,
  vai pra revisão manual.
- CNPJ da empresa aparece nos dois lados (extração ruim) → tratado como ambíguo,
  `direcao=None`.
- Zero contas bancárias no plano batem com o nome do banco extraído → `conta_bancaria_id=None`.
- Duas ou mais contas bancárias batem (mesmo banco, agências diferentes) → `conta_bancaria_id=None`.
- `banco_nome` é `None` (extração não achou o banco) → `conta_bancaria_id=None`.
- Correção manual da conta de contrapartida continua funcionando exatamente como hoje —
  não precisa re-resolver direção/banco nesse fluxo, só troca `conta_id`.
- Página de boleto sem CNPJ mas com "Código de Barras" inicia novo segmento corretamente;
  página de continuação sem nenhum dos dois sinais continua fundida ao segmento anterior.
- Regressão do arquivo real de 70 páginas do usuário: contagem de segmentos deve subir
  substancialmente acima dos 11 atuais (não necessariamente exatos 70, já que o objetivo é
  reduzir a fusão indevida, não garantir paridade perfeita com a granularidade humana).
