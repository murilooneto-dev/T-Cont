# Fase 6 — Exportação de Planilha — Design

Data: 2026-09-21
Status: Aprovado pelo usuário, aguardando plano de implementação

## Contexto

Sétimo e último documento de especificação do roadmap original, iniciado em
`docs/superpowers/specs/2026-07-24-fase0-fundacao-design.md`. As Fases 0 (fundação), 1
(upload + OCR), 2 (extração de dados), 3 (motor de regras + busca semântica), 4 (IA local
+ aprendizado por correção) e 5 (fila de revisão) estão completas e mergeadas em
`master`. Esta fase entrega o pedido explícito do usuário feito durante o brainstorming
da Fase 4: exportar os documentos analisados em uma planilha Excel, para importação em
outro sistema. Hoje não existe nenhum código de exportação — só existe *importação* de
plano de contas (`backend/app/infrastructure/spreadsheet/plano_contas_parser.py`,
`frontend/src/components/PlanoContasImport.tsx`).

## Decisões de contexto herdadas das Fases 0-5

- 100% gratuito/open-source. `openpyxl==3.1.5` já é dependência do projeto
  (`backend/requirements.txt`, usada na importação) — nenhuma dependência nova.
- Sem autenticação, execução local em Windows, SQLite portável para PostgreSQL —
  nenhuma dessas decisões é afetada por esta fase.
- Sem mudança de schema: nenhuma tabela, coluna ou migration nova.

## Objetivo da Fase 6

Permitir que o usuário baixe, com um clique, uma planilha `.xlsx` com todos os
comprovantes já processados de uma empresa, com os dados extraídos e a classificação
contábil atual de cada um, pronta para ser importada em outro sistema.

## Decisões de escopo (aprovadas pelo usuário)

- **Formato:** somente Excel (`.xlsx`). CSV está fora de escopo.
- **Documentos incluídos:** todos os documentos da empresa com `status == CONCLUIDO`, sem
  filtro por período nem por status de classificação. Documentos `PENDENTE`,
  `PROCESSANDO` ou `ERRO` não entram — não têm dados extraídos nem classificação.
- **Colunas:** conjunto completo (ver "Layout da planilha").
- **Fila de revisão pendente:** a exportação nunca é bloqueada; o frontend apenas avisa
  quando ainda há itens na fila de revisão da Fase 5.
- **Posição do botão:** ao lado do botão "Processar", na seção "Comprovantes", visível em
  qualquer aba.

## Layout da planilha

Um único arquivo com uma única aba chamada `Documentos`, uma linha por documento, com a
primeira linha sendo o cabeçalho:

| # | Coluna | Origem | Tipo da célula |
|---|---|---|---|
| 1 | Arquivo | `Documento.nome_exibicao` | texto |
| 2 | Data do pagamento | `Extracao.data_pagamento` | data nativa do Excel |
| 3 | Valor | `Extracao.valor` | número nativo do Excel |
| 4 | Tipo | `Extracao.tipo_documento` | texto |
| 5 | Pagador (nome) | `Extracao.pagador_nome` | texto |
| 6 | Pagador (CPF/CNPJ) | `Extracao.pagador_documento` | texto |
| 7 | Recebedor (nome) | `Extracao.recebedor_nome` | texto |
| 8 | Recebedor (CPF/CNPJ) | `Extracao.recebedor_documento` | texto |
| 9 | Banco | `Extracao.banco_nome` | texto |
| 10 | Conta (código) | `Conta.codigo` | texto |
| 11 | Conta (descrição) | `Conta.descricao` | texto |
| 12 | Origem | `Classificacao.origem` (`REGRA`/`IA`/`FUZZY`/`MANUAL`) | texto |

Regras de célula:

- Campo não identificado pela extração (`None`) sai como **célula vazia** — nunca o texto
  `NÃO IDENTIFICADO`, que é apenas um rótulo de exibição da API/UI.
- Documento sem classificação: colunas 10, 11 e 12 saem vazias.
- Valor e data são escritos como tipos nativos (número e data), para que o sistema de
  destino consiga somar/ordenar sem converter texto.
- CPF/CNPJ são escritos como **texto** (não número), preservando zeros à esquerda.
- Todo texto é escrito como string pura, nunca como fórmula: um nome de recebedor que
  comece com `=`, `+`, `-` ou `@` não pode ser interpretado como fórmula pelo Excel.
- Ordem das linhas: a ordem natural de retorno de `DocumentoRepository.listar_por_empresa`
  (a mesma da lista de documentos na tela).

## Arquitetura

Mesma separação em camadas do restante do projeto, com duas unidades independentes:

1. **Caso de uso `ExportarDocumentosUseCase`** — camada de aplicação, novo arquivo
   `backend/app/application/use_cases/exportacao_use_cases.py`. Recebe os repositórios já
   existentes (`DocumentoRepository`, `ExtracaoRepository`, `ClassificacaoRepository`,
   `ContaRepository`) e devolve uma lista de linhas de dados (`LinhaExportacao`, um
   dataclass com os 12 campos já tipados e com vazios normalizados). Não conhece Excel.
   Não exige nenhum método novo de repositório: filtra em memória sobre
   `listar_por_empresa`, o mesmo precedente do `ListarFilaRevisaoUseCase` da Fase 5.
