# Arquitetura de Referência — Aplicações Analíticas sobre BigQuery com Controle de Acesso

Arquitetura de referência para uma **classe de aplicações** do Escritório Municipal de
Dados:

> Dados que residem no **BigQuery** (marts mantidos por dbt) precisam ser servidos a uma
> aplicação **web (frontend + backend)** de natureza **analítica** (filtros, agregações,
> dashboards, busca facetada), com **controle de acesso por linha/atributo** por usuário.

O objetivo é descrever um desenho reutilizável por **N aplicações** desse tipo. Ele é
**agnóstico de linguagem e framework**; a implementação de referência é TypeScript, mas
Python e Go seguem o mesmo desenho.

> **padrão**; um exemplo aplicado aparece no Apêndice A.

---

## 1. O problema que esta arquitetura resolve

Aplicações analíticas costumam nascer lendo direto do data warehouse. Isso funciona no
protótipo e degrada em produção:

- **Custo e latência por request:** cada consulta varre/fatura o warehouse; a latência fica
  refém do BQ e da contenção de slots.
- **Anti-padrão de carregar tudo em memória:** para filtrar/paginar, a app baixa o dataset
  inteiro e processa em RAM. Não escala com linhas nem com usuários.
- **Sem filtragem eficiente por linha:** controle de acesso aplicado em memória, depois da
  leitura, é caro e arriscado.
- **Schema implícito:** o "contrato" dos dados é o schema do warehouse, que muda sem
  versionamento do lado da app.

O padrão separa **warehouse analítico (BQ, batch, dono: dbt)** de **banco de serviço
(baixa latência, dono: a app)**, com um **job de sincronização** entre eles, e move
filtros/agregações/controle de acesso para **queries no banco de serviço**.

### Dimensionamento (importante para não super-projetar)

"Afetar milhões de pessoas" precisa ser destrinchado: **milhões de cidadãos nos dados** ≠
**milhões de usuários concorrentes**. Estas são ferramentas internas de governo:

- **Dados:** alguns milhões de linhas por tabela — "pequeno" para PostgreSQL bem indexado.
- **Usuários concorrentes:** centenas a poucos milhares de servidores.
- **Gargalo real:** latência por request + filtragem por linha + agregação; não throughput
  massivo.

As escolhas abaixo otimizam para esse perfil. Apps com perfil materialmente diferente
(p.ex. dezenas de milhares de requests concorrentes, ou centenas de milhões de linhas com
agregação pesada) têm escape hatches indicados ao longo do texto.

## 2. Princípios

1. **Separar warehouse de banco de serviço.** BQ é a fonte analítica; a app serve a partir
   de um banco transacional indexado.
2. **Empurrar trabalho para o banco.** Filtros, paginação, agregação e controle de acesso
   acontecem em SQL, não em memória da aplicação.
3. **Contrato explícito e neutro de linguagem.** A fronteira frontend↔backend é um
   **OpenAPI** versionado, permitindo trocar a linguagem do backend.
4. **Controle de acesso como módulo de primeira classe.** "Quem vê o quê" vive em um único
   módulo, isolado e exaustivamente testado.
5. **Deployables independentes.** Frontend, API, sync e infra evoluem e implantam à parte.
6. **Auth delegada ao IdP corporativo.** A identidade vem de um IdP (OIDC); a app não
   gerencia credenciais.
7. **Propriedade de schema pela aplicação.** As migrations da app são donas do DDL de
   `serving`; o sync só escreve dados nas colunas que a app declarou. Evolução tolerante a
   drift, promoção explícita por PR.

## 3. Visão geral

```
┌────────────┐    sessão (cookies)    ┌──────────────────────────────┐
│  Browser   │ ◄────────────────────► │  Frontend + BFF              │
└────────────┘                        │  - sessão (OIDC client)      │
                                      │  - proxy /api/* → backend     │
                                      └──────────────┬───────────────┘
                                                     │  Bearer JWT (IdP)
                                                     ▼
                                      ┌──────────────────────────────┐
                                      │  API (serviço standalone)     │
                                      │  contrato: OpenAPI            │
                                      │  routes → services → repos    │
                                      │  + módulo de controle de acesso│
                                      └──────────────┬───────────────┘
                                                     │  SQL (via PgBouncer)
                                                     ▼
                                      ┌──────────────────────────────┐
                                      │  Banco de serviço (Cloud SQL) │
                                      │  schema `serving` (app é dona)│
                                      │  + materialized views          │
                                      └──────────────▲───────────────┘
                                                     │  sync BQ → serving (ver §8:
                                                     │  Opção A Prefect | Opção B Airbyte)
                                      ┌──────────────┴───────────────┐
                                      │  BigQuery (marts dbt)         │
                                      │  modelos PLANOS, sob medida   │
                                      └───────────────────────────────┘
```

