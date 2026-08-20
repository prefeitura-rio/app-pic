# Plano: migração de controle de acessos (v2) para a nova infra de dados

Escopo deste plano: **apenas o controle de acessos/governança (RLS)** do app-pic v2,
migrando a fonte de verdade de usuários/permissões do BigQuery (`endpoint_data_access`)
para um Postgres dedicado ao app-pic, com o `data-proxy` (PostgREST + pg_duckdb)
enforçando RLS sobre os dados de participantes.

Fora de escopo (não mexer): v1 (`src/api/v1/`), que continua apontando pro BigQuery
como está hoje (vira backup); migração do read-path de participantes/dashboard/
geospatial/debug da v2 para o data-proxy.

---

## 1. Por que migrar

- Hoje `src/pic/infrastructure/repositories/bigquery_admin.py` lê/escreve permissões
  direto em uma tabela BigQuery (`endpoint_data_access`), usando SQL montado por
  concatenação de string (frágil, sem transação real, sem FK/constraint).
- O `data-proxy` já expõe `rls.access_policy` (Postgres real, PostgREST) como o
  mecanismo padrão de RLS pra qualquer schema/dataset novo migrado pra ele. Times que
  migram pro data-proxy devem usar esse mecanismo pra controle de acesso.
- `data-proxy` é uma infra **efêmera**: fora da própria `access_policy` (que tem
  backup), o resto do dataset é uma read-replica reconstruível a partir de manifests,
  sem garantias de HA de escrita. Não é lugar pra guardar estado de negócio de longo
  prazo (identidade de usuário, notas, auditoria).
- Por isso: identidade/metadados de usuário passam a morar em um **Postgres separado,
  próprio do app-pic** (projeto GCP `rj-iplanrio-dia`), e só o necessário pro RLS é
  espelhado no `access_policy` do data-proxy.

---

## 2. Arquitetura

```
                    ┌─────────────────────────────┐
                    │   app-pic backend (v2)       │
                    │                               │
   Admin UI ───────►│  IAdminRepository             │
                    │   (HybridAdminRepository)     │
                    └───────────┬───────────────────┘
                                │
                 ┌──────────────┴───────────────┐
                 │ escrita: data-proxy PRIMEIRO  │
                 │ leitura: só Postgres local     │
                 ▼                                ▼
     ┌───────────────────────┐      ┌─────────────────────────────┐
     │ data-proxy (efêmero)   │      │ Postgres app-pic (fonte da   │
     │ rls.access_policy      │◄─────┤ verdade, com backup real)    │
     │ (só grants, via        │ sync │  - tabela `users`             │
     │  PostgREST HTTP)       │      │  - tabela `policy` (espelho)  │
     └───────────────────────┘      └─────────────────────────────┘
                 │
                 ▼
     RLS sobre endpoint_participante_listagem / _visao_geral
     (enforced pelo Postgres do data-proxy, via policy_writer role)
```

Princípios:

1. **Postgres local do app-pic é a fonte da verdade** para identidade de usuário e
   para o estado de acesso do ponto de vista administrativo (auditoria, quem mudou o
   quê). `access_policy` no data-proxy é só o espelho que o RLS de fato lê.
2. **Toda escrita de acesso vai para o data-proxy primeiro.** Só gravamos localmente
   depois de confirmar sucesso no PostgREST. Se o data-proxy falhar, a escrita local
   não acontece e o erro sobe pro admin — nunca deixamos o banco local "prometer" um
   estado de acesso que o RLS ainda não está de fato aplicando.
3. **Toda leitura do painel admin vem só do Postgres local** (JOIN `users` + `policy`).
   O painel não depende do data-proxy estar no ar para listar/filtrar usuários.
4. Campos que são **puramente identidade** (nome, email, ocupação, secretaria, notes,
   `is_admin`/`is_super_admin`/`active` do app) nunca vão para o data-proxy — gravam
   direto em `users`, sem gate.

---

## 3. Modelo de dados

### 3.1 `users` (Postgres local — identidade + regras de negócio do app)

