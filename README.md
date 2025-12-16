# PIC - Pequenos Cariocas

Plataforma integrada para acompanhamento de criancas e gestantes do programa Pequenos Cariocas da Prefeitura do Rio de Janeiro, reunindo informacoes de saude, educacao e assistencia social em um unico painel de monitoramento.

## Visao Geral

O PIC (Pequenos Cariocas) e uma aplicacao fullstack que permite:

- **Dashboard Gerencial**: Visualizar indicadores agregados de participantes do programa com metricas de regularidade por secretaria (Saude, Educacao, Assistencia Social)
- **Monitoramento de Protocolos**: Acompanhar o cumprimento de protocolos obrigatorios como vacinacao, frequencia escolar, atualizacao de CadUnico, entre outros
- **Busca Individual**: Pesquisar participantes por nome ou CPF com filtros avancados e multi-selecao
- **Analise Temporal**: Graficos de evolucao do programa, tempo medio de irregularidade e taxa de resolucao de alertas
- **Gestao de Acessos**: Sistema de governanca com permissoes por unidade (CRAS, Escolas, Clinicas, CAP, CRE, CAS)

## Funcionalidades do Dashboard

### Indicadores Principais
- Total de participantes ativos no programa
- Percentual de participantes regulares vs irregulares
- Breakdown por secretaria (SMS, SME, SMAS)

### Analise de Protocolos
- Regularidade por protocolo individual (CadUnico, Creche, Vacinacao, etc.)
- Filtros multi-selecao com logica AND (ex: ver quem tem CadUnico E Creche irregulares)
- Cascata inteligente de filtros

### Visualizacoes
- Evolucao temporal do resultado do programa
- Distribuicao por safra de ingresso (cohort)
- Motivos de saida do programa
- Tempo medio de irregularidade por secretaria
- Histograma de distribuicao por faixas de tempo
- Taxa de resolucao mensal de alertas

## Stack Tecnologico

### Backend

- **Python 3.13** - Linguagem principal
- **FastAPI** - Framework web async de alta performance
- **Polars 1.35+** - Processamento de dados (substitui Pandas para maior performance)
- **Google BigQuery** - Data warehouse para armazenamento
- **Redis 7+** - Cache distribuido
- **PyJWT** - Autenticacao via JWT/OAuth2 (gov.br)

### Frontend

- **Next.js 16** - Framework React com App Router
- **React 19** - UI Library
- **shadcn/ui** - Biblioteca de componentes (Radix UI)
- **TypeScript 5** - Type safety
- **Tailwind CSS 4** - Estilizacao utility-first
- **TanStack Query 5** - Gerenciamento de estado servidor
- **Recharts 3** - Graficos e visualizacoes
- **react-window** - Virtualizacao de listas longas
- **NextAuth.js 5** - Autenticacao OAuth2

## Estrutura do Projeto

```text
app-pic/
├── src/
│   ├── api/                    # Endpoints da API
│   │   └── v1/
│   │       ├── admin.py        # Endpoints de governanca/admin
│   │       ├── dashboard.py    # Metricas agregadas do dashboard
│   │       ├── participants.py # Listagem de participantes
│   │       ├── auth.py         # Autenticacao
│   │       ├── queries.py      # Queries SQL BigQuery
│   │       └── schemas.py      # Schemas Pydantic
│   ├── config/
│   │   ├── env.py              # Variaveis de ambiente
│   │   └── .env                # Configuracoes locais (gitignored)
│   ├── core/
│   │   ├── middlewares/        # Middlewares FastAPI
│   │   └── security/           # JWT, permissoes, governanca
│   ├── frontend/               # Aplicacao Next.js
│   │   ├── app/
│   │   │   ├── components/     # Componentes React
│   │   │   │   ├── ui/         # Componentes base (shadcn)
│   │   │   │   ├── OverviewTab.tsx       # Aba de visao geral
│   │   │   │   ├── ProfessionalTab.tsx   # Aba de busca individual
│   │   │   │   ├── FilterCard.tsx        # Card de filtros
│   │   │   │   └── ...
│   │   │   ├── services/       # Servicos de API
│   │   │   ├── types.ts        # Tipos TypeScript
│   │   │   ├── login/          # Pagina de login
│   │   │   └── admin/          # Pagina de administracao
│   │   └── package.json
│   ├── utils/
│   │   ├── bigquery.py         # Cliente BigQuery com Arrow
│   │   ├── cache_manager.py    # Sistema de cache L1/L2
│   │   ├── data_manager.py     # Pipeline de dados e filtros
│   │   ├── data_manager_config.py # Configuracoes do DataManager
│   │   └── log.py              # Configuracao de logs (Loguru)
│   └── main.py                 # Entrypoint FastAPI
├── scripts/
│   └── bootstrap_super_admin.py # Script para criar primeiro admin
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml              # Dependencias Python (uv)
├── justfile                    # Comandos de desenvolvimento
└── README.md
```

## Arquitetura

### Sistema de Cache (2 niveis)

