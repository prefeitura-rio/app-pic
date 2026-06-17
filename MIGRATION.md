# Migration: Python/BigQuery → Hono/Prisma/PostgreSQL

Documento de referência da decisão e plano de migração da stack do app-pic.
Registra o contexto, problemas identificados e o plano acordado.

---

## Stack atual

```
BigQuery (dados PIC)
    ↓ SELECT * (sem WHERE, sem LIMIT)
Python FastAPI
    ├── Polars (filtro em memória)
    ├── L1 cache (dict Python, in-process)
    └── L2 cache (Redis, pickle)
            ↓
Next.js (proxy — injeta Bearer token)
    ↓
Cliente
```

### Por que foi feito assim

BigQuery tem latência de 1–5s por query — inadequado para requests individuais de uma aplicação web. A solução adotada foi carregar as tabelas inteiras em RAM e filtrar com Polars. Funciona, mas tem um teto: conforme o programa cresce, a memória cresce proporcionalmente.

### Configuração atual de recursos (K8s)

```yaml
# k8s/api/prod/resources.yaml
resources:
  requests:
    cpu: 250m
    memory: 4Gi
  limits:
    cpu: 1000m
    memory: 6Gi
```

Cluster: `iplanrio-infra` (rj-iplanrio-dia), `n2d-standard-8`, 4 nodes × 32GB = 128GB total.

---

## Problemas identificados

### Arquitetural — não urgente

- `SELECT *` sem WHERE nem LIMIT carrega ~168k rows por request de cache miss
- Governança feita em Python após buscar tudo: carrega 168k rows para mostrar ~5k ao usuário
- Cache baseado em tempo (300s) — janela de dados desatualizados
- `time.sleep(0.1)` bloqueando event loop asyncio em `admin.py`
- Sem pooling do BigQuery client — novo cliente criado a cada query
- Endpoints chamados pelo frontend que não existem no FastAPI (`GET /participants/{cpf}`)
- Profiling interno exposto na resposta da API (`PaginationMeta.profiling`)
- `dependencies.py` — 100% código comentado, morto
- `next-auth` instalado mas não usado (~2MB de dependência morta)

---

## Decisão de migração

**Migrar para Hono + Prisma + PostgreSQL (Cloud SQL).**

### Por que PostgreSQL resolve o problema de memória

```
Hoje:   SELECT * → 168k rows em RAM → Polars filtra em-processo
Depois: SELECT ... WHERE id_cras = $1 LIMIT 20 OFFSET $2 → só as linhas necessárias
```

Com PostgreSQL e índices corretos, queries retornam em <100ms. Não há mais necessidade de cachear datasets inteiros. A memória do pod cai de 4–6Gi para ~200–500Mi.

### Por que Hono + TypeScript

- Frontend já é Next.js/TypeScript — stack unificada, tipos compartilhados
- Elimina o gap Python/TypeScript no onboarding
- Hono é leve, rápido e tem suporte nativo a edge/K8s
- Prisma migrations — schema versionado e rastreável (vs. BQ onde mudanças são invisíveis)

### O que não muda

- **Keycloak/GovBR** — continua como IdP obrigatório (compliance governo)
- **dbt pipelines** — `mart_pic_*` continua rodando normalmente no BQ
- **Frontend Next.js** — só muda o destino do proxy

---

## Fontes de dados (BQ → PostgreSQL)

As tabelas `app_pequenos_cariocas` (endpoint_participante_listagem, endpoint_participante_visao_geral) existiam apenas para facilitar o backend Python. Com PostgreSQL, consumimos diretamente das tabelas PIC.

| Tabela BQ (fonte) | Tabela PG | Rows atuais | Observação |
|---|---|---|---|
| `projeto_pequenos_cariocas.participantes` | `participants` | 168k | Structs aninhados achatados no sync |
| `projeto_pequenos_cariocas.protocolo_estado_atual` | `participant_protocols` | 2.36M | Já é formato LONG — copia direto |
| `projeto_pequenos_cariocas.resultado_mensal` | `monthly_results` | 500k (7 meses) | Histórico para dashboard |
| `app_pequenos_cariocas.endpoint_camadas_geoespaciais` | `geo_layers` | ~5k | Geometria como GeoJSON |
| `app_pequenos_cariocas.endpoint_data_access` | `users` + `user_equipment_access` | pequeno | App-owned, CRUD próprio |

### Tabelas eliminadas (não precisam mais existir)