```sql
CREATE TABLE users (
  cpf             text PRIMARY KEY,
  nome            text,
  email           text,
  ocupacao        text,
  secretaria      text,                         -- lotação
  is_admin        boolean NOT NULL DEFAULT false, -- "admin comum": gerencia só um subconjunto
                                                    -- de usuários (cujas unidades são
                                                    -- subconjunto das próprias). Regra 100%
                                                    -- do app, validada no backend. NUNCA
                                                    -- é enviada ao data-proxy.
  is_super_admin  boolean NOT NULL DEFAULT false, -- gerencia todos os usuários E enxerga
                                                    -- todos os dados. Mapeia 1:1 para
                                                    -- `is_admin=true` na linha base do
                                                    -- data-proxy.
  active          boolean NOT NULL DEFAULT true,  -- soft delete da conta inteira; mapeia
                                                    -- para `is_enabled=false` em TODAS as
                                                    -- linhas do subject na `policy`.
  notes           text,
  created_by      text,
  updated_by      text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);
```

### 3.2 `policy` (Postgres local — espelho 1:1 do `rls.access_policy` do data-proxy)

Só existe pra guardar, localmente, exatamente o que foi confirmado como escrito no
data-proxy (fonte de verdade para consulta rápida/local; nunca é escrita direto sem
antes confirmar no data-proxy).

```sql
CREATE TABLE policy (
  id          bigserial PRIMARY KEY,
  schema      text NOT NULL,                  -- 'app_pequenos_cariocas'
  subject     text NOT NULL,                  -- cpf
  is_admin    boolean NOT NULL DEFAULT false, -- true só na linha base do super_admin
  is_enabled  boolean NOT NULL DEFAULT true,
  unit_type   text,                           -- NULL = linha "base" (identidade/super_admin)
  unit_id     text,                           -- valores possíveis: cras, escola, cre, ap,
                                               -- cas, clinica_familia, equipe_familia,
                                               -- secretaria (este último com unit_id em
                                               -- {SME, SMS, SMAS})
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  synced_at   timestamptz,                    -- carimbo do último write confirmado no
                                               -- data-proxy
  UNIQUE (schema, subject, unit_type, unit_id)
);
```

Não guardamos `metadata` aqui — decidimos não usar o `metadata` jsonb do data-proxy
para nada (nem espelhar localmente), já que toda identidade mora em `users`.

### 3.3 `rls.access_policy` (data-proxy — já implementado pelo Pedro, fora do nosso repo)

Referência (schema real, commit `81324d7` do repo `data-proxy`):

```sql
rls.access_policy(
  schema, subject,
  is_admin,      -- boolean, default false
  is_enabled,    -- boolean, default true
  unit_type, unit_id,
  metadata       -- jsonb NOT NULL DEFAULT '{}' — não usamos, fica sempre '{}'
)
```

- `policy_writer_<schema>` só tem `SELECT, INSERT, UPDATE` — **sem DELETE**. Revogar é
  sempre `PATCH is_enabled=false`.
- Unique key: `(schema, subject, unit_type, unit_id)`.

---

## 4. Semântica de acesso confirmada

Verificado diretamente no repo `data-proxy` local (`src/dp/sql/pg/access_policy_check.sql`,
`src/dp/loading.py::unit_predicate`, `docs/security.md`, histórico de commits):

```sql
EXISTS (
  SELECT 1 FROM rls.access_policy p
  WHERE p.schema = :schema
    AND p.subject = :subject
    AND p.is_enabled
    AND (p.is_admin OR (p.unit_type = 'cras' AND p.unit_id = target.id_cras) OR ...)
)
```

- `is_admin=true` em **qualquer** linha do subject dá acesso irrestrito a toda a
  tabela — o `OR` de SQL faz curto-circuito, então `unit_type`/`unit_id` daquela mesma
  linha são ignorados nesse caso (confirmado: não existe nenhum mecanismo no data-proxy
  que restrinja `is_admin=true` por unidade, apesar de uma afirmação em contrário do
  Pedro — vale realinhar com ele, mas não muda nosso design).
- Por isso: **nunca** setamos `is_admin=true` em linha de "admin comum" — só na linha
  base (`unit_type`/`unit_id` NULL) do `is_super_admin`.
- Desativar um usuário inteiro (`users.active = false`) precisa colocar
  `is_enabled=false` em **todas** as linhas de `policy` daquele subject (o `EXISTS`
  procura qualquer linha habilitada; uma só linha ativa sobrando já daria acesso).
