# Fase 4 — Camada de IA + Aprendizado — Design

Data: 2026-07-30
Status: Aprovado pelo usuário, aguardando plano de implementação

## Contexto

Quinto documento de especificação da série iniciada em
`docs/superpowers/specs/2026-07-24-fase0-fundacao-design.md`. As Fases 0 (fundação), 1
(upload + OCR), 2 (extração de dados) e 3 (motor de regras + busca semântica) estão
completas e mergeadas em `master`. Esta fase adiciona classificação por IA local como
fallback inteligente entre a Fase 3's regra e busca fuzzy, e um mecanismo de aprendizado
por correção manual do usuário.

## Decisões de contexto herdadas das Fases 0-3

- 100% gratuito/open-source. A camada de IA usa Ollama local (não paga), conforme
  decisão de contexto já registrada na Fase 0. A interface fica desacoplada o suficiente
  pra permitir troca futura por API paga, mas essa troca NÃO é implementada agora.
- Sem autenticação nesta fase.
- Execução local em Windows via terminal, sem Docker.
- SQLite agora, schema portável para PostgreSQL no futuro.
- Assume-se que o Ollama já está instalado e rodando localmente, com o modelo já baixado
  (`ollama pull llama3.2`) manualmente pelo usuário antes de usar esta fase — o sistema só
  se conecta ao servidor local, não faz setup automatizado do Ollama.

## Objetivo da Fase 4

Estender a cadeia de classificação automática da Fase 3 (regra → fuzzy) com uma camada de
IA no meio: **REGRA → IA → FUZZY**. A IA cobre especificamente o caso de um fornecedor
novo sem nenhum histórico de classificações anteriores na empresa — situação em que a
busca fuzzy (que depende de histórico) não tem nada pra comparar, mas a IA ainda pode
raciocinar sobre a descrição das contas do plano de contas e os dados extraídos do
documento.

Além disso, adiciona um mecanismo mínimo de correção manual no painel de resultado já
existente (Fase 2/3): quando o usuário corrige uma classificação errada (de qualquer
origem — regra, IA, fuzzy, ou nenhuma), o sistema "aprende" criando ou atualizando
automaticamente uma `Regra` (Fase 3) pelo CNPJ/CPF do recebedor (com fallback pro
pagador) — reaproveitando o motor de regras já existente, sem infraestrutura de
aprendizado de máquina nova.

## Resiliência da chamada à IA (decisão arquitetural)

Diferente da extração (Fase 2) e do motor de regras/fuzzy (Fase 3) — que rodam dentro do
mesmo `try/except` do worker e propositalmente derrubam o lote inteiro se algo der errado,
por serem bugs de lógica da aplicação — a chamada ao Ollama é uma dependência externa
opcional que pode legitimamente não estar disponível na máquina (mesma situação do
binário do Tesseract na Fase 1: "pode não estar instalado, mas o pipeline nunca falha por
causa disso"). Por isso, esta é uma exceção deliberada à regra geral "sem try/except mais
estreito":

- A etapa de IA captura suas próprias exceções internamente (erro de conexão, timeout,
  resposta não-parseável) e retorna `None` — nunca deixa a exceção propagar para o
  `try/except` externo do worker.
- `None` significa "a IA não deu uma resposta utilizável agora"; a cadeia cai
  automaticamente pro fuzzy, sem crashar o documento nem o lote.

## Modelo de dados

### `OrigemClassificacao` (enum existente, Fase 3) ganha dois valores novos

- `IA` — quando a etapa de IA classificou com sucesso.
- `MANUAL` — quando o usuário corrigiu diretamente a classificação de um documento.

### Tabela `aprendizado` (ganha colunas reais — era stub da Fase 0 com só `id`,
`empresa_id`, `created_at`)

Vira um log de auditoria de correções manuais:

| Coluna | Tipo | Nullable | Descrição |
|---|---|---|---|
| `id` | int PK | não | |
| `empresa_id` | FK `empresas` | não | herdado do stub |
| `documento_id` | FK `documentos` | não | |
| `conta_anterior_id` | FK `contas` | sim | `NULL` se o documento estava "SEM CLASSIFICAÇÃO" antes da correção |
| `origem_anterior` | enum `OrigemClassificacao` | sim | `NULL` se não havia classificação anterior |
| `conta_corrigida_id` | FK `contas` | não | conta escolhida pelo usuário na correção |
| `regra_id` | FK `regras` | sim | preenchida se a correção criou ou atualizou uma regra |
| `created_at` | datetime | não | |

### Configuração nova (`backend/app/core/config.py`)

- `ollama_host: str = "http://localhost:11434"`
- `ollama_model: str = "llama3.2"`
- `ollama_timeout_segundos: int = 15`

