# Fase 2 — Extração + Normalização de Dados — Design

Data: 2026-07-28
Status: Aprovado pelo usuário, aguardando plano de implementação

## Contexto

Terceiro documento de especificação da série iniciada em
`docs/superpowers/specs/2026-07-24-fase0-fundacao-design.md`. A Fase 0 (fundação) e a Fase 1
(upload + OCR) estão completas e mergeadas em `master`. Esta fase adiciona a extração de
campos estruturados a partir do texto bruto extraído pelo OCR na Fase 1, e sua normalização
— ainda sem motor de regras, busca semântica ou classificação por IA, que ficam para as
Fases 3+.

## Decisões de contexto herdadas das Fases 0/1

- 100% gratuito/open-source, sem serviços pagos.
- Sem autenticação nesta fase.
- Execução local em Windows via terminal, sem Docker.
- SQLite agora, schema portável para PostgreSQL no futuro.

## Objetivo da Fase 2

Extrair automaticamente, a partir do texto OCR de cada documento já processado na Fase 1,
um subconjunto essencial de campos estruturados — valor, data de pagamento, tipo de
documento, CPF/CNPJ e nome do pagador e do recebedor, e o banco — usando regras
determinísticas (regex/heurísticas), sem IA. Campos não identificados no texto ficam `NULL`
no banco (nunca inventados) e são exibidos como "NÃO IDENTIFICADO" na API/frontend. A
extração roda automaticamente como parte do mesmo pipeline de processamento da Fase 1, logo
após o OCR de um documento concluir com sucesso.

Ficam fora do escopo desta fase (adiados para iterações futuras, dado que variam muito entre
bancos/tipos de comprovante): agência, conta, número de autenticação, observações. Também
fica fora desta fase a normalização/unificação de variantes de nome de fornecedor (ex.
"ENERGISA CE" vs "ENERGISA CEARÁ") — isso é resolvido melhor mais adiante, chaveando por
CNPJ em vez de por nome, quando o motor de regras/aprendizado (Fase 3/4) entrar em cena.

## Modelo de dados

A tabela `extracoes`, criada como stub na Fase 0 (apenas `id`, `empresa_id`, `created_at`),
ganha colunas reais nesta fase via nova migration Alembic:

- **extracoes**: `id`, `documento_id` (FK, único — relação 1:1 com documento),
  `pagador_nome` (nullable), `pagador_documento` (CPF/CNPJ normalizado, só dígitos,
  nullable), `recebedor_nome` (nullable), `recebedor_documento` (nullable), `valor`
  (decimal, nullable), `data_pagamento` (date, nullable), `tipo_documento` (enum: `PIX`,
  `TED`, `DOC`, `BOLETO`, `OUTRO` — nunca nulo, default `OUTRO` quando nenhuma palavra-chave
  é encontrada), `banco_nome` (nullable), `created_at`.

Todo campo de conteúdo extraído (exceto `tipo_documento`, que sempre tem um valor válido —
`OUTRO` como fallback) é `nullable`: quando o extrator não encontra o dado no texto, o campo
fica `NULL` — nunca um valor inventado. A tradução de `NULL` para a string "NÃO
IDENTIFICADO" acontece na camada de apresentação (schema de resposta da API / frontend),
não é persistida no banco.

## Pipeline de extração

```
Documento OCR concluído (texto_extraido)
    |
Extrair campos via regex/heurísticas (valor, data, CNPJ/CPF, tipo de documento, nomes, banco)
    |
Normalizar cada campo (data -> ISO, valor -> decimal, documento -> só dígitos, nome -> limpo)
    |
Campo não encontrado -> NULL no banco
    |
Salvar Extracao vinculada ao Documento
```

Executado dentro do mesmo worker de OCR da Fase 1 (`processar_lote_em_background` /
`processar_documento`): depois que um documento individual termina o OCR com sucesso, antes
de marcar `documento.status = CONCLUIDO`, a extração roda e o resultado é salvo. Falha na
extração de um campo específico não falha o documento inteiro (cada extrator é
independente); apenas uma exceção não tratada no extrator cairia no mesmo tratamento de
erro (`FALHOU`/`ERRO`) que já existe no worker desde a Fase 1.

## Extratores e normalizadores

Cada extrator é uma função pura `texto: str -> valor | None`, testável isoladamente com
textos de exemplo — sem estado, sem I/O.

- **Tipo de documento**: procura palavras-chave no texto (`PIX`, `TED`, `DOC`, `BOLETO`) —
  a primeira encontrada define o tipo; nenhuma encontrada → `OUTRO`.
- **CPF/CNPJ**: regex captura sequências nos formatos `000.000.000-00` /
  `00.000.000/0000-00` (com ou sem pontuação), normaliza removendo toda pontuação, valida o
  comprimento (11 dígitos para CPF, 14 para CNPJ) antes de aceitar — não valida dígito
  verificador nesta fase (fica como possível melhoria futura).
- **Valor**: regex captura padrões como `R$ 1.234,56` / `R$1234,56`, normaliza para um valor
  decimal (`Decimal("1234.56")`).
- **Data**: regex captura `DD/MM/AAAA` (e variantes com `-` como separador), normaliza para
  `date` ISO.
- **Nomes (pagador/recebedor)**: heurística baseada em rótulos comuns em comprovantes
  brasileiros (linha/trecho após rótulos como "Pagador:", "De:", "Favorecido:", "Para:",
  "Beneficiário:"), com normalização básica: maiúsculas, espaços múltiplos colapsados,
  remoção de sufixos societários comuns (LTDA, ME, EIRELI, S/A, S.A.).
- **Banco**: procura por nomes de bancos conhecidos (lista fixa dos principais bancos
  brasileiros: Itaú, Bradesco, Banco do Brasil, Caixa, Santander, Nubank, Inter, e outros a
  definir no plano) no texto.

## API

O endpoint já existente `GET /documentos/{id}/resultado` (Fase 1) é estendido para incluir
os campos extraídos, em vez de criar um endpoint novo — semanticamente é "o resultado do
processamento desse documento", que agora inclui tanto o texto OCR quanto os dados
extraídos dele. Campos `NULL` no banco são serializados como a string "NÃO IDENTIFICADO" na
resposta.

## Frontend

A tela de resultados (Fase 1, `DocumentoList`/visualização de "Ver texto") passa a exibir
também os campos extraídos junto ao texto bruto, cada um mostrando "NÃO IDENTIFICADO" quando
ausente.

## Testes

- Testes de unidade por extrator, com múltiplos textos de exemplo cobrindo: caso encontrado,
  caso não encontrado (retorna `None`), casos de formatação variada (ex. CPF com e sem
  pontuação).
- Testes de unidade para cada normalizador (data, valor, documento, nome).
- Teste de integração do pipeline completo: processar um documento com texto OCR conhecido
  contendo todos os campos, confirmar que `GET /documentos/{id}/resultado` retorna os campos
  extraídos corretos; e um documento com texto que não contém determinado campo, confirmar
  que esse campo aparece como "NÃO IDENTIFICADO" na resposta.

## Fora de escopo (fica para fases futuras)

- Agência, conta, número de autenticação, observações.
- Unificação de variantes de nome de fornecedor (normalização por CNPJ/aprendizado).
- Validação de dígito verificador de CPF/CNPJ.
- Motor de regras, busca semântica, classificação contábil — Fase 3.
- Classificação por IA e aprendizado — Fase 4.