- Revogar uma unidade específica = `PATCH` só daquela linha (`is_enabled=false`).
- 7 `unit_type` de dados + 1 de controle de array: `cras`, `escola`, `cre`, `ap`, `cas`,
  `clinica_familia`, `equipe_familia` (RLS nativo do Postgres, aplicado em
  `endpoint_participante_listagem`/`endpoint_participante_visao_geral`) e `secretaria`
  (não é RLS nativo — é usado pelo app-pic pra recalcular/filtrar o array
  `protocolo_listagem` em Polars, depois que o data-proxy já retornou as linhas
  reduzidas por unidade).

### `is_admin` (nativo/data-proxy) vs `users.is_admin` (app) vs `users.is_super_admin` (app)

| Conceito | Onde mora | Vai pro data-proxy? | Significado |
|---|---|---|---|
| `users.is_admin` | Postgres local | Não | "admin comum": acessa o painel admin, gerencia só um subconjunto de usuários (cujas unidades são subconjunto das próprias). Validado 100% no backend do app-pic. |
| `users.is_super_admin` | Postgres local | Sim, vira `is_admin=true` na linha base de `policy`/`access_policy` | Gerencia todos os usuários no painel E enxerga todos os dados (bypass total de RLS). |
| `policy.is_admin` / `access_policy.is_admin` | data-proxy | — | Nativo: bypass total de RLS pra aquele subject. Só usado para espelhar `users.is_super_admin`. |

A lógica de validação existente (`src/pic/infrastructure/admin/validation.py`:
`require_admin`, `_filter_manageable_users`, `validate_secretaria_acesso_permission`,
`validate_segmented_admin_can_manage`) **não muda** — ela já opera sobre
`is_admin`/`is_super_admin` do domínio (`UserPermissions`). Só troca a fonte desses
dados (Postgres local em vez de BigQuery).

---

## 5. Fluxo de escrita (grants/RLS)

Ordem estrita — data-proxy é o gate, Postgres local só reflete o que foi confirmado:

1. Monta a mudança (grant novo, revogação, toggle de `is_super_admin`/`active`).
2. `PATCH`/`POST` no `rls.access_policy` do data-proxy via PostgREST (role
   `policy_writer_app_pequenos_cariocas`, token via `client_credentials` no Keycloak).
3. Se der certo → grava a mesma mudança em `policy` local, com `synced_at = now()`.
4. Se falhar → **não** toca no banco local; propaga o erro pro admin.
5. Campos puramente de identidade (`nome`, `email`, `ocupacao`, `secretaria`, `notes`,
   `users.is_admin` "comum") não passam pelo data-proxy — gravam direto em `users`
   local, sem gate.

## 6. Fluxo de leitura

Painel admin (listar/filtrar/paginar usuários, `fetch_governance_df`,
`find_paginated_users`, `find_users_by_cpfs`) lê **só** do Postgres local, via
`JOIN users ON policy.subject = users.cpf`, reconstruindo o mesmo formato "flat" (uma
linha por usuário, colunas `id_cras_list`/`id_escola_list`/etc. como listas de
`IdWithName`) que a `IAdminRepository` já expõe hoje — sem chamar o data-proxy.

---

## 7. Infraestrutura e configuração

### 7.1 Conexão com o Postgres novo — investigação e decisão

App-pic **não roda no mesmo projeto/VPC** do Postgres novo. Confirmado via `gcloud`/
`kubectl` (contas com acesso de leitura aos dois lados):

- Postgres: instância `postgres` no projeto `rj-iplanrio-dia`
  (`rj-iplanrio-dia:us-central1:postgres`), rede `default`, IP público
  `35.193.157.1`, `sslMode: ENCRYPTED_ONLY` (conexão criptografada, sem exigir
  verificação de certificado), `connectorEnforcement: NOT_REQUIRED`,
  `authorizedNetworks` vazio hoje. Banco `pic` e usuário `pic` já existem na
  instância (compartilhada com n8n, airflow, authentik, sonarqube, etc).
- App-pic roda no cluster `application` do projeto `rj-superapp`, rede
  `application-network` — projeto e VPC diferentes do Postgres. O NAT desse cluster
  usa IP de saída automático/efêmero (`AUTO_ONLY`), não fixo.