| Deployable | Responsabilidade | Time dono |
|---|---|---|
| `frontend` | UI + BFF (proxy autenticado) + sessão (OIDC) | app-eng |
| `api` | Regras de negócio + controle de acesso + acesso a dados | app-eng |
| `migrations` | DDL/índices de `serving` e `app` (versionado) | app-eng |
| `sync` | Carrega BQ → `serving` (ver §8: Prefect ou Airbyte) | app-eng / plataforma |
| `infra` | Banco de serviço + conectividade + secrets | plataforma |

Fronteira de propriedade: o **schema `serving`**. As **migrations da app** definem seu DDL
(colunas, índices, MVs); o **sync** só escreve dados nas colunas que a app declarou. O dbt
permanece exclusivo do BigQuery (datalake) — nunca toca no Postgres.

## 4. Store de serviço — PostgreSQL (Cloud SQL por padrão)

- **Cloud SQL (PostgreSQL)** como padrão: Postgres gerenciado (HA, backups, read replicas),
  suficiente para o perfil destas apps (alguns milhões de linhas, centenas a poucos milhares
  de usuários). Bem indexado, dá conta dos filtros, paginação e agregações de dashboard.
- Para agregações pesadas, **empurrar o custo para materialized views** (refrescadas pelo
  sync) em vez de depender de engine colunar.
- **ClickHouse** = escape hatch: só quando uma app estoura de verdade em volume/agregação
  (centenas de milhões de linhas, alta concorrência analítica). Não justifica a
  complexidade operacional no caso comum.
- **Pooling de conexões (PgBouncer)** é obrigatório: a API escala horizontalmente (muitos
  pods), e cada pod multiplicaria conexões sem o pooler.

## 5. Camadas da API

A arquitetura define **camadas com contratos claros** (não pastas). Regra de ouro:

> **SQL só na camada de repositório. Regra de negócio na camada de serviço. HTTP/validação
> na camada de rota. Controle de acesso é um módulo isolado e testável.**

```
route/handler   → valida entrada (contrato), extrai contexto do usuário, traduz erros
service         → regra de negócio; orquestra acesso + repositórios; não conhece HTTP/SQL
access-control  → traduz permissões do usuário em predicados/agregações; único decisor
repository      → todas as queries SQL; retorna dados tipados, sem regra de negócio
db/migrations   → schema versionado, índices, materialized views
```

Transversais: **config validada**, **logger estruturado**, **observabilidade**
(health/ready, métricas, tracing), **erros padronizados** (problem+json, sem vazar internals).

### Notas por linguagem

- **TypeScript (referência):** Hono (rotas) · Drizzle (repos/migrations) · Zod (validação derivada do OpenAPI).
- **Python:** FastAPI · SQLAlchemy Core/SQLModel + Alembic · Pydantic gerado do OpenAPI.
- **Go:** chi/echo · sqlc/pgx + goose/golang-migrate · structs via `oapi-codegen`.

## 6. Contrato — OpenAPI como fonte da verdade

Para permitir backends poliglotas servindo o mesmo frontend, o contrato **não** pode ser
tipos de uma linguagem. A fonte da verdade é um **`openapi.yaml` versionado**, revisado em PR.

```
openapi.yaml  (fonte da verdade)
   ├─► frontend: client + tipos        (openapi-typescript)
   ├─► backend TS: tipos/validadores    (zod / openapi-fetch)
   ├─► backend Python: modelos          (datamodel-code-generator → Pydantic)
   └─► backend Go: structs/handlers     (oapi-codegen)
```

Regras: mudança de contrato = mudança no spec (PR); o frontend não importa tipos do
backend; versionamento por path (`/v1`, `/v2`); teste de contrato valida a implementação.

