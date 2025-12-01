from src.utils.infisical import getenv_or_action
import os

# if file .env exists, load it.
if os.path.exists("src/config/.env"):
    import dotenv

    dotenv.load_dotenv(dotenv_path="src/config/.env")


GCP_SERVICE_ACCOUNT_CREDENTIALS = getenv_or_action(
    "GCP_SERVICE_ACCOUNT_CREDENTIALS", action="ignore", default=None
)
GOOGLE_BIGQUERY_PAGE_SIZE = int(
    getenv_or_action("GOOGLE_BIGQUERY_PAGE_SIZE", default="100")
)

PIC_TOKEN = getenv_or_action("PIC_TOKEN", action="ignore", default=None)
USE_LOCAL_API = (
    getenv_or_action("USE_LOCAL_API", default="false", action="ignore") == "true"
)

# Authentik OAuth2 Configuration
AUTHENTIK_JWKS_URL = getenv_or_action("AUTHENTIK_JWKS_URL", action="raise")
AUTHENTIK_ISSUER = getenv_or_action("AUTHENTIK_ISSUER", action="raise")
AUTHENTIK_AUDIENCE = getenv_or_action("AUTHENTIK_AUDIENCE", action="raise")