- Sem VPC peering entre os dois projetos e sem IP público liberado, a única forma de
  conectar é via **Cloud SQL Auth Proxy / connector** — que não depende da VPC de
  nenhum dos dois lados (o túnel é autenticado via IAM/mTLS sobre HTTPS até a API do
  Google, não pela rede da instância).

**Decisão final (confirmada com Pedro/Diego no Slack em 20/08)**: usar o **Cloud SQL
connector via Workload Identity Federation (WIF)** — sem chave de service account
estática. O cluster `application` (rj-superapp) já tem a federação de identidade
liberada; falta só a Google Service Account (no projeto `rj-iplanrio-dia`) com a role
`roles/cloudsql.client`, vinculada via WIF à KSA do app-pic — Pedro fica responsável
por criar/configurar essa GSA e o binding.

Implicações pro código:

- Usar a lib `cloud-sql-python-connector` (extra `[asyncpg]`), **não** um sidecar —
  zero componente extra no deployment.
- Autenticação do túnel usa Application Default Credentials (ADC) automaticamente via
  o metadata server do GKE (WIF) — **nenhuma credencial em env var** para isso.
- A autenticação no Postgres em si continua sendo usuário/senha nativos
  (`APP_PIC_PG_USER`/`APP_PIC_PG_PW`), como já está no `.env` — o connector só troca a
  forma de abrir a conexão TCP, não o login do Postgres.
- Localmente (fora do cluster), precisa de `gcloud auth application-default login`
  com uma conta que tenha `roles/cloudsql.client` em `rj-iplanrio-dia` (a conta
  `diego.soliveira@prefeitura.rio` já tem acesso de leitura ao projeto — confirmar se
  também tem/terá essa role).

### 7.2 Demais pontos

- **Driver/ORM**: SQLAlchemy (async) + Alembic para migrations, usando o connector
  como `creator`/`async_creator` da engine (em vez de uma URL de host:porta comum).
- **Cliente do data-proxy**: HTTP (via `httpx`, já é dependência) contra o PostgREST do
  data-proxy (`DATA_PROXY_API_URL`), autenticando via OAuth2 `client_credentials` no
  mesmo Keycloak do `RMI_ISSUER` (realm `idrio_cidadao`), usando
  `DATA_PROXY_CLIENT_ID`/`DATA_PROXY_CLIENT_SECRET` já presentes no `.env`. Token URL:
  `https://auth-idriohom.apps.rio.gov.br/auth/realms/idrio_cidadao/protocol/openid-connect/token`.
- Variáveis já presentes em `src/config/.env`: `APP_PIC_PG_DB`, `APP_PIC_PG_USER`,
  `APP_PIC_PG_PW`, `DATA_PROXY_API_URL`, `DATA_PROXY_CLIENT_ID`,
  `DATA_PROXY_CLIENT_SECRET`.
- Variáveis a adicionar: `APP_PIC_PG_INSTANCE_CONNECTION_NAME`
  (`rj-iplanrio-dia:us-central1:postgres`, já confirmado — não é segredo),
  `DATA_PROXY_TOKEN_URL` (já temos o valor acima), `DATA_PROXY_SCHEMA`
  (`app_pequenos_cariocas`). Nenhuma variável de credencial nova é necessária (WIF).
- Dependências novas em `pyproject.toml` (via `uv add`): `sqlalchemy[asyncio]`,
  `asyncpg`, `alembic`, `cloud-sql-python-connector[asyncpg]`.
- Ação pendente de deploy: confirmar/ajustar a `ServiceAccount` do Pod (anotação
  `iam.gke.io/gcp-service-account: <gsa>@rj-iplanrio-dia.iam.gserviceaccount.com`) nos
  charts de `k8s/api/{staging,prod}` assim que Pedro criar a GSA — hoje esses
  manifests não têm essa configuração.

---

## 8. Estrutura de código planejada