- `endpoint_participante_listagem` — era um JOIN desnormalizado para o Python. No PG, fazemos o JOIN diretamente.
- `endpoint_participante_visao_geral` — era um CUBE pré-agregado de todas as combinações de filtro. No PG, agregamos dinamicamente com GROUP BY.

---

## Como o dashboard muda

O `endpoint_participante_visao_geral` era um CUBE pré-computado de todas as combinações de filtro no BQ. No PostgreSQL, as métricas são calculadas dinamicamente:

```sql
-- Indicadores atuais com governança aplicada
SELECT
  COUNT(*)                                         AS total,
  COUNT(*) FILTER (WHERE situacao = 'Regular')     AS regular,
  COUNT(*) FILTER (WHERE situacao = 'Irregular')   AS irregular
FROM participants
WHERE status = 'ativo'
  AND ($grupo IS NULL OR grupo = $grupo)
  AND id_cras = ANY($cras_list);  -- governança do usuário

-- Série histórica mensal (antes exigia CUBE pré-agregado no BQ)
SELECT
  mr.mes,
  SUM(mr.geral_regular)::numeric / NULLIF(SUM(mr.geral_total), 0) AS pct_regular
FROM monthly_results mr
JOIN participants p USING (id_membro_familia)
WHERE p.id_cras = ANY($cras_list)
GROUP BY mr.mes
ORDER BY mr.mes;
```

---

## Infraestrutura necessária

### Cloud SQL (rj-pic-dev)

```bash
gcloud sql instances create app-pic \
  --database-version=POSTGRES_17 \
  --tier=db-custom-2-7680 \     # 2 vCPU, 7.5GB RAM, ~$100/mes
  --region=us-central1 \
  --storage-size=50GB \
  --storage-auto-increase \
  --no-assign-ip \              # só IP privado, sem IP público
  --network=default \
  --project=rj-pic-dev
```

Resize futuro (online, segundos de downtime):
```bash
gcloud sql instances patch app-pic --tier=db-custom-4-15360 --project=rj-pic-dev
```

### Extensions a habilitar

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- busca por similaridade de nome
CREATE EXTENSION IF NOT EXISTS unaccent;  -- José = Jose na busca
```

### Cloud SQL Proxy (K8s — namespace cloud-sql-proxy)

Seguir o padrão já existente em `cloud-sql-proxy` namespace no cluster `iplanrio-infra`.
Usar Cloud SQL Auth Proxy v2 (`cloud-sql-proxy:2.x`, não o legado `gce-proxy:1.23`).

### Auth (Keycloak/GovBR permanece)

Better Auth pode ser usado como camada de sessão em cima do Keycloak (OIDC client), substituindo o gerenciamento manual de cookies atual (`callback/rmi/route.ts`, `refresh/route.ts`). O Keycloak continua como IdP — não há mudança no fluxo de autenticação com o governo.

---

## Plano de execução

Cada etapa é deployável e testável independentemente. O frontend não muda durante a migração.

```
Etapa 1 — Infraestrutura
  ├── Cloud SQL instance + database + extensions
  ├── Cloud SQL Proxy no K8s (iplanrio-infra)
  └── Secrets DATABASE_URL no Infisical

Etapa 2 — Schema e sync
  ├── Prisma schema + migrations iniciais
  ├── Sync script: BQ → PG (participantes + protocolos + monthly_results + geo_layers)
  └── Migrar users/equipment_access de endpoint_data_access → PG

Etapa 3 — API Hono (endpoints simples)
  ├── /health
  ├── /geospatial/layers (geo_layers direto do PG)
  └── Auth/sessão (Better Auth + Keycloak OIDC)

Etapa 4 — API Hono (participants — parte crítica)
  ├── GET /participants (listagem com filtros + paginação SQL)
  ├── GET /participants/:id (detalhe)
  └── Governança em SQL (WHERE id_cras = ANY($list))
  ⚠️  Testar exaustivamente: quem vê o quê deve ser idêntico ao comportamento atual

Etapa 5 — API Hono (dashboard)
  ├── Indicadores atuais (COUNT com filtros)
  └── Séries históricas (GROUP BY mes via monthly_results)

Etapa 6 — API Hono (admin CRUD)
  ├── GET/PUT/DELETE /admin/users/:cpf
  └── POST /admin/users-batch

Etapa 7 — Desliga Python
  └── Remove imagem, deployments e dependências do backend Python
