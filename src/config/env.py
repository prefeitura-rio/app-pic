import os

from src.utils.infisical import getenv_or_action

# if file .env exists, load it.
if os.path.exists("src/config/.env"):
    import dotenv

    dotenv.load_dotenv(dotenv_path="src/config/.env", override=True)

GCP_SERVICE_ACCOUNT_CREDENTIALS = getenv_or_action(
    env_name="GCP_SERVICE_ACCOUNT_CREDENTIALS",
    action="raise",
)
GOOGLE_BIGQUERY_PAGE_SIZE = int(
    getenv_or_action(env_name="GOOGLE_BIGQUERY_PAGE_SIZE", default="100")
)

BQ_PROJECT_ID = getenv_or_action(
    env_name="BQ_PROJECT_ID", default="rj-pic-dev", action="raise"
)
BQ_DATASET_ID = getenv_or_action(
    env_name="BQ_DATASET_ID", default="app_pequenos_cariocas", action="raise"
)
BQ_TABLE_ID_PARTICIPANTS_LISTAGEM = getenv_or_action(
    env_name="BQ_TABLE_ID_PARTICIPANTS_LISTAGEM",
    action="raise",
)
BQ_TABLE_ID_PARTICIPANTS_DEBUG = getenv_or_action(
    env_name="BQ_TABLE_ID_PARTICIPANTS_DEBUG",
    action="raise",
)
BQ_TABLE_ID_PARTICIPANTS_DEBUG_ORIGINS = getenv_or_action(
    env_name="BQ_TABLE_ID_PARTICIPANTS_DEBUG_ORIGINS",
    action="raise",
)
BQ_TABLE_ID_DASHBOARD = getenv_or_action(
    env_name="BQ_TABLE_ID_DASHBOARD",
    action="raise",
)
BQ_TABLE_ID_DATA_ACCESS = getenv_or_action(
    env_name="BQ_TABLE_ID_DATA_ACCESS",
    action="raise",
)
BQ_TABLE_ID_GEOSPATIAL_LAYERS = getenv_or_action(
    env_name="BQ_TABLE_ID_GEOSPATIAL_LAYERS",
    action="raise",
)

USE_LOCAL_API = (
    getenv_or_action(env_name="USE_LOCAL_API", default="false", action="ignore")
    == "true"
)

# RMI OAuth2 Configuration (Keycloak)
RMI_ISSUER = getenv_or_action(env_name="RMI_ISSUER", action="raise")
RMI_AUDIENCE = getenv_or_action(env_name="RMI_AUDIENCE", action="raise")
# JWKS URL with fallback to standard Keycloak endpoint
RMI_JWKS_URL = getenv_or_action(
    env_name="RMI_JWKS_URL",
    default=f"{RMI_ISSUER}/protocol/openid-connect/certs",
    action="raise",
)


REDIS_URL = getenv_or_action(env_name="REDIS_URL", action="raise")
CACHE_TTL_SECONDS = int(
    getenv_or_action(env_name="CACHE_TTL_SECONDS", default="300", action="raise")
)

# Frontend URL for CORS — list comma-separated URLs if needed (e.g. staging + prod)
FRONTEND_URL = getenv_or_action(
    env_name="FRONTEND_URL",
    action="raise",
)

# App-pic Postgres (identity + local mirror of data-proxy access_policy).
# Plain host:port connection through the cluster's shared `cloudsql-proxy`
# Service (in-cluster) or a `kubectl port-forward` of it (local dev).
APP_PIC_PG_HOST = getenv_or_action(env_name="APP_PIC_PG_HOST", action="raise")
APP_PIC_PG_PORT = int(
    getenv_or_action(env_name="APP_PIC_PG_PORT", default="5432", action="raise")
)
APP_PIC_PG_DB = getenv_or_action(env_name="APP_PIC_PG_DB", action="raise")
APP_PIC_PG_USER = getenv_or_action(env_name="APP_PIC_PG_USER", action="raise")
APP_PIC_PG_PW = getenv_or_action(env_name="APP_PIC_PG_PW", action="raise")

# Schema por ambiente — a mesma instância/banco Postgres é compartilhada
# entre staging e prod (ver plan.md seção 7), então o isolamento de dados
# entre ambientes é feito por schema Postgres (não por nome de tabela).
# Tabelas (`users`, `policy`) têm nome fixo; staging e prod devem apontar
# para schemas diferentes (ex: "staging"/"prod") via configuração de deploy.
APP_PIC_PG_SCHEMA = getenv_or_action(env_name="APP_PIC_PG_SCHEMA", action="raise")

# data-proxy (PostgREST) — writes to rls.access_policy for RLS enforcement.
DATA_PROXY_API_URL = getenv_or_action(env_name="DATA_PROXY_API_URL", action="raise")
DATA_PROXY_SCHEMA = getenv_or_action(
    env_name="DATA_PROXY_SCHEMA", default="app_pequenos_cariocas", action="raise"
)
DATA_PROXY_CLIENT_ID = getenv_or_action(env_name="DATA_PROXY_CLIENT_ID", action="raise")
DATA_PROXY_CLIENT_SECRET = getenv_or_action(
    env_name="DATA_PROXY_CLIENT_SECRET", action="raise"
)
DATA_PROXY_TOKEN_URL = getenv_or_action(env_name="DATA_PROXY_TOKEN_URL", action="raise")