## 7. Controle de acesso (modelo genérico)

A parte mais crítica e a que mais se repete. Modelo: **row-level security baseado em
concessões (grants)**. Um **sujeito** (usuário) possui concessões sobre uma ou mais
**dimensões de acesso** (unidade organizacional, geografia, categoria). A visibilidade
deriva dessas concessões.

Cinco tipos de escopo, que cobrem a maioria das apps:

| Escopo | O que controla | Tradução em SQL |
|---|---|---|
| **Linha** | Quais registros o usuário enxerga | `WHERE dim IN (grants)` (OR/AND entre dimensões) |
| **Atributo** | Quais colunas/campos retornam (ex.: PII mascarada) | Projeção condicional / mascaramento |
| **Sub-recurso** | Coleções aninhadas (ex.: itens de categoria permitida) | `JOIN`/`WHERE` na tabela filha (formato LONG) |
| **Agregado** | Métricas refletem só a fatia visível | `COUNT(*) FILTER (...)`, `GROUP BY` recalculados |
| **Delegação** | Admins gerenciam um subconjunto de sujeitos/concessões | Predicado de "subconjunto" sobre os grants do admin |

Design:

- Módulo `access-control` com **funções puras** (ex.: `buildRowPredicate(subject)`,
  `buildScopedAggregation(subject)`). Nenhuma rota/repositório decide acesso por conta própria.
- **Negar por padrão.** Ausência de concessão → sem acesso.
- **Matriz de testes obrigatória:** `papéis × dimensões × combinações de concessões`,
  validando linha, atributo, sub-recurso, agregado e delegação.
- Recursos baseados em pré-agregação (dashboards) podem ter regras simplificadas (ex.:
  liberados só a perfis com visão total) — decisão explícita por app.

## 8. Sincronização BigQuery → Banco de serviço

A fonte é **sempre o BigQuery** (o datalake) — toda app passa por lá antes de servir. Há
**duas formas válidas** de levar BQ → banco de serviço; ambas mantêm o **dbt exclusivo no
BQ** e a **app dona do contrato (`serving`)**, e diferem em quem faz a extração/carga:

- **Opção A — Motor genérico no Prefect:** código próprio, code-first, BQ → `serving` direto
  (sem camada intermediária). Maestro: Prefect.
- **Opção B — Airbyte em duas camadas:** ferramenta gerenciada faz BQ → `raw`; a app faz um
  transform fino `raw` → `serving`. Maestro: Airbyte (EL) + app (transform).

A escolha é discutida em **§8.3**. As duas convivem com o resto da arquitetura sem mudar
nada (controle de acesso, OpenAPI, camadas, auth).

### 8.1 Opção A — Motor genérico no Prefect

Uma fonte única e homogênea permite um **motor de sync genérico, dirigido por manifesto**, que
copia BQ → `serving` direto, sem camada `raw` intermediária.

```
BQ (dbt, datalake): modelos PLANOS, sob medida para o sync
   │  motor de sync genérico (flow Prefect) — 1 codebase para todas as apps
   │    ├─ lê o manifesto da app
   │    ├─ introspecta a `serving` (descobre colunas/PK)
   │    ├─ casa colunas POR NOME: existe na `serving` → grava; resto → política da tabela
   │    ├─ incremental (cursor) ou full-refresh, por tabela
   │    └─ idempotente; watermark em `sync_runs`
   ▼
schema `serving`   ← APP é dona do DDL (migrations): colunas, ÍNDICES, MVs
```

**Pontos fortes desta opção:**

- **Sem camada `raw` / sem 2N.** BQ → `serving` direto; nada duplicado no Postgres.
- **Nº de tabelas não ameaça.** PIC ~10 tabelas, outras apps muito mais — só **mais linhas no
  manifesto**. O motor itera tabelas e o **Prefect paraleliza**. Escala linear, mesmo motor.
- **Nesting resolvido no dbt.** Os modelos que alimentam o sync são feitos **planos, sob
  medida**; o motor nunca vê struct/array aninhado — sem flattening no sync.
- **Uma pipeline, um agendador, code-first.** Casa com a cultura do dbt; sem segundo sistema.
- **App dona do DDL.** Schema governado pela aplicação (migrations), `serving` blindada do
  churn do warehouse.

