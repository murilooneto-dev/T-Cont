# Documentos Unificados (Multi-Comprovante) — Design

Data: 2026-09-22
Status: Aprovado pelo usuário, aguardando plano de implementação

## Contexto

O sistema (Fases 0-6, todas completas e mergeadas) assume hoje que **um arquivo enviado
é um comprovante**: `POST /empresas/{id}/documentos` cria um `Documento` por arquivo, o
worker roda OCR sobre o arquivo inteiro (concatenando todas as páginas de um PDF em um
único texto), e a extração (Fase 2, regex) roda uma vez sobre esse texto concatenado,
produzindo uma `Extracao` e depois uma `Classificacao`.

O usuário forneceu um arquivo real de exemplo — `COMPROVANTES DE PAGAMENTOS DE BOLETOS
MATRIZ (2).pdf`, gerado pelo sistema do Banco do Brasil — com **70 páginas, cada uma um
comprovante de pagamento completo e independente** (PIX ou boleto, CNPJ pagador/recebedor
e valor diferentes por página). Hoje, subir esse arquivo geraria um único `Documento` com
o texto das 70 páginas misturado, e a extração capturaria (na melhor das hipóteses) só os
dados da primeira página — as outras 69 transações seriam perdidas. Além disso, o
`renderizar_paginas_pdf` atual tem um limite de 20 páginas
(`backend/app/infrastructure/ocr/renderizador_pdf.py:6`, comentário original: "comprovante
de pagamento praticamente nunca passa de duas páginas") — esse arquivo de 70 páginas seria
hoje rejeitado antes mesmo de chegar à extração.

O pedido do usuário, refinado durante o brainstorming: o sistema precisa continuar
aceitando comprovantes/extratos avulsos exatamente como hoje (nenhuma mudança nesse caso),
e além disso reconhecer quando um único arquivo enviado contém **múltiplos comprovantes**,
quebrando-o em documentos independentes que passam pelo resto do pipeline (extração,
classificação, fila de revisão, exportação) sem nenhuma mudança nessas etapas.

## Decisões de contexto herdadas das Fases 0-6

- 100% gratuito/open-source, sem autenticação, execução local Windows, SQLite portável.
- `Extracao` continua sendo produzida pelo motor de regex já existente (Fase 2) — esta
  fase não muda a lógica de extração em si, só quantas vezes ela roda e sobre qual texto.

## Decisões de escopo (aprovadas pelo usuário durante o brainstorming)

- **Extratos avulsos continuam exatamente como hoje.** Um extrato bancário tabular (várias
  transações listadas numa única página/tabela) **não** é quebrado em múltiplos
  comprovantes nesta fase — isso é um problema de extração de tabela, estruturalmente
  diferente, e fica fora de escopo.
- **Um comprovante pode ocupar mais de uma página** dentro de um arquivo unificado — a
  quebra não pode assumir "1 página = 1 comprovante" cegamente.
- **A quebra reaproveita a extração já existente como sinal de limite**, em vez de casar
  padrões de cabeçalho por banco/sistema (mais genérico, sem necessidade de cadastrar
  formato por formato).
- **Documentos unificados podem vir tanto com texto real** (gerados por sistema, ex.: o
  arquivo do BB) **quanto escaneados** (sem camada de texto, exigindo OCR por página) — a
  quebra precisa funcionar nos dois casos, o que implica que ela só pode acontecer **depois**
  do OCR (dentro do worker), nunca no upload.
- **Limite de páginas por PDF sobe de 20 para 300** — folga generosa acima do exemplo real
  (70 páginas), cobrindo um lote mensal inteiro, ainda protegendo contra um upload
  gigante/acidental.
- **Nenhuma tela nova.** A única mudança visível é como os documentos aparecem na lista já
  existente (status e nome).

## Objetivo desta fase

Quando um arquivo PDF enviado contém múltiplos comprovantes, o sistema deve detectar isso
automaticamente durante o processamento em lote e criar um `Documento` independente para
cada comprovante encontrado — cada um com sua própria extração e classificação, seguindo o
pipeline já existente sem nenhuma alteração downstream (fila de revisão, correção,
exportação). Um arquivo com um único comprovante (o caso de hoje, e a esmagadora maioria
dos uploads) deve continuar processando **exatamente como hoje**, sem nenhuma mudança de
comportamento ou de dado gravado.

## Modelo de dados

### `StatusDocumento` ganha um valor novo: `DIVIDIDO`

Quando o worker determina que um `Documento` originalmente enviado contém 2+ comprovantes,
esse documento original passa para `status=DIVIDIDO` — permanece no banco como registro de
proveniência (nome do arquivo, arquivo físico original, ainda baixável), mas nunca ganha
`OcrResultado`/`Extracao`/`Classificacao` próprios, e é excluído da fila de revisão (mesmo
tratamento que hoje já exclui documentos com `origem` que não seja `None`/`FUZZY` — aqui o
critério simplesmente ignora qualquer documento em `DIVIDIDO`, do mesmo jeito que já ignora
`PENDENTE`/`PROCESSANDO`/`ERRO`).

### `Documento` ganha uma coluna nova: `documento_origem_id` (FK opcional para `Documento`)

Cada comprovante "filho" extraído de um arquivo unificado é um `Documento` completo,
independente, com seu próprio `caminho_arquivo`, `OcrResultado`, `Extracao` e
`Classificacao` — e `documento_origem_id` apontando para o `Documento` original
(`DIVIDIDO`), só para rastreabilidade ("de onde veio esse comprovante"). Um documento
avulso enviado normalmente (o caso de hoje) tem `documento_origem_id=None`, sempre.

### Migration

Nova migration Alembic (`0006_documentos_unificados.py`, seguindo o padrão das anteriores):
adiciona a coluna `documento_origem_id` (nullable, FK para `documentos.id`, índice) e não
precisa alterar a coluna `status` em si (já é uma string livre validada pelo enum Python, o
mesmo padrão já usado para `OrigemClassificacao` ganhar `IA`/`MANUAL` na Fase 4 sem migration
de schema).

## Limite de páginas

`renderizar_paginas_pdf` (`backend/app/infrastructure/ocr/renderizador_pdf.py`): a
constante `MAX_PAGINAS` sobe de `20` para `300`. O comentário existente ("comprovante
praticamente nunca passa de duas páginas") deixa de ser verdade com documentos unificados
e é atualizado para refletir o novo cenário. Nenhuma outra mudança nessa função — ela já
devolve uma lista de imagens por página.

## OCR e extração por página

### `extrair_texto_nativo` deixa de concatenar páginas

Hoje (`backend/app/infrastructure/ocr/pdf_nativo.py`) devolve um único `str | None` com
todas as páginas juntas. Passa a devolver `list[str] | None` — uma entrada por página
(lista vazia tratada como `None`, mesma semântica de "sem texto nativo, cair para OCR" de
hoje). O limiar mínimo de texto (`TAMANHO_MINIMO_TEXTO`) passa a ser avaliado sobre o texto
combinado de todas as páginas (soma), não por página individual — uma página legitimamente
curta (ex.: só um QR code + poucas linhas) não deve, sozinha, derrubar o documento inteiro
para OCR.

### `processar_documento` (`backend/app/infrastructure/ocr/pipeline.py`) devolve resultado por página

`ResultadoPipelineOcr.texto: str` vira `ResultadoPipelineOcr.textos_por_pagina: list[str]`
(uma entrada por página do PDF; para uma imagem avulsa PNG/JPG, sempre uma lista de 1
elemento — imagens nunca são candidatas a divisão). Internamente, a função já processa
página por página tanto no caminho nativo (após a mudança acima) quanto no caminho de OCR
(`_executar_engine_em_imagens` já itera imagem por imagem, hoje só junta o resultado cedo
demais com `"\n".join(...)`) — a mudança é não descartar a fronteira entre páginas antes de
devolver o resultado, não uma reescrita do motor de OCR em si. Sem impacto de performance:
o mesmo trabalho de OCR já era feito por imagem, individualmente.

### Nova função: agrupamento de páginas em comprovantes

Novo módulo `backend/app/infrastructure/extracao/agrupamento.py`:

```python
def agrupar_paginas_em_comprovantes(textos_por_pagina: list[str]) -> list[list[int]]:
```

Recebe o texto de cada página (na ordem do documento) e devolve uma lista de segmentos,
cada segmento sendo a lista de índices de página (0-based) que pertencem ao mesmo
comprovante. Roda `extrair_dados_documento` (já existente, sem mudança) sobre cada página
isoladamente; uma página cuja extração tem `valor is not None` **e** pelo menos um de
`pagador_documento`/`recebedor_documento` preenchido é tratada como início de um novo
comprovante; qualquer outra página (extração incompleta) é anexada ao segmento em
andamento. A primeira página do documento sempre inicia o primeiro segmento,
independentemente do resultado da sua própria extração (nunca perde a primeira página por
falta de dado extraível — mesmo princípio já usado hoje para documentos sem dados
suficientes, que viram "SEM CLASSIFICAÇÃO" em vez de erro).

Um documento com um único segmento (resultado mais comum, e o único resultado possível
para um documento de 1 página) sinaliza ao worker "não é um documento unificado — processa
normal, sem criar `DIVIDIDO` nem filhos". Esse é o caminho que precisa ficar bit-a-bit
idêntico ao comportamento atual.

## Recorte de páginas em um novo arquivo físico

Novo módulo `backend/app/infrastructure/ocr/recorte_pdf.py` (ao lado de
`renderizador_pdf.py`, mesma camada):

```python
def recortar_paginas_pdf(conteudo_pdf: bytes, indices_paginas: list[int]) -> bytes:
```

Usa `fitz` (já dependência do projeto) para montar um novo PDF só com as páginas do
segmento, devolvendo os bytes prontos para `ArmazenamentoArquivos.salvar` (interface já
existente, sem mudança) — o comprovante filho é salvo como um arquivo físico independente,
do mesmo jeito que qualquer upload direto é salvo hoje.

## Integração no worker

Em `backend/app/infrastructure/workers/lote_worker.py`, o laço que hoje processa um
`documento_id` por vez e grava um `OcrResultado`/`Extracao` direto passa a, para
documentos PDF com mais de uma página:

1. Chamar `processar_documento` (já devolve por página, ver acima).
2. Chamar `agrupar_paginas_em_comprovantes` sobre os textos por página.
3. **Se 1 segmento só**: caminho idêntico ao atual — concatena o texto das páginas (nesse
   caso, todas), grava `OcrResultado`/`Extracao`/`Classificacao` no próprio `Documento`
   original, sem tocar em `status` além do já existente `CONCLUIDO`/`ERRO`. Zero mudança
   de comportamento observável para este caso.
4. **Se 2+ segmentos**: marca o `Documento` original como `DIVIDIDO` (sem
   `OcrResultado`/`Extracao`/`Classificacao` próprios). Para cada segmento, na ordem:
   recorta as páginas correspondentes do PDF original (`recortar_paginas_pdf`), salva como
   novo arquivo físico, cria um `Documento` filho (`documento_origem_id` apontando para o
   original, `nome_exibicao` = nome original + sufixo de página — ver seção de UI),
   `status=CONCLUIDO` direto (o OCR dessas páginas já foi feito no passo 1, não precisa
   refazer), grava `OcrResultado`/`Extracao` (a extração de cada segmento já foi calculada
   durante o agrupamento — reaproveitada, não recalculada) e roda a classificação (mesmo
   código REGRA→IA→FUZZY já usado para qualquer documento, sem alteração) para esse filho.
5. Documentos que não são PDF (imagem avulsa) ou PDF de 1 página só: pulam os passos 1-2
   inteiramente (sempre 1 segmento trivial), seguem o caminho já existente sem qualquer
   overhead novo.

### Contagem de progresso do lote

`LoteProcessamento.total_documentos`/`documentos_processados` contam por **arquivo
originalmente enviado**, não por comprovante final — um arquivo que virou 70 comprovantes
ainda conta como 1 no progresso do lote ("3 de 5 arquivos processados"), consistente com o
que o usuário via ao selecionar os arquivos para upload. Nenhuma mudança na tabela
`lotes_processamento` nem no cálculo existente — os filhos criados durante o processamento
de um documento não entram na contagem do lote que os gerou (não existiam quando o lote foi
criado).

## Frontend

Sem tela nova. `frontend/src/types/documento.ts`: `StatusDocumento` ganha `"DIVIDIDO"`.
`DocumentoList.tsx`/`FilaRevisao.tsx`: um documento `DIVIDIDO` aparece na lista "Todos os
Documentos" com esse status e sem o botão "Ver texto" (mesma condição já usada hoje para só
mostrar "Ver texto" em `CONCLUIDO`, estendida para também excluir `DIVIDIDO`); um texto
auxiliar indica quantos comprovantes ele gerou (ex.: "Dividido em 70 comprovantes" —
calculado no frontend contando quantos documentos da lista têm `documento_origem_id`
apontando para ele, sem endpoint novo). Cada comprovante filho aparece como uma linha
normal, com `nome_exibicao` já contendo o sufixo de página (`" — pág. 5"` ou
`" — pág. 5-6"` para segmentos de múltiplas páginas) atribuído pelo backend na criação —
nenhuma lógica de exibição nova no componente.

## Casos de borda

- **1 segmento** (a esmagadora maioria dos uploads, incluindo todo o histórico já
  processado): comportamento idêntico ao atual, testado explicitamente como regressão.
- **Primeira página sem extração completa**: ainda inicia o primeiro segmento (nunca
  perdida).
- **PDF além de 300 páginas**: mesmo erro claro de hoje (`PdfComPaginasDemais`), só com o
  novo limite.
- **Upload em lote misto** (arquivos avulsos + um unificado juntos): cada arquivo
  processado de forma independente pelo worker, exatamente como hoje — só o(s) arquivo(s)
  que resultam em 2+ segmentos ganham filhos.
- **Imagem avulsa (PNG/JPG)**: sempre 1 segmento trivial, nunca candidata a divisão.
- **Cancelamento de lote no meio do processamento de um documento unificado**: o
  documento em processamento no momento do cancelamento termina seu processamento atual
  (mesmo comportamento já existente para qualquer documento em andamento quando um lote é
  cancelado — este trabalho não muda essa semântica).

## Testes

- **Unitário do agrupamento** (`agrupar_paginas_em_comprovantes`): 1 página → 1 segmento; 2
  páginas cada uma com extração completa → 2 segmentos de 1 página; página 2 sem extração
  → anexada ao segmento 1 (comprovante de 2 páginas); primeira página sem extração ainda
  assim inicia o segmento 1; N páginas alternando completas/incompletas → segmentos
  corretos.
- **Unitário do recorte de PDF** (`recortar_paginas_pdf`): recorta um subconjunto de
  páginas de um PDF de teste, reabre o resultado com `fitz`/`pypdf` e confirma que tem
  exatamente as páginas esperadas, na ordem certa, com conteúdo legível.
- **Unitário/integração do `processar_documento`**: confirma que devolve
  `textos_por_pagina` com uma entrada por página (não mais concatenado), tanto no caminho
  PDF_NATIVO quanto no caminho de OCR de imagem.
- **Integração do worker**: upload de um PDF sintético de 3 páginas com 2 comprovantes
  completos e um caso de 2 páginas fundidas em 1 comprovante → confirma que o documento
  original vira `DIVIDIDO`, os 2 filhos corretos são criados com `Extracao`/`Classificacao`
  próprios e `documento_origem_id` correto, e a contagem de progresso do lote conta o
  arquivo original como 1 unidade.
- **Regressão (o teste mais importante)**: reprocessar um documento de 1 página (ou 2
  páginas que juntas formam 1 comprovante só) produz exatamente o mesmo `OcrResultado`/
  `Extracao`/`Classificacao` que o pipeline atual produziria — sem `DIVIDIDO`, sem filhos,
  sem `documento_origem_id`.
- **Verificação manual de ponta a ponta** com o arquivo real de 70 páginas fornecido pelo
  usuário: upload, processamento, confirmação de que ~70 comprovantes foram criados com
  dados corretos (CNPJ, valor, data por página), navegação pela lista, fila de revisão,
  exportação incluindo os comprovantes filhos.

## Fora de escopo desta fase

- Quebrar um extrato bancário tabular (várias transações numa única página/tabela) em
  múltiplos comprovantes — problema de extração de tabela, estruturalmente diferente do
  recorte de páginas desta fase.
- Casar padrões de cabeçalho específicos por banco/sistema como sinal de limite alternativo
  — a abordagem escolhida (reaproveitar a extração já existente) é deliberadamente mais
  genérica e não precisa disso.
- Qualquer tela ou fluxo novo de UI — a mudança é só na lista de documentos já existente.
- Reprocessamento automático de documentos já classificados anteriormente sob a lógica
  antiga (documentos já no banco não são retroativamente divididos).
