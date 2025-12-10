# PIC - Pequenos Cariocas

Plataforma integrada para acompanhamento de criancas e gestantes da Prefeitura do Rio de Janeiro, reunindo informacoes de saude, educacao e assistencia social.

## Visao Geral

O PIC (Pequenos Cariocas) e uma aplicacao fullstack que permite:
- Visualizar indicadores e metricas de participantes do programa
- Monitorar o cumprimento de protocolos por dimensao (Saude, Educacao, Assistencia Social)
- Buscar e filtrar participantes individualmente
- Gerenciar permissoes de acesso por unidade (CRAS, Escolas, Clinicas, etc.)

## Stack Tecnologico

### Backend
- **Python 3.13** - Linguagem principal
- **FastAPI** - Framework web async
- **Polars** - Processamento de dados (substitui Pandas para maior performance)
- **Google BigQuery** - Data warehouse para armazenamento
- **Redis** - Cache distribuido (producao)
- **PyJWT** - Autenticacao via JWT/OAuth2

### Frontend
- **Next.js 16** - Framework React com App Router
- **React 19** - Biblioteca UI
- **TypeScript** - Type safety
- **Tailwind CSS 4** - Estilizacao
- **Radix UI** - Componentes acessiveis
- **TanStack Query** - Gerenciamento de estado servidor
- **Recharts** - Graficos e visualizacoes
- **NextAuth.js** - Autenticacao OAuth2

## Estrutura do Projeto

```
app-pic/
├── src/
│   ├── api/                    # Endpoints da API
│   │   └── v1/
│   │       ├── admin.py        # Endpoints de governanca/admin
│   │       ├── dashboard.py    # Metricas agregadas
│   │       ├── participants.py # Listagem de participantes
│   │       ├── auth.py         # Autenticacao
│   │       ├── queries.py      # Queries SQL BigQuery
│   │       └── schemas.py      # Schemas Pydantic
│   ├── config/
│   │   └── env.py              # Variaveis de ambiente
│   ├── core/
│   │   ├── middlewares/        # Middlewares FastAPI
│   │   └── security/           # JWT, permissoes
│   ├── frontend/               # Aplicacao Next.js
│   │   ├── app/
│   │   │   ├── components/     # Componentes React
│   │   │   ├── services/       # Servicos de API
│   │   │   ├── login/          # Pagina de login
│   │   │   └── admin/          # Pagina de administracao
│   │   └── package.json
│   ├── utils/
│   │   ├── bigquery.py         # Cliente BigQuery
│   │   ├── cache_manager.py    # Sistema de cache L1/L2
│   │   ├── data_manager.py     # Pipeline de dados
│   │   └── log.py              # Configuracao de logs
│   └── main.py                 # Entrypoint FastAPI
├── scripts/
│   └── bootstrap_super_admin.py # Script para criar primeiro admin
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── justfile                    # Comandos de desenvolvimento
└── README.md
```

## Arquitetura

### Sistema de Cache (2 niveis)

```
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
│  L2 - Redis/File Cache                                      │
│  • Redis em producao, File em dev                           │
│  • Pickle serialization (~2-3s deserialize)                 │
│  • Compartilhado entre processos                            │
└─────────────────────────────────────────────────────────────┘
                              │ MISS
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  BigQuery                                                    │
│  • Query SQL completa                                        │
│  • ~3-5s por query                                          │
└─────────────────────────────────────────────────────────────┘
```

### Fluxo de Autenticacao

```
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
| **user** | Ve apenas dados das unidades atribuidas (CRAS, Escolas, etc.) |
| **admin** | Pode gerenciar usuarios com subset de seus IDs |
| **super_admin** | Acesso total, pode gerenciar qualquer usuario |

Filtros de governanca sao aplicados em memoria apos buscar do cache, garantindo que cada usuario veja apenas seus dados autorizados.

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
| `bairro`, `cras`, `escola`, etc. | string | Filtros por unidade |

## Configuracao

### Variaveis de Ambiente

Crie um arquivo `src/config/.env` com:

```env
# BigQuery
GCP_SERVICE_ACCOUNT_CREDENTIALS={"type": "service_account", ...}
BQ_PROJECT_ID=seu-projeto-gcp
BQ_DATASET_ID=seu_dataset
BQ_TABLE_ID_PARTICIPANTS_LISTAGEM=nome_tabela_participantes
BQ_TABLE_ID_DATA_ACCESS=nome_tabela_governanca

