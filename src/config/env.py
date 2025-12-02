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

USE_LOCAL_API = (
    getenv_or_action(env_name="USE_LOCAL_API", default="false", action="ignore")
    == "true"
)

# Authentik OAuth2 Configuration
AUTHENTIK_JWKS_URL = getenv_or_action(env_name="AUTHENTIK_JWKS_URL", action="raise")
AUTHENTIK_ISSUER = getenv_or_action(env_name="AUTHENTIK_ISSUER", action="raise")
AUTHENTIK_AUDIENCE = getenv_or_action(env_name="AUTHENTIK_AUDIENCE", action="raise")


REDIS_URL = getenv_or_action(env_name="REDIS_URL", action="raise")
CACHE_TTL_SECONDS = int(getenv_or_action(env_name="CACHE_TTL_SECONDS", default="300"))
