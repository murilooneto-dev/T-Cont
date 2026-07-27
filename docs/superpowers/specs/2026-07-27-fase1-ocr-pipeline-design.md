# Fase 1 — Upload + Pipeline de OCR — Design

Data: 2026-07-27
Status: Aprovado pelo usuário, aguardando plano de implementação

## Contexto

Segundo documento de especificação de fase da série iniciada em
`docs/superpowers/specs/2026-07-24-fase0-fundacao-design.md`. A Fase 0 (fundação: banco,
Empresas, Plano de Contas) está completa e mergeada em `master`. Esta fase adiciona o
pipeline de upload e OCR dos comprovantes de pagamento — ainda sem extração de campos
estruturados (pagador, valor, data etc.) nem classificação contábil, que ficam para as
Fases 2+.

## Decisões de contexto herdadas da Fase 0

- 100% gratuito/open-source, sem serviços pagos.
- Sem autenticação nesta fase.
- Execução local em Windows via terminal, sem Docker.
- SQLite agora, schema portável para PostgreSQL no futuro.

## Objetivo da Fase 1

Permitir que o usuário selecione uma empresa, envie múltiplos comprovantes (PDF/PNG/JPG)
de uma vez, e o sistema extraia o texto bruto de cada um — via extração nativa de PDF
quando possível, ou OCR (PaddleOCR com fallback para Tesseract) quando necessário —
mostrando progresso do lote e permitindo cancelamento. O resultado desta fase é o texto
bruto extraído por documento, visível numa tela de resultados. Nenhum campo estruturado
é extraído ainda (isso é Fase 2).

## Modelo de dados

As tabelas `documentos` e `ocr_resultados`, criadas como stub na Fase 0 (apenas `id`,
`empresa_id`, `created_at`), ganham colunas reais nesta fase via nova migration Alembic:

- **documentos**: `id`, `empresa_id` (FK), `nome_arquivo` (nome físico gerado, baseado em
  timestamp — nunca o nome enviado pelo usuário, para evitar path traversal),
  `nome_exibicao` (inicialmente igual ao nome enviado pelo usuário; atualizado na Fase 2
  para o formato "Tipo - Data" quando esses dados forem extraídos), `caminho_arquivo`,
  `extensao`, `tamanho_bytes`, `status` (enum: `PENDENTE`, `PROCESSANDO`, `CONCLUIDO`,
  `ERRO`), `mensagem_erro` (nullable), `created_at`, `updated_at`
- **ocr_resultados**: `id`, `documento_id` (FK, único — relação 1:1 com documento),
  `texto_extraido`, `metodo` (enum: `PDF_NATIVO`, `PADDLEOCR`, `TESSERACT`),
  `tempo_processamento_ms`, `created_at`

Tabela nova, adicionada nesta fase para suportar progresso/cancelamento de lote (não
prevista como stub na Fase 0, mas necessária para o requisito de barra de progresso):

- **lotes_processamento**: `id`, `empresa_id` (FK), `total_documentos`,
  `documentos_processados`, `status` (enum: `EM_ANDAMENTO`, `CONCLUIDO`, `CANCELADO`),
  `created_at`, `concluido_em` (nullable)

## Pipeline de OCR

```
Documento (PDF/imagem)
    |
[PDF?] -> tentar extracao nativa de texto (pypdf)
    |
  [texto suficiente encontrado?]
  SIM -> salva texto, metodo=PDF_NATIVO, fim
  NAO
    |
Renderizar pagina(s) em imagem (PyMuPDF -- nao exige Poppler instalado a parte)
    |
Tentar PaddleOCR
    |
  [sucesso?]
  SIM -> salva texto, metodo=PADDLEOCR, fim
  NAO
    |
Fallback: Tesseract
    |
  salva texto, metodo=TESSERACT (ou ERRO se ambos falharem)
```

- **Engine abstraction**: interface `OcrEngine` com `extrair_texto(imagem) -> str`,
  implementada por `PaddleOcrEngine` e `TesseractOcrEngine`. O orquestrador tenta
  nativo → Paddle → Tesseract, registrando qual método funcionou em `ocr_resultados.metodo`.
- **Paralelismo**: `ProcessPoolExecutor` (processos — OCR é CPU-bound) processando N
  documentos de um lote em paralelo, atualizando
  `lotes_processamento.documentos_processados` conforme cada um termina.
- **Cancelamento**: marcar o lote como `CANCELADO` interrompe o envio de novos documentos
  ao pool; documentos já em processamento terminam normalmente.

## API

```
POST   /empresas/{id}/documentos              (multipart, múltiplos arquivos)
         -> valida extensão (.pdf/.png/.jpg/.jpeg) e tamanho (máx 20MB/arquivo)
         -> salva em storage/empresa_{id}/documentos/{nome_fisico_gerado}
         -> cria Documento com status=PENDENTE
         -> retorna lista de Documentos criados (com erros de validação por arquivo,
            se houver)

GET    /empresas/{id}/documentos               (lista documentos da empresa, com status)

POST   /empresas/{id}/documentos/processar     -> cria um Lote, enfileira todos os
                                                   documentos PENDENTE da empresa no
                                                   pool, retorna lote_id

GET    /lotes/{id}                             -> status do lote (total, processados,
                                                   status) -- usado para polling

POST   /lotes/{id}/cancelar                    -> marca lote como CANCELADO

GET    /documentos/{id}/resultado              -> texto extraído + método usado (para a
                                                   tela de resultados)
```

- **Storage**: arquivos ficam em `storage/empresa_{id}/documentos/`, fora do banco,
  caminho relativo salvo em `documentos.caminho_arquivo`. O nome físico do arquivo é
  gerado (timestamp + sequencial), nunca deriva do nome enviado pelo usuário.
- **Progresso no frontend**: polling simples — o frontend consulta `GET /lotes/{id}` a
  cada poucos segundos até `status` sair de `EM_ANDAMENTO`.

## Frontend

Tela adicionada ao fluxo existente: após selecionar a empresa (já implementado na Fase 0),
uma área de drag-and-drop para anexar múltiplos arquivos, lista dos arquivos anexados com
status, botão "Processar" (dispara o lote) e um indicador de progresso (barra +
contador "X de Y processados") com botão "Cancelar", alimentado por polling em
`GET /lotes/{id}`. Ao concluir, a lista mostra o texto extraído (ou erro) por documento.

## Testes

- Testes de unidade dos engines de OCR com imagens/PDFs de exemplo (fixtures pequenas).
- Teste de unidade da lógica de decisão "extração nativa vs. OCR" (PDF com texto vs. PDF
  escaneado simulado).
- Teste de integração do upload (validação de extensão/tamanho, sanitização de nome de
  arquivo).
- Teste de integração do fluxo completo de processamento de um lote pequeno (2-3
  documentos), incluindo o polling de status e cancelamento.

## Fora de escopo (fica para fases futuras)

- Extração de campos estruturados do texto (pagador, valor, CNPJ, data etc.) — Fase 2.
- Atualização de `nome_exibicao` para o formato "Tipo - Data" — Fase 2, quando esses dados
  existirem.
- Normalização de nomes de fornecedores, motor de regras, busca semântica — Fase 2/3.
- Classificação por IA — Fase 4.