```
src/pic/infrastructure/
  db/
    engine.py                 # engine async SQLAlchemy (Cloud SQL Python Connector + WIF)
    models.py                 # ORM: User, PolicyRow
  data_proxy/
    client.py                 # AccessPolicyClient: token client_credentials + cache,
                               #   GET/POST/PATCH em rls.access_policy via PostgREST
  repositories/
    hybrid_admin.py            # HybridAdminRepository(IAdminRepository):
                               #   orquestra UsersRepo (SQLAlchemy) + AccessPolicyClient,
                               #   aplica a ordem de escrita da seção 5
alembic/
  env.py
  versions/
    0001_create_users_and_policy.py
```

`src/pic/presentation/di.py` troca `BigQueryAdminRepository` por
`HybridAdminRepository` — único ponto de wiring.

---

## 9. Checklist cross-team (data-proxy / Pedro)

1. ~~Adicionar `metadata`/timestamps em `access_policy`~~ — feito (`81324d7`), mas
   decidimos não usar `metadata` no fim das contas.
2. Confirmar client Keycloak `policy_writer_app_pequenos_cariocas` (confidential,
   service account) — credenciais já recebidas em `.env`, falta validar em staging.
3. Confirmar `app_pequenos_cariocas` no `syncConfig` de produção do data-proxy, com os
   7 `rls` mappings em `endpoint_participante_listagem`/`_visao_geral`.
4. Realinhar com o Pedro sobre a semântica de `is_admin` + `unit_type`/`unit_id`
   (seção 4) — divergência encontrada entre o que ele descreveu e o código atual.
5. (Fora de escopo por ora) client scope `schemas` claim mapper no Keycloak do app-pic,
   necessário só quando migrarmos o read-path de participantes.
6. Pedro cria a GSA em `rj-iplanrio-dia` com `roles/cloudsql.client` e configura o WIF
   binding com a KSA do app-pic (confirmado no Slack em 20/08). Depois disso, ajustar
   a anotação da `ServiceAccount` nos manifests `k8s/api/{staging,prod}`.

---

## 10. Passos de implementação

1. Adicionar `sqlalchemy[asyncio]`, `asyncpg`, `alembic`,
   `cloud-sql-python-connector[asyncpg]` via `uv add`; configurar `alembic/env.py`
   para ler `env.py`.
2. Criar migration inicial: tabelas `users` e `policy` (seção 3.1/3.2).
3. Implementar `AccessPolicyClient` (token cache, `GET`/`POST`/`PATCH` em
   `access_policy`, tratamento de erro sem retry silencioso).
4. Implementar `HybridAdminRepository` cobrindo todos os métodos de
   `IAdminRepository` (`fetch_governance_df`, `find_paginated_users`,
   `find_users_by_cpfs`, `update_user`, `insert_user`, `soft_delete_user`,
   `batch_merge_permissions`, `refresh_cache`), seguindo a ordem de escrita da seção 5.
5. Atualizar `env.py` com as novas variáveis (seção 7) e `.env`/`.env.example`.
6. Trocar `BigQueryAdminRepository` por `HybridAdminRepository` em `di.py`.
7. Simplificar `example.md` para refletir só o desenho final de grants (sem metadata
   de usuário) — ou removê-lo em favor deste `plan.md`.
8. Rodar `just lint-python` / `uv run pytest src/pic` antes de considerar concluído.
9. Plano de rollout: backfill de `endpoint_data_access` (BigQuery) para `users` +
   `policy` (novo Postgres + data-proxy), validar paridade com a v2 atual antes do
   cutover em produção.

---

## 11. Pendências / bloqueios conhecidos

- Falta a GSA em `rj-iplanrio-dia` com `roles/cloudsql.client` + binding WIF com a KSA
  do app-pic (responsabilidade do Pedro, confirmado no Slack em 20/08).
- Falta confirmar se a conta usada em desenvolvimento local também tem/terá
  `roles/cloudsql.client` em `rj-iplanrio-dia` para testar via
  `gcloud auth application-default login`.
- Falta ajustar a anotação da `ServiceAccount` nos manifests `k8s/api/{staging,prod}`
  assim que a GSA existir.
- Falta confirmar se `syncConfig` de produção do data-proxy já tem
  `app_pequenos_cariocas` configurado.
- Falta validar client Keycloak `policy_writer_app_pequenos_cariocas` em staging (fazer
  um `POST`/`GET` de teste contra `DATA_PROXY_API_URL`).