Custo: você **escreve e mantém o código de extração** (BQ→PG, tipagem, incremental, deleção).

### O motor (superfície pequena, declarativa)

Como a fonte é uma só, o destino é um só e o nesting saiu (dbt), o motor é enxuto:

- **Sem framework de conectores:** um source (BQ Storage Read API), um sink (PG `COPY`/upsert).
- **Sem detecção de schema:** **introspecta a `serving`** e casa colunas **por nome**. O que
  a app não declarou segue a política da tabela (ver abaixo).
- **Incremental:** `SELECT … WHERE cursor > :watermark` → upsert por PK → grava novo watermark.
- **Full-refresh:** carrega num staging **transitório do run** → `DELETE+INSERT` na mesma
  transação (MVCC-safe, índices preservados, sem lock de leitura) → dropa o staging. O staging
  é por-run, **não** é um schema `raw` permanente.

### Manifesto (por app, no repo da app, ao lado das migrations)

```yaml
tables:
  - source: marts.participantes_serving   # modelo dbt plano
    target: serving.participants
    mode: incremental
    cursor: updated_at
    primary_key: [cpf]
    on_unknown: ignore          # estrito (default): descarta coluna não declarada
    on_delete: ignore           # default; ver opções abaixo

  - source: marts.indicador_novo          # tabela em exploração (piloto)
    target: serving.indicador_novo
    mode: full_refresh
    on_unknown: extra           # joga coluna desconhecida num `extra` JSONB
```

Repare: **sem lista de colunas.** O motor casa por nome contra a `serving`. Adicionar coluna
= **só a migration**; o motor passa a populá-la no próximo run. O manifesto fica estável.

### Política de coluna desconhecida (`on_unknown`)

Para uma coluna que existe na fonte mas não na `serving`:

- **`ignore` (default):** descarta. Contrato 100% explícito; app blindada do churn do
  warehouse. Para usar a coluna, abre-se PR com migration.
- **`extra`:** despeja as colunas não-mapeadas num `extra JSONB` da tabela. Consultável via
  `extra->>'col'` **na hora, sem migration** — bom para **exploração no piloto**. Sem tipo
  nem índice nativo (dá para índice de expressão como atalho interino).

Casa com a trajetória piloto→estável: tabelas exploratórias usam `extra`; tabelas de contrato
usam `ignore`.

### Política de deleção (`on_delete`)

Incremental por cursor pega insert/update, não deleção (linha some na fonte). Opções:

- **`ignore` (default):** append/update-only (a fonte não deleta).
- **`soft`:** o modelo dbt expõe `deleted_at`/`is_deleted` e o upsert reflete.
- **`reconcile`:** full-refresh periódico nas tabelas onde deleção importa.

### Evolução de schema (drift → promoção)

`serving` tem **um único dono de DDL: as migrations da app**. O motor só escreve dados.

1. **Land** — dbt adiciona a coluna no modelo plano.
2. **No-op seguro** — o motor introspecta a `serving`, não acha a coluna → segue `on_unknown`
   (descarta, ou guarda em `extra` se a tabela optou). Nada quebra.
3. **Triage** — drift check (o próprio motor diffa fonte vs `serving`) **alerta** "coluna X
   disponível".
4. **Promote** (PR na app): migration `ADD COLUMN x` + índice; o motor passa a popular `x`
   (sai do `extra`); adiciona ao OpenAPI se virar filtro/sort/campo; **backfill = re-rodar o
   sync** (o dado já está no BQ).

Como os índices vivem só em `serving` (migrations), nada externo os derruba. **Exceção de
segurança:** campo que pode afetar controle de acesso não pode dormir no `extra` — o drift
check trata como alta prioridade e a promoção é imediata. O drift também detecta **remoção**
de campo na fonte.

### Acionamento

O motor é orquestrado **pelo Prefect**, downstream da pipeline de modelos do dbt:

- **Agendado:** scheduler do Prefect (freshness logo após os modelos ficarem prontos).
- **Manual via API:** botão no admin da app → chama a **API do Prefect** para disparar o run.
- **Manual via UI:** roda o flow direto na **UI do Prefect**.

### 8.2 Opção B — Airbyte em duas camadas (`raw` + `serving`)