```

---

## Evolução de schema

O dbt adiciona colunas no BQ com frequência. Sem uma estratégia, cada mudança pode quebrar o sync e exigir migration + deploy coordenados.

### Problema

```
dbt adiciona coluna nova no BQ
        ↓
sync tenta copiar → coluna não existe no PG → quebra
        ↓
alguém precisa rodar migration manualmente + fazer deploy da API
```

### Solução: coluna `extra` JSONB como buffer

Cada tabela sincronizada tem uma coluna `extra Json?` que absorve campos desconhecidos automaticamente. O sync nunca quebra por campo novo — ele vai para `extra` até o time decidir promover para coluna própria.

```prisma
model Participant {
  // campos conhecidos, indexados, usados em queries
  id_membro_familia String  @id
  nome              String
  id_cras           String?
  status            String?
  // ...

  // buffer para campos novos do BQ ainda não promovidos
  extra Json?

  @@map("participants")
}
```

### Sync tolerante a schema

O script de sync não pode ter colunas hardcoded. Ele separa campos conhecidos de desconhecidos em tempo de execução:

```typescript
const KNOWN_COLUMNS = new Set([
  'id_membro_familia', 'cpf', 'nome', 'status', 'id_cras',
  // ... todos os campos do schema Prisma atual
])

function splitRow(bqRow: Record<string, unknown>) {
  const known: Record<string, unknown> = {}
  const extra: Record<string, unknown> = {}

  for (const [key, value] of Object.entries(bqRow)) {
    if (KNOWN_COLUMNS.has(key)) known[key] = value
    else extra[key] = value
  }

  return { known, extra }
}

// no upsert
const { known, extra } = splitRow(bqRow)
await db.participant.upsert({
  where: { id_membro_familia: known.id_membro_familia as string },
  create: { ...known, extra: Object.keys(extra).length ? extra : undefined },
  update: { ...known, extra: Object.keys(extra).length ? extra : undefined },
})
```

### Fluxo com esse sistema

```
dbt adiciona coluna nova no BQ
        ↓
sync roda normalmente — campo vai pra extra, não quebra
        ↓
CI detecta drift e avisa o time (ver abaixo)
        ↓
time decide:
  ├── campo precisa de índice ou filtro? → migration + promove para coluna
  └── campo é só exibição? → fica em extra, API lê de lá
```

A API acessa campos em `extra` enquanto a migration não acontece:

```typescript
// antes da migration — lê de extra
const valor = participant.extra?.novo_campo

// depois da migration — campo promovido para coluna própria
const valor = participant.novo_campo
```

### Detecção de drift no CI

Job no pipeline que compara o schema BQ com o Prisma e abre alerta quando há campos novos. Não bloqueia o deploy — só avisa:

```bash
# .github/workflows/schema-drift.yml (ou equivalente)
bq show --schema rj-crm-registry:projeto_pequenos_cariocas.participantes \
  | jq '[.[].name]' > /tmp/bq_columns.json

# extrai colunas do Prisma (exceto 'extra' e campos app-owned)
node scripts/list-prisma-columns.ts > /tmp/prisma_columns.json

# diff — campos no BQ que não estão no Prisma vão pra extra
diff /tmp/bq_columns.json /tmp/prisma_columns.json \
  && echo "Schema em sincronia" \
  || echo "DRIFT: campos novos no BQ detectados — avaliar promoção para coluna"
```

### Dois tipos de coluna — separar responsabilidades

| Tipo | Exemplos | Quem controla | Como muda |
|---|---|---|---|
| **Sync** | `id_cras`, `nome_escola`, `status` | dbt | Vai pra `extra` primeiro, promove se necessário |
| **App-owned** | `created_at`, campos de `users` | Este repo | Sempre via Prisma migration explícita |

Nunca misturar: campos app-owned nunca entram no sync, campos sync nunca são escritos pela API diretamente.

---

## Riscos

**Governança (alto)** — A lógica de quem vê quais participantes é o núcleo de segurança. A tradução de Polars filters para SQL WHERE precisa de testes explícitos cobrindo todos os tipos de acesso (secretaria_acesso = TODOS, SMAS, SME, SMS + listas de equipamentos específicos).

**Sync script (médio)** — Precisa tratar:
- Deleções (participantes que saem do programa)
- Evolução de schema (campo novo no BQ → vai pra `extra`, não quebra)
- Falhas parciais (transação ou idempotência)

**Histórico (baixo)** — `monthly_results` cresce ~70k rows/mês. Em 2 anos: ~2M rows adicionais. Sem impacto de performance com o índice em `mes`.