# OAuth2 (Keycloak/RMI)
RMI_ISSUER=https://seu-keycloak.com/realms/seu-realm
RMI_AUDIENCE=seu-client-id
RMI_CLIENT_ID=seu-client-id
RMI_CLIENT_SECRET=seu-client-secret

# Cache
REDIS_URL=redis://localhost:6379
CACHE_TTL_SECONDS=300

# Desenvolvimento
USE_LOCAL_API=true
```

### Frontend (.env.local)

```env
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=seu-secret-aleatorio
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

### Instalacao

```bash
# Clonar repositorio
git clone https://github.com/seu-org/app-pic.git
cd app-pic

# Instalar dependencias Python
uv sync

# Instalar dependencias Frontend
cd src/frontend && npm install && cd ../..
```

### Comandos

```bash
# Listar todos os comandos disponiveis
just

# Rodar backend (porta 8089)
just run-api

# Rodar frontend (porta 3000)
just run-frontend

# Linting
just lint           # Python + Frontend
just lint-python    # Apenas Python
just lint-frontend  # Apenas Frontend

# Formatacao
just fmt            # Python + Frontend
just fix            # Auto-fix Python
```

### Primeiro Acesso (Bootstrap)

Para criar o primeiro super admin:

1. Edite `scripts/bootstrap_super_admin.py` e configure o CPF:
   ```python
   SUPER_ADMIN_CPF = "12345678900"  # CPF do primeiro admin
   ```

2. Execute o script:
   ```bash
   python scripts/bootstrap_super_admin.py
   ```

3. Faca login com o CPF configurado via gov.br.

## Deploy

### Docker Compose

```bash
# Build e start
docker-compose up -d

# Logs
docker-compose logs -f

# Stop
docker-compose down
```

### Kubernetes

Configuracoes em `k8s/`:
- ConfigMaps para variaveis de ambiente
- Secrets para credenciais
- Deployments para api e frontend
- Services e Ingress

## Performance

### Otimizacoes Implementadas

1. **Polars ao inves de Pandas** - 10x mais rapido para operacoes de DataFrame
2. **Cache L1/L2** - Evita deserializacao repetida de pickle
3. **Query compartilhada** - Dashboard e Participants usam mesma query (cache sharing)
4. **Filtros pre-computados** - Filter options calculadas durante cache write
5. **Arrow para BigQuery** - Transferencia zero-copy de dados
6. **React.memo e useCallback** - Evita re-renders desnecessarios no frontend

### Metricas Tipicas

| Operacao | Tempo (cache hit) | Tempo (cache miss) |
|----------|-------------------|-------------------|
| /dashboard | ~0.1s | ~5s |
| /participants | ~0.3s | ~5s |
| Filtro cascata | ~0.05s | N/A |

## Troubleshooting

### Cache nao atualiza

O botao "Atualizar" no frontend envia `bypass_cache=true` que:
1. Ignora cache L1 (memoria) e L2 (Redis/File)
2. Busca dados frescos do BigQuery
3. Substitui o cache antigo

### Login em loop

Verifique se:
1. CPF esta cadastrado na tabela de governanca
2. Usuario esta marcado como `active=true`
3. Cookies estao sendo aceitos pelo navegador

### Erros de permissao

1. Verifique logs do backend: `logs/api_*.log`
2. Confirme que o CPF no JWT (`preferred_username`) bate com a tabela de governanca
3. Para admins segmentados, verifique se possui IDs suficientes

## Licenca

Projeto interno da Prefeitura do Rio de Janeiro - Escritorio de Dados.
