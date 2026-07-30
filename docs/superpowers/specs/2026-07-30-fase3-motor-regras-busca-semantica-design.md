# Fase 3 — Motor de Regras + Busca Semântica — Design

Data: 2026-07-30
Status: Aprovado pelo usuário, aguardando plano de implementação

## Contexto

Quarto documento de especificação da série iniciada em
`docs/superpowers/specs/2026-07-24-fase0-fundacao-design.md`. As Fases 0 (fundação), 1
(upload + OCR) e 2 (extração de dados) estão completas e mergeadas em `master`. Esta fase
adiciona classificação automática de cada comprovante numa conta do plano de contas da
empresa, usando os campos extraídos na Fase 2 como entrada.

## Decisões de contexto herdadas das Fases 0/1/2

- 100% gratuito/open-source, sem serviços pagos, sem modelo de IA/ML nesta fase (embeddings
  e IA generativa ficam reservados para a Fase 4).
- Sem autenticação nesta fase.
- Execução local em Windows via terminal, sem Docker.
- SQLite agora, schema portável para PostgreSQL no futuro.
- Extração de dados (Fase 2) é a entrada desta fase: `pagador_nome`, `pagador_documento`,
  `recebedor_nome`, `recebedor_documento`, `valor`, `tipo_documento` de cada documento já
  processado.

## Objetivo da Fase 3

Classificar automaticamente cada comprovante numa conta analítica do plano de contas da
empresa, em duas etapas, na ordem:

1. **Motor de regras explícitas**: o usuário cadastra regras (CNPJ/CPF, tipo de documento,
   faixa de valor, palavra-chave no nome → conta). O motor encontra a regra mais específica
   que bate com o documento e classifica com alta confiança (`origem=REGRA`).
2. **Fallback por busca fuzzy**: se nenhuma regra bater, o sistema busca a classificação
   histórica mais similar (por nome do pagador/recebedor, usando `rapidfuzz`) entre
   documentos já classificados da mesma empresa, e sugere a mesma conta (`origem=FUZZY`).

Roda automaticamente dentro do worker de background (Fase 1), logo após a extração (Fase 2)
ser persistida com sucesso — mesmo pipeline único: OCR → extração → classificação. Inclui
CRUD mínimo de regras no frontend e exibição da classificação no painel de resultado do
documento.

## Modelo de dados

### Tabela `regras` (nova)

| Coluna | Tipo | Nullable | Descrição |
|---|---|---|---|
| `id` | int PK | não | |
| `empresa_id` | FK `empresas` | não | |
| `conta_id` | FK `contas` | não | validada como `conta_analitica=True` na criação |
| `lado_alvo` | enum `PAGADOR`/`RECEBEDOR` | sim | obrigatório apenas se `documento_fiscal` ou `palavra_chave_nome` estiver preenchido |
| `documento_fiscal` | string (dígitos) | sim | CNPJ/CPF normalizado, mesma normalização da Fase 2 |
| `tipo_documento` | enum `TipoDocumento` | sim | PIX/TED/DOC/BOLETO/OUTRO |
| `valor_min` | decimal | sim | faixa de valor; pode ser usado isoladamente ou combinado com `valor_max` |
| `valor_max` | decimal | sim | |
| `palavra_chave_nome` | string | sim | substring case-insensitive no nome do lado (`lado_alvo`) escolhido |
| `ativo` | bool | não | default `True` |
| `created_at` | datetime | não | |

Validação na criação/edição: pelo menos uma condição (`documento_fiscal`, `tipo_documento`,
`valor_min`/`valor_max`, `palavra_chave_nome`) deve estar preenchida — regra sem nenhuma
condição é rejeitada com erro claro.

### Tabela `classificacoes` (ganha colunas reais — era stub da Fase 0 com só `id`,
`empresa_id`, `created_at`)

| Coluna | Tipo | Nullable | Descrição |
|---|---|---|---|
| `id` | int PK | não | |
| `empresa_id` | FK `empresas` | não | herdado do stub |
| `documento_id` | FK `documentos`, único | não | relação 1:1 com documento, mesmo padrão de `extracoes` |
| `conta_id` | FK `contas` | não | |
| `origem` | enum `REGRA`/`FUZZY` | não | |
| `regra_id` | FK `regras` | sim | preenchido quando `origem=REGRA` |
| `score_similaridade` | float | sim | preenchido quando `origem=FUZZY`, faixa 0.0–1.0 |
| `created_at` | datetime | não | |

Documento sem classificação possível (nenhuma regra bate e não há histórico algum na
empresa para comparar) simplesmente não ganha linha em `classificacoes` — a API traduz a
ausência como `"SEM CLASSIFICAÇÃO"`, mesmo padrão do `"NÃO IDENTIFICADO"` da Fase 2.