Usa o **Airbyte (OSS, self-managed)** para o EL e deixa o app dono de um transform fino. Como
full-refresh do Airbyte recria tabelas (e o Airbyte não cria os índices de query da app), a
camada que a API lê **precisa** ser separada da que o Airbyte escreve.

```
BQ (dbt, modelos planos)
   │  Airbyte (EL + tipagem + propagação de schema), incremental ou full-refresh
   ▼
schema `raw`        ← Airbyte é DONO; espelha o BQ; pode recriar/truncar à vontade
   │  transform fino da APP (SQL: INSERT SELECT / MERGE + REFRESH MV), pós-sync
   ▼
schema `serving`    ← APP é dona (migrations): colunas, ÍNDICES, MVs   ── API só LÊ
```

**Três schemas, dois donos:**

| Schema | Dono | Quem escreve | Papel |
|---|---|---|---|
| `raw` | Airbyte | Airbyte | espelho cru do BQ; sem índices de query |
| `serving` | app (migrations) | transform da app | camada indexada read-only; API lê |
| `app` | app (migrations) | API (CRUD) | estado OLTP (users, grants, audit); Airbyte nunca toca |

**Por que duas camadas (e não consumir o Airbyte direto):** o Airbyte **não cria os índices
de query** da app, e **full-refresh recria a tabela** — então índice criado por cima morreria.
Mantendo os índices/MVs numa `serving` própria, eles ficam a salvo do ciclo de vida do `raw`.

**Coluna nova vinda do dbt — o que o Airbyte faz:** adicionar coluna é mudança *não-destrutiva*.
Por conexão, o Airbyte tem uma **política de propagação** (detecta no *schema discovery*
periódico ou no "Refresh source schema"):

- **Propagar (recomendado para `raw`):** faz `ALTER TABLE ADD COLUMN` no `raw` (preserva
  índices do `raw`, se houver). Colunas antigas ficam `NULL` até re-sync/backfill.
- **Aprovação manual / ignorar:** detecta e notifica; só aplica quando aprovado na UI.

**Portão do contrato fica no `serving`, não no Airbyte:** deixe o Airbyte **propagar livremente
para o `raw`** (raw = espelho fiel do BQ). O **transform da app** é o portão real: casa colunas
por nome (`serving` declarada → grava; resto → ignora ou `extra` JSONB). Promover coluna =
**PR de migration na app** — contrato versionado no repo, mesmo sendo o mesmo time.

**Quem dispara o transform `raw`→`serving`:** o **app** (tira o Prefect do hop):

- **Botão** (endpoint admin) — sempre presente, cobre exploração e ad-hoc.
- **Webhook pós-sync do Airbyte → endpoint do app** — recomendado para automação: dispara
  exatamente quando o `raw` fica fresco.
- **TTL/cron** (`pg_cron` ou k8s CronJob) — fallback simples, porém cego ao sync.

As `serving` base são **tabelas** (robustas ao full-refresh do `raw`); **MVs só sobre
`serving`** (nunca direto sobre `raw`, para não acoplar ao ciclo de vida do Airbyte),
refrescadas (`CONCURRENTLY`) no mesmo transform.

**Deleção:** a fonte não é CDC → **full-refresh** (manual, ou default em algumas tabelas)
reconcilia deleções nessas tabelas.

**Pontos fortes desta opção:** não escreve código de extração (Airbyte cobre BQ→`raw`, tipagem,
incremental, propagação); UI/scheduler/retries prontos. **Custo:** camada `raw` (2N), operar o
Airbyte, e ainda manter o transform fino.

### 8.3 Como escolher

| Critério | A — Prefect (motor genérico) | B — Airbyte (duas camadas) |
|---|---|---|
| Camadas no Postgres | 1 (`serving`) | 2 (`raw` + `serving`) |
| Código que você mantém | o motor de extração | só o transform fino |
| Ferramenta extra a operar | não (só Prefect) | sim (Airbyte OSS) |
| Tipagem BQ→PG | sua (controle fino) | do Airbyte |
| Maestro | Prefect | Airbyte (EL) + app (transform) |
| Melhor quando | quer mínimo de peças e controle total | quer reaproveitar o Airbyte já operado |
| Escape hatch comum | fontes não-BQ → reavaliar | — |