```text
┌─────────────────────────────────────────────────────────────┐
│                         Request                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  L1 - Memory Cache (InMemoryCache)                          │
│  • Thread-safe, TTL-based                                   │
│  • Instant access (~0.001s)                                 │
│  • Local ao processo                                        │
└─────────────────────────────────────────────────────────────┘
                              │ MISS
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  L2 - Redis Cache                                           │
│  • Pickle + LZ4 compression                                 │
│  • Compartilhado entre processos                            │
│  • TTL configuravel (default 5min)                          │
└─────────────────────────────────────────────────────────────┘
                              │ MISS
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  BigQuery (via Arrow)                                        │
│  • Query SQL completa                                        │
│  • Zero-copy transfer para Polars                           │
│  • ~3-5s por query                                          │
└─────────────────────────────────────────────────────────────┘
```

### Pipeline de Dados (DataManager)

```text
┌──────────────────────────────────────────────────────────────┐
│  fetch_filter_paginate()                                     │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│ 1. GET DATASET   │──▶│ 2. GOVERNANCE    │──▶│ 3. APPLY FILTERS │
│    (Cache/BQ)    │   │    FILTERS       │   │    (Polars)      │
└──────────────────┘   └──────────────────┘   └──────────────────┘
                                                     │
    ┌────────────────────────────────────────────────┘
    ▼
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│ 4. APPLY SEARCH  │──▶│ 5. SORT          │──▶│ 6. FILTER OPTIONS│
│    (Nome/CPF)    │   │    (Coluna)      │   │    (Cascata)     │
└──────────────────┘   └──────────────────┘   └──────────────────┘
                                                     │
                                                     ▼
                                              ┌──────────────────┐
                                              │ 7. PAGINATE      │
                                              │    (Slice)       │
                                              └──────────────────┘
```

### Sistema de Filtros

O sistema suporta filtros avancados com:

- **Multi-selecao**: Selecionar multiplos valores para um filtro
- **Logica AND**: Quando multiplos protocolos sao selecionados com um status, apenas participantes que tenham TODOS os protocolos com aquele status sao exibidos
- **Cascata inteligente**: Opcoes de filtro sao recalculadas baseadas nos filtros ativos, excluindo o proprio filtro para manter suas opcoes disponiveis
- **Filtros de array**: Suporte a filtrar por campos dentro de arrays de structs (ex: protocolo_listagem.descricao)

### Fluxo de Autenticacao

```text
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  Login   │────▶│ Keycloak │────▶│  gov.br  │────▶│ Callback │
│  Page    │     │  (RMI)   │     │  OAuth2  │     │  /api/   │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
                                                         │
                                                         ▼
┌─────────────────────────────────────────────────────────────┐
│  JWT Token (preferred_username = CPF)                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Governance Table (BigQuery)                                 │
│  • Verifica se CPF esta cadastrado                          │
│  • Carrega permissoes (IDs autorizados)                     │
│  • Determina nivel: user/admin/super_admin                  │
└─────────────────────────────────────────────────────────────┘
```

### Sistema de Governanca

O sistema possui 3 niveis de acesso:

| Nivel | Descricao |
|-------|-----------|
| **user** | Ve apenas dados das unidades atribuidas (CRAS, Escolas, Clinicas, CAP, CRE, CAS) |
| **admin** | Pode gerenciar usuarios com subset de seus IDs |
| **super_admin** | Acesso total, pode gerenciar qualquer usuario |

Filtros de governanca sao aplicados em memoria apos buscar do cache, garantindo que cada usuario veja apenas seus dados autorizados sem afetar o cache compartilhado.

## Endpoints da API

### Autenticacao

Todos os endpoints requerem header `Authorization: Bearer <token>`.

### Principais Endpoints

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/health` | Health check |
| GET | `/api/v1/dashboard` | Metricas agregadas do dashboard |
| GET | `/api/v1/participants` | Lista participantes com filtros e paginacao |
| GET | `/api/v1/admin/me` | Informacoes do usuario atual |
| GET | `/api/v1/admin/users` | Lista usuarios (apenas admin) |
| PUT | `/api/v1/admin/users/{cpf}` | Cria/atualiza usuario (UPSERT) |
| DELETE | `/api/v1/admin/users/{cpf}` | Soft-delete de usuario |
| GET | `/api/v1/admin/available-ids` | IDs disponiveis para atribuicao |

### Parametros de Query Comuns

| Parametro | Tipo | Descricao |
|-----------|------|-----------|
| `page` | int | Pagina atual (1-indexed) |
| `page_size` | int | Itens por pagina (1-10000) |
| `search` | string | Busca por nome ou CPF |
| `bypass_cache` | bool | Forca refresh do cache |
| `sort_by` | string | Coluna para ordenacao |
| `sort_order` | asc/desc | Direcao da ordenacao |
| `grupo`, `status`, `bairro`, etc. | string | Filtros simples |
| `protocolo_descricao` | string | Filtro de protocolo (multi-selecao com virgula) |
| `protocolo_status` | string | Filtro de status do protocolo |

## Configuracao

### Variaveis de Ambiente (Backend)

Crie um arquivo `src/config/.env` com:

```env
# BigQuery
GCP_SERVICE_ACCOUNT_CREDENTIALS={"type": "service_account", ...}
BQ_PROJECT_ID=rj-pic-dev
BQ_DATASET_ID=app_pequenos_cariocas
BQ_TABLE_ID_PARTICIPANTS_LISTAGEM=endpoint_participante_listagem
BQ_TABLE_ID_DASHBOARD=endpoint_participante_visao_geral
BQ_TABLE_ID_DATA_ACCESS=controle_acesso