## Motor de regras — algoritmo

Para cada documento:

1. Carrega todas as regras `ativo=True` da empresa.
2. Para cada regra, verifica se TODAS as condições preenchidas batem com os dados extraídos
   (AND lógico entre condições preenchidas; condições vazias na regra são ignoradas na
   avaliação — não restringem o match).
3. Entre as regras que bateram, escolhe a mais específica: conta-se quantas condições estão
   preenchidas (`documento_fiscal`, `tipo_documento`, faixa de valor — `valor_min`/`valor_max`
   juntos contam como uma condição —, `palavra_chave_nome`); a regra com mais condições
   preenchidas vence. Empate: a regra com `id` mais antigo (criada primeiro) vence.
4. `documento_fiscal` casa por dígitos normalizados (mesma normalização CPF/CNPJ da Fase 2).
5. `palavra_chave_nome` casa por substring case-insensitive, sem normalização de acento
   adicional por enquanto.

Se nenhuma regra bater, segue para o fallback fuzzy.

## Busca fuzzy — algoritmo

Quando nenhuma regra bate:

1. Busca todas as `classificacoes` já existentes da empresa (qualquer origem), junto com o
   `recebedor_nome`/`pagador_nome` do documento associado a cada uma.
2. Compara o `recebedor_nome` do documento atual contra os nomes históricos usando
   `rapidfuzz` (Levenshtein normalizado). Se `recebedor_nome` for `NULL`, usa `pagador_nome`
   no lugar (mesma prioridade recebedor → pagador usada na direção padrão do motor de
   regras).
3. Usa a `conta_id` do candidato histórico com maior score, sempre — sem limiar mínimo de
   similaridade (decisão explícita: preferir sempre sugerir algo a não sugerir nada). Em
   caso de empate de score entre candidatos com contas diferentes, usa o candidato com
   `created_at` mais recente (classificação mais nova).
4. Se não houver nenhuma classificação anterior na empresa (ex: primeiro documento
   processado), não há candidato — documento fica sem classificação.
5. Persiste com `origem=FUZZY`, `score_similaridade` = score encontrado, `regra_id=NULL`.

## Integração no worker

Dentro de `processar_lote_em_background` (Fase 1), logo após a `Extracao` (Fase 2) ser
persistida com sucesso, adiciona um passo de classificação:

1. Chama o motor de regras com os dados extraídos.
2. Se nenhuma regra bater, chama o fallback fuzzy.
3. Se algo for encontrado, persiste `Classificacao`.
4. Falhas na etapa de classificação caem no MESMO `try/except` externo que já existe no
   worker (mesma decisão de severidade usada para a extração na Fase 2 — nenhum
   try/except mais estreito ao redor só da classificação).

Documento sem extração bem-sucedida nunca chega na etapa de classificação (mesmo padrão:
só roda se a etapa anterior teve sucesso).

## API

CRUD de regras, escopado por empresa:

- `POST /empresas/{empresa_id}/regras` — criar
- `GET /empresas/{empresa_id}/regras` — listar
- `PATCH /empresas/{empresa_id}/regras/{regra_id}` — editar (inclusive `ativo`)
- `DELETE /empresas/{empresa_id}/regras/{regra_id}` — apagar

Extensão do resultado do documento: `GET /documentos/{id}/resultado` ganha um campo
`classificacao` (nullable), contendo a conta (código + descrição), `origem` e
`score_similaridade` (quando `origem=FUZZY`) — mesmo padrão de tradução NULL→string de
exibição da Fase 2, com `"SEM CLASSIFICAÇÃO"` quando não há linha.

## Frontend

- Tela mínima de regras por empresa: formulário para criar (conta, lado_alvo, CNPJ/CPF,
  tipo, faixa de valor, palavra-chave) + lista com apagar/ativar-desativar.
- Painel de resultado do documento (já existe da Fase 2) ganha mais uma linha mostrando a
  conta classificada, origem (regra/fuzzy) e score (se fuzzy).

## Dependências novas

- `rapidfuzz` (biblioteca Python gratuita/leve para similaridade de string, sem modelo de
  ML) — adicionar a `backend/requirements.txt`.

## Fora de escopo desta fase

- Interface de revisão/correção manual de classificações erradas (Fase 5).
- Reclassificação em massa quando uma regra é criada/editada depois de documentos já
  processados (documentos mantêm sua classificação até serem reprocessados manualmente —
  não há reprocessamento automático nesta fase).
- Aprendizado automático a partir de correções do usuário (Fase 4 — tabela `aprendizado`
  continua stub).
- Normalização de acento/case mais sofisticada na palavra-chave (iteração futura se
  necessário).
- Autenticação, multiempresa concorrente, ou qualquer coisa fora do escopo já estabelecido
  nas fases anteriores.
