from src.utils.infisical import getenv_or_action
import os

# if file .env exists, load it.
if os.path.exists("src/config/.env"):
    import dotenv

    dotenv.load_dotenv(dotenv_path="src/config/.env")


GCP_SERVICE_ACCOUNT_CREDENTIALS = getenv_or_action(
    "GCP_SERVICE_ACCOUNT_CREDENTIALS", action="raise"
)
GOOGLE_BIGQUERY_PAGE_SIZE = int(
    getenv_or_action("GOOGLE_BIGQUERY_PAGE_SIZE", default="100")
)
PIC_TOKEN = getenv_or_action("PIC_TOKEN", action="raise")
USE_LOCAL_API = (
    getenv_or_action("USE_LOCAL_API", default="false", action="ignore") == "true"
)