2. **Gerador `.xlsx`** — camada de infraestrutura, novo arquivo
   `backend/app/infrastructure/spreadsheet/documentos_exporter.py`, ao lado dos módulos de
   importação existentes. Recebe `list[LinhaExportacao]` e devolve `bytes` do arquivo,
   usando `openpyxl`. Não conhece repositórios nem banco.

Dessa forma, "quais documentos e quais campos" é testável sem abrir Excel, e "como o
arquivo é montado" é testável sem banco.

## API

### `GET /empresas/{empresa_id}/documentos/exportar`

- **Resposta 200:** corpo binário `.xlsx`, `Content-Type:
  application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`,
  `Content-Disposition: attachment; filename="comprovantes_<cnpj>_<AAAA-MM-DD>.xlsx"`
  (CNPJ da empresa em dígitos + data da exportação).
- **Empresa inexistente:** 404, com o mesmo tratamento de `EmpresaNaoEncontrada` dos
  demais endpoints da empresa.
- **Empresa sem nenhum documento `CONCLUIDO`:** 200 com um `.xlsx` válido contendo apenas
  a linha de cabeçalho — nunca um erro.
- Nenhum arquivo é gravado em disco; a planilha é gerada em memória e devolvida na
  resposta.
- Não existe endpoint novo para o aviso de fila pendente: o frontend reaproveita
  `GET /empresas/{empresa_id}/documentos/fila-revisao` (Fase 5).

## Frontend

- **Botão "Exportar planilha"** na seção "Comprovantes" de `EmpresasPage.tsx`, ao lado de
  "Processar", visível sempre que uma empresa está selecionada, em qualquer aba. Fica
  desabilitado enquanto a exportação está em andamento, para evitar clique duplo.
- **Fluxo ao clicar:**
  1. Consulta `api.documentos.filaRevisao(empresaId)` apenas para contar pendências.
  2. Baixa o arquivo de `GET /empresas/{id}/documentos/exportar` como blob e dispara o
     download no navegador com o nome vindo do `Content-Disposition`.
  3. Se a fila tinha itens, exibe abaixo do botão: "N documento(s) ainda na fila de
     revisão — as linhas sem conta ficaram em branco na planilha." Se a fila estava
     vazia, nenhuma mensagem.
- **Erros:** se a consulta ou o download falharem, a mensagem de erro é exibida no mesmo
  lugar do aviso — nenhuma falha silenciosa (lição registrada na revisão final da Fase
  5).
- **Cliente da API:** novo método `api.documentos.exportar(empresaId)`. O helper
  `request()` atual assume resposta JSON, então este método usa `fetch` diretamente e lê
  o `Content-Disposition` da resposta para obter o nome do arquivo, devolvendo blob +
  nome.
- O aviso reflete a fila no instante da geração da planilha, pois a consulta é feita
  imediatamente antes do download.

## Casos de borda

- **Empresa sem documentos concluídos:** `.xlsx` só com cabeçalho, sem erro.
- **Documento concluído sem extração:** a linha sai apenas com o nome do arquivo e as
  demais colunas vazias; a exportação não quebra.
- **Conta deletada depois de classificar:** a classificação aponta para uma conta que não
  existe mais — colunas 10 e 11 saem vazias, sem erro 500 (mesmo tratamento já usado em
  `GET /documentos/{id}/resultado` e na fila de revisão da Fase 5). A coluna Origem
  permanece preenchida, pois a classificação ainda existe.
- **Texto livre começando com `=`/`+`/`-`/`@`:** escrito como string, nunca como fórmula.

## Testes

- **Unitário do caso de uso** (`Fake*Repository`): só `CONCLUIDO` entra; campos ausentes
  viram vazio; valor e data chegam tipados; conta deletada não quebra; filtra pela empresa
  correta; documento sem extração não quebra.
- **Unitário do gerador:** os bytes gerados são reabertos pelo `openpyxl`; cabeçalho na
  ordem exata das 12 colunas; valor e data são tipos nativos nas células; CPF/CNPJ com
  zero à esquerda permanece texto; texto começando com `=` permanece texto (não é
  fórmula).
- **Integração da API** (`TestClient`, `get_engine()` — nunca `create_engine()` cru, para
  manter o `PRAGMA foreign_keys=ON`): 404 para empresa inexistente; `.xlsx` válido com
  cabeçalhos corretos; `Content-Disposition` com o nome esperado; planilha só com
  cabeçalho quando não há documentos concluídos; documento `PENDENTE` não aparece.
- **Frontend:** verificação manual (o projeto não tem framework de teste de componente),
  incluindo o aviso de fila pendente e um download real do arquivo.

## Fora de escopo desta fase

- CSV ou qualquer outro formato além de `.xlsx`.
- Relatório em PDF. O roadmap original da Fase 0 citava "Relatórios PDF/Excel", mas o
  pedido concreto do usuário (Fase 4) foi uma planilha para importação em outro sistema,
  e esta fase entrega só isso. PDF não foi discutido e fica como possível evolução
  futura.
- Filtro por período, por status de classificação ou por origem.
- Múltiplas abas, totais, gráficos ou qualquer formatação além de cabeçalho legível.
- Exportação de regras, plano de contas ou histórico de aprendizado.
- Bloqueio da exportação por itens pendentes de revisão (apenas aviso).
- Persistência do arquivo gerado ou histórico de exportações.