Em ambas: dbt fica no BQ; `serving` é da app e indexada; contrato promovido por **PR de
migration**; deleção por full-refresh (sem CDC).

### 8.4 DX local (vale para as duas)

- App local aponta para um **Postgres dev compartilhado** (na tailnet) populado pelo sync —
  menor delta do fluxo atual (hoje a app local já fala com o BQ pela rede; troca-se por um
  Postgres mais rápido e barato). Refresh sob demanda = disparar o sync (flow Prefect, ou
  Airbyte UI + transform).
- Alternativa offline: **seed/snapshot** de `serving` para subir o banco local em segundos.
- Loop de exploração ≈ o de hoje: mexe no dbt → roda o sync → coluna aparece (em coluna
  declarada, ou no `extra` se a tabela optou) → consome.

## 9. Agregações e dashboards

- **Indicadores correntes** (totais, percentuais): dinâmicos; baratos com índices adequados.
- **Séries históricas e métricas pesadas:** **materialized views** refrescadas pelo sync —
  evita recomputar tudo on-the-fly por request sob controle de acesso.
- Para cada app, **mapear cada métrica → fonte** (tabela ou MV) antes de implementar o
  dashboard. Esse mapa é pré-requisito.

## 10. Autenticação

- **IdP corporativo (OIDC) é a fonte de identidade** (ex.: Keycloak/govbr). O login não é
  reimplementado pela app.
- **Sessão no frontend:** cliente OIDC (ex.: Better Auth) com tokens em cookies httpOnly.
- **API stateless:** valida o JWT (JWKS + audience + issuer). A API não conhece a camada de
  sessão — só o token.
- Ao introduzir uma nova camada de sessão durante migração, tratá-la como **fase isolada,
  antes** das mudanças de dados, exigindo paridade com o fluxo anterior.

## 11. Migração e cutover (quando aplicável)

Como o controle de acesso é crítico de segurança, o corte não deve ser "big bang":

1. Backend novo sobe lendo do banco de serviço, **sem tráfego de usuário**.
2. Camada de shadow (no proxy ou via script) replica requests reais aos dois backends e faz
   **diff das respostas**, com foco em listagens por usuário (cada perfil de acesso),
   números agregados e telas administrativas.
3. **Cutover por endpoint**, só quando o diff zera e estabiliza.
4. Rollback = trocar a variável de ambiente/rota no proxy do frontend.

## 12. Observabilidade e operação

- **Health/Readiness** separados (liveness simples; readiness checa o banco).
- **Logs estruturados** (JSON) com correlação por request-id; sem ruído de debug em prod.
- **Métricas** (latência por endpoint, erros, duração/linhas do sync, freshness por tabela) e **tracing** (OpenTelemetry).
- **Config validada na inicialização** — a app falha rápido se faltar env.
- **Erros padronizados** (problem+json); nunca vazar stack traces ou dados internos.

---

# Implementação de referência (TypeScript)

Materialização do desenho acima, recomendada quando o frontend já é Next.js/TS. É o ponto
de partida padrão, não uma obrigação.

| Camada | Tecnologia |
|---|---|
| Runtime | Node.js (LTS) |
| HTTP | **Hono** |
| Dados | **Drizzle** (schema + migrations + query-builder) |
| Validação | **Zod**, derivada do `openapi.yaml` |
| Sessão (frontend) | **Better Auth** sobre o IdP |
| JWT (API) | `jose` (JWKS) |
| Banco | Cloud SQL (PostgreSQL) + PgBouncer |
| Sync | **Opção A:** motor genérico (flow **Prefect**) · **Opção B:** **Airbyte** (`raw`) + transform da app (ver §8) |
| Schema do sync | Migrations **Drizzle** (dona da `serving`); na Opção A, manifesto YAML no repo |

### Por que Drizzle e não Prisma

- **Queries analíticas/dinâmicas** (GROUP BY, `FILTER`, window functions, facetas, WHERE
  dinâmico) são o coração da app; a API do Prisma é fraca nisso e empurra para `$queryRaw`,
  **perdendo o type-safety** que justifica o ORM. Drizzle compõe SQL dinâmico tipado.
- **Carga em massa** é via `COPY` (não Prisma); o `createMany` é linha-a-linha.
- **DDL perto do metal:** índices GIN/trigram, parciais, em expressão JSONB, materialized
  views, extensões — nativos no Drizzle; `Unsupported`/SQL cru no Prisma.
