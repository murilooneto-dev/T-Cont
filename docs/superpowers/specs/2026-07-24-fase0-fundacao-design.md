# Fase 0 — Fundação — Design

Data: 2026-07-24
Status: Aprovado pelo usuário, aguardando plano de implementação

## Contexto

Este documento é o primeiro de uma série de specs para o sistema de classificação automática
de comprovantes de pagamento (OCR + IA + regras contábeis). O sistema completo foi decomposto
em fases independentes:

0. **Fundação** (este documento) — banco de dados, entidades, API FastAPI, frontend mínimo
1. Upload + Pipeline de OCR
2. Extração + Normalização de dados
3. Motor de Regras + Busca Semântica
4. Camada de IA + Aprendizado
5. Interface de revisão/edição
6. Relatórios (PDF/Excel)

Cada fase terá seu próprio ciclo design → plano → implementação.

## Decisões de contexto (fora do escopo técnico desta fase, mas que influenciam o design)

- **Custo**: projeto experimental, 100% gratuito/open-source. A camada de IA (Fase 4) usará
  Ollama local por padrão, desacoplada para permitir troca futura por API paga.
- **Autenticação**: nenhuma nesta fase. Uso único, local. Multiusuário/permissões ficam no
  roadmap de escalabilidade.
- **Ambiente**: execução local em Windows (backend FastAPI + frontend Vite via terminal),
  sem Docker nesta fase.
- **Banco**: SQLite nesta fase, com todas as decisões de schema compatíveis com PostgreSQL
  no futuro (tipos e constraints portáveis, uso de SQLAlchemy + Alembic).

## Objetivo da Fase 0

Entregar uma base testável de ponta a ponta: banco de dados completo (incluindo tabelas stub
das fases futuras), API REST completa para Empresas e Plano de Contas (CRUD + importação de
planilha com detecção automática de colunas), e uma tela mínima no frontend para cadastrar
empresa e importar/conferir o plano de contas. Upload de comprovantes ainda não processa nada
(isso é Fase 1).

## Arquitetura

Clean Architecture em camadas, separando entidades de domínio, casos de uso, infraestrutura
e API. Use cases dependem de interfaces de repositório (Repository Pattern), não de
implementações concretas — isso permite trocar SQLite por PostgreSQL sem tocar na lógica de
negócio, e testar use cases com repositórios fake/in-memory.

```
backend/
  app/
    domain/            # entidades puras (dataclasses/Pydantic), sem dependência de framework
    application/
      use_cases/        # ex: CriarEmpresa, ImportarPlanoContas
      dto/
    infrastructure/
      db/                # SQLAlchemy models, sessão, Alembic migrations
      repositories/      # implementações concretas dos repositórios
      spreadsheet/        # parser de planilha com detecção automática de colunas
    api/                 # FastAPI routers, request/response schemas (Pydantic)
    core/                # config, exceptions, logging
  tests/
  alembic/
frontend/
  src/
    pages/
    components/
    api/                 # client HTTP tipado
    types/
```

## Modelo de dados

Tabelas com lógica de negócio completa nesta fase:

- **empresas**: `id`, `razao_social`, `nome_fantasia`, `cnpj` (único), `ativo`, `created_at`,
  `updated_at`
- **planos_contas**: `id`, `empresa_id` (FK), `nome`, `versao`, `ativo`, `created_at`
- **contas**: `id`, `plano_conta_id` (FK), `codigo`, `descricao`, `natureza` (enum: `ATIVO`,
  `PASSIVO`, `RECEITA`, `DESPESA`, `PATRIMONIO_LIQUIDO`), `conta_analitica` (bool),
  `conta_pai_id` (FK autorreferente, nullable — suporta hierarquia)

Regra de domínio: apenas contas analíticas (folha da hierarquia) podem ser usadas em
lançamentos. Validado no domínio desde já, mesmo sem consumidor (IA) ainda.

Tabelas stub (schema criado via Alembic, sem use cases/endpoints ainda — apenas `id`,
`empresa_id` quando aplicável, e timestamps), para que fases futuras adicionem lógica sem
migrations quebradas:

- `documentos`, `ocr_resultados`, `extracoes`, `classificacoes`, `aprendizado`,
  `historico_alteracoes`, `usuarios`, `logs`, `configuracoes`

## Importação do Plano de Contas — detecção automática de colunas

- Usuário sobe `.xlsx`/`.csv` sem formato fixo pré-definido.
- Parser lê a primeira linha como cabeçalho e casa cada coluna com um campo esperado
  (`codigo`, `descricao`, `natureza`, `conta_analitica`, `conta_pai`) via dicionário de
  sinônimos (ex.: "código", "cod", "cod. conta", "account code" → `codigo`; "descrição",
  "nome da conta", "histórico" → `descricao`), com normalização (lowercase, sem acento) e
  fuzzy match como fallback.
- Campos obrigatórios: `codigo` e `descricao`. Se não forem identificados com confiança
  suficiente, a importação falha com mensagem clara listando as colunas encontradas —
  **nunca adivinha silenciosamente** (consistente com a regra geral do sistema de nunca
  inventar dado).
- Fluxo em dois passos:
  - `POST /planos-contas/{id}/import/preview` — recebe o arquivo, retorna o mapeamento de
    colunas detectado + amostra de linhas, sem gravar nada.
  - `POST /planos-contas/{id}/import/confirm` — confirma e grava a importação.

## API (Fase 0)

```
POST   /empresas
GET    /empresas
GET    /empresas/{id}
PUT    /empresas/{id}
DELETE /empresas/{id}                       (soft delete via campo ativo)

POST   /empresas/{id}/planos-contas
GET    /empresas/{id}/planos-contas
POST   /planos-contas/{id}/import/preview   (multipart file)
POST   /planos-contas/{id}/import/confirm
GET    /planos-contas/{id}/contas
POST   /planos-contas/{id}/contas           (CRUD manual pontual)
PUT    /contas/{id}
DELETE /contas/{id}
```

## Frontend mínimo

Uma página: CRUD de Empresa + dentro dela, upload da planilha do Plano de Contas com tela de
preview do mapeamento de colunas antes de confirmar, e listagem das contas importadas em
árvore (respeitando `conta_pai`).

## Testes

- Testes de unidade nos use cases com repositórios in-memory (sem banco real).
- Teste de integração do parser de planilha com 2-3 planilhas de exemplo (formatos diferentes
  de cabeçalho) para validar a detecção automática.
- Teste de integração da API via `TestClient` do FastAPI contra SQLite em memória.

## Fora de escopo (fica para fases futuras)

- Upload/processamento de comprovantes, OCR, extração, classificação, IA, aprendizado,
  relatórios — fases 1 a 6.
- Autenticação/multiusuário, Docker, deploy em servidor.
- Mapeamento manual de colunas na importação de planilha (só detecção automática nesta fase;
  se a detecção falhar, o usuário corrige a planilha e reenvia).
