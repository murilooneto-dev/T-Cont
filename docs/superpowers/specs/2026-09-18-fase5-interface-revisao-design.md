# Fase 5 — Interface de Revisão/Edição — Design

Data: 2026-09-18
Status: Aprovado pelo usuário, aguardando plano de implementação

## Contexto

Sexto documento de especificação da série iniciada em
`docs/superpowers/specs/2026-07-24-fase0-fundacao-design.md`. As Fases 0 (fundação), 1
(upload + OCR), 2 (extração de dados), 3 (motor de regras + busca semântica) e 4 (IA
local + aprendizado por correção) estão completas e mergeadas em `master`. Esta fase
adiciona uma fila de revisão dedicada aos documentos que mais precisam de atenção
humana, com suporte a correção em lote e atalhos de teclado — hoje a única forma de
corrigir uma classificação é abrir o painel de resultado de um documento por vez dentro
da lista completa (`DocumentoList.tsx`), sem nenhum recorte por prioridade nem forma de
agir sobre vários documentos de uma vez.

## Decisões de contexto herdadas das Fases 0-4

- 100% gratuito/open-source, sem autenticação, execução local em Windows via terminal,
  sem Docker, SQLite portável para PostgreSQL — nenhuma dessas decisões é afetada por
  esta fase.
- Volume esperado por empresa na fila de revisão: poucas dezenas de documentos — não é
  necessário paginação na API nem no frontend, mesmo padrão já usado hoje em
  `DocumentoList` (carrega tudo de uma vez).
- Sistema de usuário único por sessão — não há necessidade de lock nem de atualização
  em tempo real entre abas/usuários concorrentes.

## Objetivo da Fase 5

Dar ao usuário um lugar único para revisar e corrigir os documentos que a classificação
automática (Fase 3/4) não resolveu com confiança, em vez de precisar navegar pela lista
completa de documentos procurando quais precisam de atenção. Cobre dois fluxos:

1. **Revisão individual rápida**: aceitar ("Confirmar") ou corrigir a classificação de
   um documento por vez, sem sair da fila.
2. **Correção em lote**: selecionar vários documentos (via checkbox, sem exigir que
   sejam do mesmo fornecedor) e aplicar a mesma conta a todos de uma vez.

## Critério de inclusão na fila (modelo de dados)

Não é necessária nenhuma coluna ou tabela nova. A fila de revisão é uma **query
derivada** sobre o estado já existente de `Classificacao`:

- Documentos **sem classificação** (`classificacao is None` — nenhuma das 3 camadas
  REGRA/IA/FUZZY conseguiu classificar).
- Documentos cuja classificação atual tem **`origem == FUZZY`**.

Documentos com `origem` `REGRA`, `IA` ou `MANUAL` nunca entram na fila — REGRA e IA são
sempre tratados como resultado de match exato/confiável (nenhum dos dois carrega um
score de incerteza), e MANUAL já significa que um humano revisou.

Quando um documento é confirmado ou corrigido (ver "Ações", abaixo), sua classificação
passa a `origem=MANUAL` — o que automaticamente o remove da fila na próxima consulta.
Não existe (e não é necessário) nenhum campo booleano "revisado" separado.

## API

### `GET /empresas/{empresa_id}/documentos/fila-revisao`

Novo endpoint. Retorna a lista de documentos da empresa que atendem ao critério acima,
já com os dados de classificação e extração inline — para evitar que o frontend precise
fazer uma chamada a `GET /documentos/{id}/resultado` por documento só para montar a
fila.

Response — lista de:

```json
{
  "documento": { ...DocumentoOut... },
  "extracao": { ...ExtracaoOut ou null... },
  "classificacao_sugerida": {
    "conta_id": int,
    "conta_codigo": str,
    "conta_descricao": str,
    "score_similaridade": float
  } | null
}
```

`classificacao_sugerida` é `null` para documentos sem classificação (SEM CLASSIFICAÇÃO)
e preenchido para os que têm `origem=FUZZY`. Reaproveita os schemas Pydantic existentes
(`DocumentoOut`, `ExtracaoOut` de `backend/app/api/schemas/documento_schemas.py`) mais
um schema novo e mínimo para o item sugerido (não é o mesmo shape de `ClassificacaoOut`,
que inclui `origem`/`regra_id` — aqui só interessa o que o usuário precisa ver pra
decidir).

A consulta reaproveita os repositórios já existentes (`DocumentoRepository`,
`ExtracaoRepository`, `ClassificacaoRepository`, `ContaRepository`) — sem necessidade de
SQL bruto nem de um repositório novo; a filtragem por critério de fila pode ser feita em
memória sobre os documentos já carregados da empresa (volume esperado: poucas dezenas),
seguindo o mesmo padrão de simplicidade já usado nas consultas existentes deste
projeto.

### `PATCH /documentos/classificacao/lote`

Novo endpoint. Recebe:

```json
{ "documento_ids": [1, 2, 3], "conta_id": 42 }
```