- **Runtime/pooling:** Drizzle é camada fina sobre o driver `pg`, conversa melhor com
  PgBouncer; o query engine do Prisma adiciona peso e cuidado extra.

Prisma brilha em CRUD/DX de migrations, mas traria duas ferramentas ou muito `$queryRaw`.
Drizzle cobre tudo com menos compromissos.

### Estrutura

```
src/
  routes/         # handlers Hono: validação + contexto + chamada ao service
  services/       # regra de negócio
  access-control/ # buildRowPredicate, buildScopedAggregation (+ testes)
  repositories/   # queries Drizzle, materialized views
  db/             # schema, migrations, client
  auth/           # verificação de JWT (JWKS), contexto do usuário
  config/         # env validada com Zod
  observability/  # logger, métricas, tracing, health
  contracts/      # tipos gerados a partir do openapi.yaml
openapi.yaml
```

Pontos de implementação:

- Middleware injeta contexto do usuário (`{ user, permissions }`) tipado, após validar o JWT.
- Tabela de usuários/concessões costuma ser pequena → cache em memória por pod com
  invalidação na escrita, dispensando Redis na maioria dos casos.
- **Busca facetada / filtros em cascata** (recalcular opções conforme os demais filtros) e
  **multi-select com AND** são, em geral, metade do esforço da listagem — tratar como
  subdesign próprio na repository.

### Equivalentes em outros backends

- **Python (FastAPI):** routers · SQLAlchemy/SQLModel + Alembic · Pydantic do OpenAPI ·
  JWT `pyjwt`/`python-jose` + JWKS · módulo `access-control` com funções puras.
- **Go:** chi/echo · sqlc/pgx + goose · `oapi-codegen` · `go-oidc` + JWKS · pacote
  `accesscontrol` com testes table-driven.

Inegociáveis em qualquer linguagem: o **contrato OpenAPI** e o **módulo de controle de
acesso isolado e testado**.

---

# Apêndice A — Exemplo aplicado (PIC)

Instanciação concreta na aplicação PIC (Pequenos Cariocas):

- **Dimensões de acesso (escopo de linha):** equipamentos por tipo — `cras`, `escola`,
  `cre`, `ap`, `cas`, `clinica_familia`, `equipe_familia`. Visibilidade = OR entre os tipos.
- **Escopo de sub-recurso + agregado:** `secretaria_acesso` (TODOS/SME/SMS/SMAS/NULL) filtra
  quais protocolos (tabela filha em formato LONG) o usuário vê e **recalcula** contadores,
  frações e situação.
- **Escopo de atributo:** colunas sensíveis (ex.: latitude/longitude) só para visão total.
- **Delegação:** admin segmentado só gerencia usuários cujas concessões são subconjunto das
  dele e de secretaria compatível.
- **Dashboard:** liberado apenas para `secretaria_acesso = TODOS`; métricas históricas via
  materialized views.
- **Entidades:** `participants` (1 linha/pessoa), `participant_protocols` (LONG),
  `monthly_results` (LONG), `geo_layers`, `users` (+ concessões, app-owned).

# Apêndice B — Riscos recorrentes neste tipo de migração

| Risco | Severidade | Mitigação |
|---|---|---|
| Tradução do controle de acesso (memória → SQL) | Alta | Módulo isolado + matriz de testes + parallel-run com diff |
| Mapeamento métricas do dashboard → fonte no banco | Média | Fechar o mapa antes de implementar o dashboard |
| Busca facetada / filtros em cascata / multi-select AND | Média | Subdesign próprio na repository; testes de faceta |
| Nova camada de sessão no caminho crítico | Média | Fase isolada, antes dos dados, com paridade exigida |
| Volume/custo do sync | Baixa-Média | Incremental por cursor + upsert; full-refresh só onde precisa; paralelizar tabelas |
| Drift de schema vindo do warehouse | Baixa | Contrato no `serving` (migration); `on_unknown` (`ignore`/`extra`) + drift check (prioriza campo sensível a acesso) |
| Full-refresh do Airbyte derrubar índices (Opção B) | Média | Índices/MVs só no `serving` (app); Airbyte toca só `raw` |
