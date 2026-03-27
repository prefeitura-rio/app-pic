from src.utils.infisical import getenv_or_action
import os

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
    action="ignore",
)


REDIS_URL = getenv_or_action(env_name="REDIS_URL", action="raise")
CACHE_TTL_SECONDS = int(getenv_or_action(env_name="CACHE_TTL_SECONDS", default="300"))