Itera cada `documento_id` chamando o `CorrigirClassificacaoUseCase` já existente (Fase
4, `backend/app/application/use_cases/classificacao_use_cases.py`) — cada documento
aprende de forma independente (usa seu próprio CNPJ/CPF fiscal, se houver, para
criar/atualizar uma `Regra`). Uma falha em um item **não interrompe** o processamento
dos demais — mesmo princípio de tolerância a falha parcial já usado no processamento de
lote de documentos das Fases 1-3.

Response:

```json
{
  "resultados": [
    { "documento_id": 1, "sucesso": true, "classificacao": { ...ClassificacaoOut... } },
    { "documento_id": 2, "sucesso": false, "erro": "Conta não encontrada." }
  ]
}
```

Os erros de negócio já mapeados no endpoint individual (`DocumentoNaoEncontrado`,
`ContaNaoEncontrada`, `ContaNaoPertenceAEmpresa`, `ContaNaoAnalitica`) são capturados por
item — cada item do array de resultado reflete sucesso ou a mensagem de erro
correspondente, sem propagar exceção para a request como um todo.

### Confirmação individual (sem endpoint novo)

O botão "Confirmar" de um item `FUZZY` reaproveita o
`PATCH /documentos/{id}/classificacao` já existente (Fase 4) — o frontend simplesmente
envia `conta_id` igual ao `classificacao_sugerida.conta_id` que já veio da fila, sem
abrir nenhum seletor. Do ponto de vista do backend é uma correção normal (mesmo use
case, mesmo efeito de aprendizado — cria/atualiza `Regra` e grava em `aprendizado`).

## Frontend

Nova aba **"Fila de Revisão"** dentro de `EmpresasPage.tsx`, ao lado da lista de
documentos completa existente (que continua funcionando sem nenhuma mudança de
comportamento).

### Estrutura

- Cada linha da fila mostra: nome do documento, dados extraídos resumidos (pagador/
  recebedor, valor, tipo), e:
  - se `classificacao_sugerida` existir (FUZZY): a conta sugerida + o score, com um
    botão **"Confirmar"**;
  - um seletor de conta + botão **"Corrigir"**, disponível em toda linha (com ou sem
    sugestão) — mesmo comportamento de correção manual já existente na Fase 4.
- Um **checkbox** por linha para seleção livre (não precisa ser do mesmo fornecedor).
- Uma **barra de ação em lote**, visível apenas quando 1 ou mais checkboxes estão
  marcados: um seletor de conta + botão "Aplicar aos selecionados", que chama
  `PATCH /documentos/classificacao/lote`. Erros parciais são exibidos por item (qual
  documento falhou e por quê); os itens que falharam continuam marcados, para permitir
  nova tentativa; os que tiveram sucesso saem da fila na atualização seguinte.
- **Atalhos de teclado**: `↑`/`↓` movem um indicador de foco visual entre as linhas da
  fila; `Enter` ou `C` aciona "Confirmar" no item focado — só tem efeito em itens que
  têm `classificacao_sugerida` (itens SEM CLASSIFICAÇÃO não têm o que confirmar, a tecla
  não faz nada nesse caso).
- Fila vazia: mensagem simples "Nenhum documento pendente de revisão."

### Reaproveitamento de componente

A lógica de seletor de conta + tratamento de erro + filtro para contas analíticas que
hoje está implementada dentro de `DocumentoList.tsx` (Fase 4, correção individual) deve
ser extraída para um componente compartilhado (ex.: `CorrecaoClassificacao.tsx`),
reutilizado tanto pela lista de documentos completa quanto pela nova fila de revisão —
evita duplicar a mesma lógica de erro/filtro em dois lugares.

## Casos de borda

- **Lote com falha parcial**: já coberto acima — resposta por item, UI mostra o que
  falhou, mantém selecionado para retry.
- **Documento sai da fila entre a consulta e a ação**: se outro fluxo já corrigiu o
  documento (ex.: usuário reprocessou o lote de upload, ou corrigiu pela lista completa
  em outra aba), a tentativa de correção simplesmente resulta em um erro de negócio já
  tratado pelo use case (o documento não está mais nesse estado esperado) — nenhum
  tratamento especial de concorrência é necessário, dado o contexto de usuário único.
- **Fila vazia**: mensagem informativa, sem nenhum estado de erro.

## Fora de escopo desta fase

- Tempo real/lock entre sessões ou abas concorrentes.
- Qualquer alteração de comportamento na lista de documentos completa existente
  (`DocumentoList.tsx` continua mostrando todos os documentos, independente de status).
- Paginação — volume esperado (poucas dezenas por empresa) não justifica.
- Priorização automática dentro da fila (ordenação por score, urgência, etc.) — a fila
  é exibida na ordem natural de retorno da consulta (mesma ordem de criação já usada
  hoje).
- Exportação de planilha dos documentos revisados — reservado para a Fase 6.