# OAuth2 (Keycloak/RMI)
RMI_ISSUER=https://seu-keycloak.com/realms/seu-realm
RMI_AUDIENCE=seu-client-id

# Cache
REDIS_URL=redis://localhost:6379
CACHE_TTL_SECONDS=300
```

### Variaveis de Ambiente (Frontend)

Crie um arquivo `src/frontend/.env.local` com:

```env
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=seu-secret-aleatorio-32-chars
NEXT_PUBLIC_API_URL=http://localhost:8089
RMI_ISSUER=https://seu-keycloak.com/realms/seu-realm
RMI_CLIENT_ID=seu-client-id
RMI_CLIENT_SECRET=seu-client-secret
```

## Desenvolvimento

### Pre-requisitos

- Python 3.13+
- Node.js 20+
- uv (gerenciador de pacotes Python)
- just (command runner)
- Redis (ou Docker para subir localmente)

### Instalacao

```bash
# Clonar repositorio
git clone https://github.com/prefeitura-rio/app-pic.git
cd app-pic

# Instalar dependencias Python
uv sync

# Instalar dependencias Frontend
cd src/frontend && npm install && cd ../..

# Subir Redis (se nao tiver rodando)
docker run -d -p 6379:6379 redis:7-alpine
```

### Comandos

```bash
# Listar todos os comandos disponiveis
just

# Rodar backend (porta 8089)
just run-api

# Rodar frontend (porta 3000)
just run-frontend

# Rodar ambos em paralelo
just dev

# Linting
just lint           # Python + Frontend
just lint-python    # Apenas Python
just lint-frontend  # Apenas Frontend

# Formatacao
just fmt            # Python + Frontend
just fix            # Auto-fix Python (ruff)
```

### Primeiro Acesso (Bootstrap)

Para criar o primeiro super admin:

1. Edite `scripts/bootstrap_super_admin.py` e configure o CPF:

   ```python
   SUPER_ADMIN_CPF = "12345678900"  # CPF do primeiro admin
   ```

2. Execute o script:

   ```bash
   uv run python scripts/bootstrap_super_admin.py
   ```

3. Faca login com o CPF configurado via gov.br.

## Deploy

### Docker Compose

```bash
# Build e start
docker-compose up -d --build

# Logs
docker-compose logs -f

# Stop
docker-compose down
```

### Variaveis em Producao

Em producao, configure as variaveis via secrets do Kubernetes ou sistema de CI/CD. Nunca commite credenciais no repositorio.

## Performance

### Otimizacoes Implementadas

1. **Polars ao inves de Pandas** - 10x mais rapido para operacoes de DataFrame
2. **Cache L1/L2** - Evita deserializacao repetida e queries ao BigQuery
3. **Filter options pre-computadas** - Calculadas durante cache write (instant em cache hit)
4. **Arrow para BigQuery** - Transferencia zero-copy de dados
5. **Virtualizacao de listas** - react-window para selects com muitas opcoes
6. **React.memo e useCallback** - Evita re-renders desnecessarios no frontend
7. **Filtros combinados de array** - Explode + filter em uma unica operacao

### Metricas Tipicas

| Operacao | Cache Hit | Cache Miss |
|----------|-----------|------------|
| /dashboard | ~0.1s | ~5s |
| /participants (paginado) | ~0.3s | ~5s |
| Filtro cascata | ~0.05s | N/A |
| Multi-select com AND | ~0.1s | N/A |

## Troubleshooting

### Cache desatualizado

O botao "Atualizar" no frontend envia `bypass_cache=true` que:

1. Ignora cache L1 (memoria) e L2 (Redis)
2. Busca dados frescos do BigQuery
3. Substitui o cache antigo

### Login em loop

Verifique se:

1. CPF esta cadastrado na tabela de governanca (`controle_acesso`)
2. Usuario esta marcado como `active=true`
3. Cookies estao sendo aceitos pelo navegador
4. `NEXTAUTH_SECRET` esta configurado corretamente

### Erros de permissao

1. Verifique logs do backend: `logs/api_*.log`
2. Confirme que o CPF no JWT (`preferred_username`) bate com a tabela de governanca
3. Para admins segmentados, verifique se possui IDs suficientes atribuidos

### Dados nao aparecem no dashboard

1. Verifique se a tabela `BQ_TABLE_ID_DASHBOARD` esta correta
2. Limpe o cache com `bypass_cache=true`
3. Verifique os logs para erros de query

## Contribuindo

1. Crie uma branch a partir de `staging`
2. Faca suas alteracoes
3. Rode `just lint` e corrija problemas
4. Abra um PR para `staging`

## Licenca

Projeto interno da Prefeitura do Rio de Janeiro - Escritorio Municipal de Dados.