## Prompt e parsing da resposta da IA

Quando a etapa de IA é alcançada (nenhuma regra bateu), o motor monta um prompt fechado
(não gerativo/livre) contendo:

- Os dados extraídos do documento: tipo de documento, nome/documento do pagador, nome/
  documento do recebedor, valor, banco.
- A lista de contas analíticas (`conta_analitica=True`) do plano de contas da empresa,
  cada uma como `código — descrição`.
- Uma instrução pedindo que o modelo responda APENAS o código de uma das contas listadas,
  ou a palavra `NENHUMA` se nenhuma parecer adequada.

O parsing da resposta é estrito: só é aceita se o texto devolvido (após `strip()` e
normalização de case) bater exatamente com um dos códigos de conta oferecidos no prompt.
Qualquer outra coisa — texto livre, alucinação, código que não estava na lista, a palavra
`NENHUMA`, timeout, erro de conexão — é tratada como "sem resposta utilizável" → `None` →
a cadeia cai pro fuzzy. Não há parsing "inteligente" de texto livre nem correspondência
aproximada de código.

## Integração no worker

Dentro de `processar_lote_em_background` (Fases 1-3), o pipeline de classificação ganha
um passo entre regra e fuzzy:

1. Motor de regras (Fase 3, inalterado).
2. **Novo:** se nenhuma regra bateu, tenta a IA. As contas analíticas da empresa são
   carregadas uma vez por lote (mesmo padrão de cache já usado pra regras/histórico fuzzy
   na Fase 3), não recarregadas por documento.
3. Busca fuzzy (Fase 3, inalterada) — só roda se a IA não deu resposta utilizável.

Continua rodando automaticamente pra todo documento processado, sem intervenção do
usuário — a IA é só mais uma camada de fallback na cadeia automática, não algo acionado
manualmente.

## Correção manual + aprendizado

### API

`PATCH /documentos/{documento_id}/classificacao` — recebe `{ "conta_id": <int> }`. O use
case:

1. Registra a correção em `aprendizado` (conta anterior — pode ser `NULL` —, origem
   anterior — pode ser `NULL` —, conta corrigida).
2. Busca o `documento_fiscal` do recebedor (fallback pro pagador, mesma prioridade já
   usada na busca fuzzy da Fase 3) via a `Extracao` já persistida do documento.
3. Se um documento fiscal foi encontrado: procura, entre as regras já cadastradas da
   empresa, uma que tenha exatamente aquele `documento_fiscal` + `lado_alvo`
   correspondente. Se achar, atualiza o `conta_id` dela pra conta corrigida. Se não achar,
   cria uma nova regra com apenas essa condição preenchida (`documento_fiscal` +
   `lado_alvo`, sem `tipo_documento`/faixa de valor/palavra-chave).
4. Se nenhum documento fiscal foi encontrado (documento sem CPF/CNPJ identificado em
   nenhum lado): a correção só atualiza a classificação deste documento — não cria nem
   atualiza regra nenhuma (não há campo estável pra amarrar uma regra futura).
5. Cria ou atualiza a `Classificacao` do documento com `origem=MANUAL`, `conta_id` =
   conta corrigida, `regra_id` = a regra criada/atualizada (se houver), sem
   `score_similaridade`.

### Frontend

O painel de resultado do documento (já existe desde a Fase 2, já mostra a classificação
desde a Fase 3) ganha um seletor de conta + botão "Corrigir", reaproveitando a lista de
contas já carregada na página. Sem fila de revisão, sem atalhos de teclado, sem fluxo em
lote — isso é escopo da Fase 5 (Interface de revisão/edição).

## Fora de escopo desta fase

- Interface de revisão/fila de correções em lote, atalhos de teclado (Fase 5).
- Exportação de planilha (Excel/CSV) com os documentos analisados para importação em
  outro sistema — **pedido explícito do usuário durante o brainstorming desta fase**,
  mas mantido como próxima prioridade natural depois das Fases 4/5, reservado desde a
  Fase 0 como Fase 6 (Relatórios PDF/Excel). Revisitar nessa fase.
- Fine-tuning ou few-shot learning real com as correções acumuladas — o "aprendizado"
  aqui é 100% via regras determinísticas (Fase 3), a IA não recebe exemplos de
  correções passadas no prompt.
- Troca do Ollama por uma API de IA paga — a interface fica desacoplada o suficiente pra
  permitir essa troca depois, mas não é implementada agora.
- Setup automatizado do Ollama (instalação do binário, download/pull do modelo) —
  assume-se que o usuário já fez isso manualmente antes de usar esta fase.
- Autenticação, multiempresa concorrente, ou qualquer coisa fora do escopo já
  estabelecido nas fases anteriores.
