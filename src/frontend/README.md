# Frontend - Programa Pequenos Cariocas

Dashboard integrado para visualização e gestão de dados do programa Primeira Infância da Prefeitura do Rio de Janeiro.

## 📋 Índice

- [Stack Tecnológica](#-stack-tecnológica)
- [Arquitetura](#-arquitetura)
- [Autenticação](#-autenticação)
- [Estrutura de Pastas](#-estrutura-de-pastas)
- [Componentes Principais](#-componentes-principais)
- [Configuração](#-configuração)
- [Desenvolvimento](#-desenvolvimento)
- [Deploy](#-deploy)

---

## 🚀 Stack Tecnológica

### Core
- **Next.js 16** (App Router + Server Components)
- **React 19** com Server Actions
- **TypeScript** para type safety
- **Turbopack** para build ultra-rápido

### UI/Styling
- **Tailwind CSS** para estilização
- **shadcn/ui** para componentes acessíveis
- **Lucide Icons** para ícones
- **next-themes** para dark/light mode

### Data Fetching & State
- **TanStack Query (React Query)** para cache e estado assíncrono
- **Server-side data fetching** com cookies httpOnly

### Autenticação
- **OAuth2/OIDC** custom implementation (sem NextAuth)
- **Keycloak** (Identidade Carioca + GovBR)
- **JWT tokens** em cookies httpOnly
- **Automatic token refresh** em background

---

## 🏗️ Arquitetura

### Arquitetura Híbrida (Server + Client Components)

```
┌─────────────────────────────────────────────────────────────┐
│                     Next.js App Router                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐      ┌──────────────┐                    │
│  │ Server Pages │──────│ Server API   │                    │
│  │ (app/page.tsx)│      │ (/api/*)     │                    │
│  └──────────────┘      └──────────────┘                    │
│         │                      │                             │
│         │                      │                             │
│         ▼                      ▼                             │
│  ┌──────────────────────────────────────┐                   │
│  │     Client Components                │                   │
│  │  - DashboardClient (orquestrador)    │                   │
│  │  - OverviewTab (métricas)            │                   │
│  │  - ProfessionalTab (busca individual)│                   │
│  └──────────────────────────────────────┘                   │
│         │                                                    │
│         │ TanStack Query (cache + refetch)                  │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────────────────────────────────┐                   │
│  │      API Service Layer               │                   │
│  │  - Automatic token refresh           │                   │
│  │  - Request retry on 401              │                   │
│  └──────────────────────────────────────┘                   │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────────────────────────────────┐                   │
│  │      Proxy API (/api/proxy/*)        │                   │
│  │  - Reads tokens from cookies         │                   │
│  │  - Forwards to backend with auth     │                   │
│  └──────────────────────────────────────┘                   │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────────────────────────────────┐                   │
│  │    Backend API (FastAPI)             │                   │
│  │    http://localhost:8089              │                   │
│  └──────────────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

### Fluxo de Dados

1. **Inicialização da Página**
   - Server Component (`app/page.tsx`) lê cookies
   - Extrai informações do usuário do JWT
   - Passa `userName` para Client Component

2. **Dashboard Client (Orquestrador)**
   - Gerencia estado de abas (Overview / Professional)
   - Mantém filtros separados para cada aba
   - Usa TanStack Query para cache inteligente

3. **TanStack Query Strategy**
   - **Overview tab**: Query key `['dashboard', filters]`
   - **Professional tab**: Query key `['participants', filters, page]`
   - Cache de 5 minutos (`staleTime`)
   - `placeholderData` evita "piscar" durante loading

4. **API Service Layer**
   - Intercepta todos os erros 401
   - Tenta refresh automático via `/api/auth/refresh`
   - Se sucesso: repete requisição original
   - Se falha: redireciona para `/login`

5. **Proxy API**
   - Lê tokens dos cookies (server-side)
   - Adiciona header `Authorization: Bearer <token>`
   - Forward para backend FastAPI
   - Retorna resposta para cliente

---

## 🔐 Autenticação

### Implementação Custom OAuth2 (sem NextAuth)

#### Por que Custom?
NextAuth v5 tinha problemas com validação de nonce do Keycloak. Implementamos OAuth2 manualmente baseado no padrão OIDC.

### Fluxo de Autenticação Completo

```
┌─────────────────────────────────────────────────────────────────┐
│                    1. LOGIN INICIADO                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Usuário clica "Sign In"                                        │
│         │                                                        │
│         ▼                                                        │
│  POST /login (Server Action)                                    │
│         │                                                        │
│         ▼                                                        │
│  Redirect to Keycloak:                                          │
│  https://auth-idriohom.../auth                                  │
│    ?client_id=app-pic                                          │
│    &redirect_uri=http://localhost:3000/api/auth/callback/rmi   │
│    &response_type=code                                          │
│    &scope=openid+profile+email                                  │
│    &kc_idp_hint=govbr    ← Pula Identidade Carioca            │
│    &prompt=login          ← Força re-autenticação              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                 2. AUTENTICAÇÃO NO GOVBR                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Keycloak redireciona para GovBR                                │
│         │                                                        │
│         ▼                                                        │
│  https://sso.staging.acesso.gov.br/login                        │
│         │                                                        │
│         ▼                                                        │
│  Usuário insere CPF + senha                                     │
│         │                                                        │
│         ▼                                                        │
│  GovBR valida e retorna para Keycloak                          │
│         │                                                        │
│         ▼                                                        │
│  Keycloak gera authorization code                              │
│         │                                                        │
│         ▼                                                        │
│  Redirect to callback:                                          │
│  http://localhost:3000/api/auth/callback/rmi?code=xxx          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                  3. EXCHANGE CODE FOR TOKENS                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  GET /api/auth/callback/rmi?code=xxx                            │
│         │                                                        │
│         ▼                                                        │
│  POST to Keycloak token endpoint:                              │
│    - client_id + client_secret                                 │
│    - grant_type=authorization_code                             │
│    - code=xxx                                                   │
│         │                                                        │
│         ▼                                                        │
│  Keycloak retorna:                                             │
│    {                                                            │
│      access_token: "ey...",    (10 horas)                      │
│      refresh_token: "ey...",   (30 min idle)                   │
│      id_token: "ey...",        (10 horas)                      │
│      expires_in: 35924,                                        │
│      refresh_expires_in: 1800                                  │
│    }                                                            │
│         │                                                        │
│         ▼                                                        │
│  Salva tokens em httpOnly cookies                             │
│         │                                                        │
│         ▼                                                        │
│  Redirect to /                                                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                   4. SESSÃO ATIVA                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Usuário navega pelo dashboard                                  │
│         │                                                        │
│         ▼                                                        │
│  Middleware verifica JWT em cada request                       │
│         │                                                        │
│         ├─ Token válido? ────────────► Permite acesso          │
│         │                                                        │
│         └─ Token expirado? ──────────► Redirect /login         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│              5. REFRESH AUTOMÁTICO (Token Expira)                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  API retorna 401 Unauthorized                                   │
│         │                                                        │
│         ▼                                                        │
│  apiService detecta 401                                         │
│         │                                                        │
│         ▼                                                        │
│  POST /api/auth/refresh                                         │
│         │                                                        │
│         ▼                                                        │
│  Server lê refresh_token do cookie                             │
│         │                                                        │
│         ▼                                                        │
│  POST to Keycloak:                                             │
│    - grant_type=refresh_token                                  │
│    - refresh_token=xxx                                         │
│         │                                                        │
│         ├─ Sucesso? ──────────────────┐                        │
│         │                               │                        │
│         ▼                               ▼                        │
│  Atualiza cookies             Repete request original          │
│  com novos tokens                     │                         │
│                                        │                         │
│                                        ▼                         │
│                           Usuário continua navegando            │
│                           (nem percebe que houve refresh)       │
│         │                                                        │
│         └─ Falha? ────────────► Redirect /login                │
│            (refresh_token expirou após 30min idle)             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                       6. LOGOUT                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Usuário clica "Sair"                                           │
│         │                                                        │
│         ▼                                                        │
│  window.location.href = "/api/auth/logout"                     │
│         │                                                        │
│         ▼                                                        │
│  Server lê refresh_token                                        │
│         │                                                        │
│         ▼                                                        │
│  POST to Keycloak logout (se tiver refresh_token)              │
│         │                                                        │
│         ▼                                                        │
│  Limpa todos os cookies                                         │
│         │                                                        │
│         ▼                                                        │
│  Redirect to Keycloak logout:                                  │
│  https://auth-idriohom.../logout                               │
│    ?post_logout_redirect_uri=http://localhost:3000/login       │
│    &id_token_hint=xxx                                          │
│         │                                                        │
│         ▼                                                        │
│  Keycloak limpa sessão SSO (incluindo GovBR)                  │
│         │                                                        │
│         ▼                                                        │
│  Redirect to /login                                             │
│                                                                  │
│  Próximo login SEMPRE pede credenciais (prompt=login)          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Endpoints de Autenticação

#### `POST /login` (Server Action)
- Constrói URL de autorização do Keycloak
- Parâmetros importantes:
  - `kc_idp_hint=govbr` - pula seleção do Identidade Carioca
  - `prompt=login` - força re-autenticação mesmo com SSO ativa
- Redireciona navegador para Keycloak

#### `GET /api/auth/callback/rmi`
- Recebe `code` do Keycloak
- Troca code por tokens (access + refresh + id)
- Salva tokens em cookies httpOnly
- Redireciona para `/`

#### `POST /api/auth/refresh`
- Usa refresh_token para obter novos tokens
- Atualiza cookies com novos valores
- Retorna 401 se refresh_token inválido

#### `GET /api/auth/logout`
- Chama endpoint de logout do Keycloak (server-side)
- Limpa todos os cookies
- Redireciona navegador para logout do Keycloak (client-side)
- Keycloak limpa SSO e redireciona para `/login`

### Tokens e Cookies

| Cookie | Conteúdo | Expiração | Uso |
|--------|----------|-----------|-----|
| `access_token` | JWT do Keycloak | 10 horas | Enviado ao backend nas requisições |
| `id_token` | JWT com dados do usuário | 10 horas | Lido no servidor para mostrar nome |
| `refresh_token` | Token opaco | 30 min idle | Renovar access_token automaticamente |

### Middleware de Proteção

**Arquivo:** `middleware.ts`

- Roda em **todas** as rotas exceto `/login` e `/api/auth/*`
- Verifica se existe `access_token` no cookie
- Valida se o token não expirou (usando `jwt-decode`)
- Se inválido ou expirado: redirect para `/login`

---

## 📁 Estrutura de Pastas

```
src/frontend/
├── app/
│   ├── api/
│   │   ├── auth/
│   │   │   ├── callback/
│   │   │   │   └── rmi/
│   │   │   │       └── route.ts          # OAuth2 callback
│   │   │   ├── logout/
│   │   │   │   └── route.ts              # Logout handler
│   │   │   └── refresh/
│   │   │       └── route.ts              # Token refresh
│   │   └── proxy/
│   │       └── [...path]/
│   │           └── route.ts              # API proxy (GET/POST/PUT/DELETE)
│   │
│   ├── components/
│   │   ├── ui/                           # shadcn/ui components
│   │   │   ├── button.tsx
│   │   │   ├── card.tsx
│   │   │   ├── dialog.tsx
│   │   │   ├── select.tsx
│   │   │   ├── tabs.tsx
│   │   │   └── ...
│   │   │
│   │   ├── DashboardClient.tsx           # ⭐ Orquestrador principal
│   │   ├── DashboardHeader.tsx           # Header com logo + user menu
│   │   ├── OverviewTab.tsx               # Tab de visão geral (métricas)
│   │   ├── ProfessionalTab.tsx           # Tab de busca individual
│   │   ├── UserAreaDialog.tsx            # Dialog de área do usuário
│   │   ├── ThemeToggle.tsx               # Toggle dark/light mode
│   │   └── ParticipantDetailsDialog.tsx  # Modal de detalhes do participante
│   │
│   ├── services/
│   │   └── api.ts                        # ⭐ API service layer
│   │
│   ├── utils/
│   │   └── jwt-utils.ts                  # JWT decode e validação
│   │
│   ├── login/
│   │   └── page.tsx                      # Página de login
│   │
│   ├── types.ts                          # TypeScript types
│   ├── layout.tsx                        # Root layout
│   ├── page.tsx                          # Home page (Server Component)
│   └── globals.css                       # Tailwind globals
│
├── middleware.ts                         # ⭐ Route protection
├── .env.local                            # Environment variables (gitignored)
├── .env.example                          # Example env vars
├── next.config.ts                        # Next.js config
├── tailwind.config.ts                    # Tailwind config
├── tsconfig.json                         # TypeScript config
└── package.json                          # Dependencies
```

---

## 🧩 Componentes Principais

### DashboardClient (Orquestrador)

**Arquivo:** `app/components/DashboardClient.tsx`

**Responsabilidades:**
- Gerencia estado de abas (Overview / Professional)
- Mantém filtros separados para cada aba
- Usa TanStack Query para cache e refetch automático
- Detecta erros 401 e redireciona para login

**Queries:**
```typescript
// Query 1: Dashboard (Visão Geral)
useQuery({
  queryKey: ['dashboard', overviewFilters],
  queryFn: () => apiService.getDashboard(overviewFilters),
  staleTime: 5 * 60 * 1000, // 5 minutos
})

// Query 2: Participants (Busca Individual)
useQuery({
  queryKey: ['participants', professionalFilters, professionalPage],
  queryFn: () => apiService.getParticipants(professionalFilters, professionalPage, 20),
  staleTime: 5 * 60 * 1000,
})
```

**Otimizações:**
- `placeholderData: (prev) => prev` - evita "piscar" durante loading
- `staleTime: 5min` - reduz chamadas desnecessárias
- Queries só rodam quando aba está ativa
- Troca de aba usa cache (não faz nova chamada)

### OverviewTab (Visão Geral)

**Arquivo:** `app/components/OverviewTab.tsx`

**Mostra:**
- Cards de métricas principais (total, ativos, inativos, etc.)
- Filtros dinâmicos (bairro, CRE, CRAS, escola, etc.)
- Gráficos e visualizações agregadas

**Comportamento:**
- Ao mudar filtro → nova chamada à API
- Backend recalcula métricas com os filtros aplicados
- TanStack Query gerencia loading/error states

### ProfessionalTab (Busca Individual)

**Arquivo:** `app/components/ProfessionalTab.tsx`

**Mostra:**
- Tabela paginada de participantes
- Filtros dinâmicos (mesmos do Overview)
- Paginação server-side
- Detalhes do participante em modal

**Comportamento:**
- Ao mudar filtro → reset para página 1
- Ao mudar página → mantém filtros atuais
- Click em participante → abre modal com detalhes

### API Service Layer

**Arquivo:** `app/services/api.ts`

**Métodos:**
- `getDashboard(filters)` - busca métricas do dashboard
- `getParticipants(filters, page, pageSize)` - busca participantes paginados
- `getParticipantDetails(cpf)` - busca detalhes de um participante
- `getParticipantProtocols(cpf)` - busca protocolos de um participante

**Funcionalidades:**
- ✅ Automatic retry on 401 (após token refresh)
- ✅ Token refresh transparente
- ✅ Logging detalhado
- ✅ Error handling robusto

**Fluxo de Retry:**
```typescript
1. Requisição retorna 401
2. Tenta refresh (POST /api/auth/refresh)
3. Se sucesso: repete requisição original
4. Se falha: redireciona para /login
```

---

## ⚙️ Configuração

### Variáveis de Ambiente

**Arquivo:** `.env.local` (criar baseado no `.env.example`)

```bash
# Application URL
NEXTAUTH_URL=http://localhost:3000

# RMI OAuth2 Configuration (Keycloak) - all server-side
RMI_CLIENT_ID=app-pic
RMI_CLIENT_SECRET=your-client-secret-here
RMI_ISSUER=https://auth-idriohom.apps.rio.gov.br/auth/realms/idrio_cidadao

# Backend API URL (used by /api/proxy)
API_URL=http://localhost:8089
```

**⚠️ IMPORTANTE:**
- Todas as variáveis são **server-side only**
- Nunca use `NEXT_PUBLIC_` prefix (expõe no cliente)
- Tokens e secrets **sempre** em cookies httpOnly

### Infisical (Produção)

Em produção, as variáveis são gerenciadas pelo **Infisical** (secrets manager).

**Secrets necessários:**
- `RMI_ISSUER` - URL do Keycloak
- `RMI_CLIENT_ID` - Client ID do Keycloak
- `RMI_CLIENT_SECRET` - Client Secret do Keycloak
- `API_URL` - URL da API backend
- `NEXTAUTH_URL` - URL pública da aplicação

---

## 💻 Desenvolvimento

### Instalação

```bash
# Instalar dependências
npm install

# Copiar exemplo de .env
cp .env.example .env.local

# Editar .env.local com valores corretos
vim .env.local
```

### Rodar em Dev

```bash
npm run dev
```

Aplicação estará disponível em: http://localhost:3000

### Build para Produção

```bash
npm run build
npm start
```

### Lint

```bash
npm run lint
```

### Type Check

```bash
npx tsc --noEmit
```

---

## 🚢 Deploy

### Dockerfile Multi-Stage

```dockerfile
# Stage 1: Build
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .

# Build com variáveis de ambiente
ARG NEXTAUTH_URL
ARG RMI_CLIENT_ID
ARG RMI_CLIENT_SECRET
ARG RMI_ISSUER
ARG API_URL

ENV NEXTAUTH_URL=$NEXTAUTH_URL
ENV RMI_CLIENT_ID=$RMI_CLIENT_ID
ENV RMI_CLIENT_SECRET=$RMI_CLIENT_SECRET
ENV RMI_ISSUER=$RMI_ISSUER
ENV API_URL=$API_URL

RUN npm run build

# Stage 2: Production
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
```

### Kubernetes Deployment

**Configurações importantes:**

1. **Infisical Secret Injection**
```yaml
annotations:
  secrets.infisical.com/auto-reload: "true"
```

2. **Health Checks**
```yaml
livenessProbe:
  httpGet:
    path: /api/health
    port: 3000
  initialDelaySeconds: 30
  periodSeconds: 10
```

3. **Resource Limits**
```yaml
resources:
  requests:
    memory: "256Mi"
    cpu: "100m"
  limits:
    memory: "512Mi"
    cpu: "500m"
```

---

## 📚 Referências

### Documentação
- [Next.js 15 Docs](https://nextjs.org/docs)
- [TanStack Query](https://tanstack.com/query/latest)
- [Tailwind CSS](https://tailwindcss.com/docs)
- [shadcn/ui](https://ui.shadcn.com/)

### OAuth2/OIDC
- [RFC 6749 - OAuth 2.0](https://datatracker.ietf.org/doc/html/rfc6749)
- [OpenID Connect Spec](https://openid.net/specs/openid-connect-core-1_0.html)
- [Keycloak Documentation](https://www.keycloak.org/documentation)

### Padrões de Código
- Server Components para páginas públicas
- Client Components apenas quando necessário (interatividade)
- Server Actions para mutations
- API Routes para proxy e autenticação
- TypeScript strict mode

---

## 🤝 Contribuindo

### Padrões de Commit

```bash
feat: adiciona nova funcionalidade
fix: corrige bug
docs: atualiza documentação
style: formatação de código
refactor: refatoração sem mudança de funcionalidade
test: adiciona ou atualiza testes
chore: tarefas de manutenção
```

### Code Review Checklist

- [ ] TypeScript sem erros
- [ ] Lint passing
- [ ] Componentes documentados
- [ ] Loading states implementados
- [ ] Error handling robusto
- [ ] Acessibilidade (ARIA labels)
- [ ] Responsivo (mobile-first)
- [ ] Performance (React Query cache)

---

## 📞 Suporte

Para dúvidas ou problemas:
- **Repositório:** [github.com/prefeitura-rio/app-pic](https://github.com/prefeitura-rio/app-pic)
- **Issues:** Use GitHub Issues
- **Documentação Backend:** `../README.md`

---

**Desenvolvido com ❤️ pela equipe de Dados da Prefeitura do Rio de Janeiro**
