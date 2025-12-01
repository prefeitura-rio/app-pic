import time
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse
import os
import sys

from src.api import router as api_router
from src.core.middlewares.logging import LoggingMiddleware
from src.core.middlewares.static_cache import NoCacheStaticFilesMiddleware
from src.config import env
import logging

from src.utils.log import logger


class InterceptHandler(logging.Handler):
    def emit(self, record):
        logger_opt = logger.opt(depth=6, exception=record.exc_info)
        logger_opt.log(record.levelname, record.getMessage())


logging.basicConfig(handlers=[InterceptHandler()], level=logging.DEBUG)

for _log in ["uvicorn", "uvicorn.error", "fastapi"]:
    _logger = logging.getLogger(_log)
    _logger.handlers = [InterceptHandler()]
    _logger.propagate = False
    _logger.setLevel(logging.DEBUG)

for _log in ["httpcore._trace", "httpx._client"]:
    _logger = logging.getLogger(_log)
    _logger.handlers = [InterceptHandler()]
    _logger.propagate = False
    _logger.setLevel(logging.DEBUG)

_logger = logging.getLogger("src.services.letta")
_logger.handlers = [InterceptHandler()]
_logger.propagate = False
_logger.setLevel(logging.DEBUG)

# Configurar loguru
logger.configure(
    handlers=[
        {
            "sink": sys.stdout,
            "format": "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            "level": "INFO",
        },
        {
            "sink": "logs/api_{time}.log",
            "rotation": "1 day",
            "retention": "7 days",
            "format": "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
            "level": "INFO",
            "backtrace": True,
            "diagnose": True,
        },
    ]
)


app = FastAPI(
    title="PIC API",
    description="API que gerencia fluxo de dados do PIC da Prefeitura do Rio de Janeiro",
    version="0.1.0",
    servers=[
        {
            "url": (
                "http://localhost:8089" if env.USE_LOCAL_API else "https://example.com"
            ),
            "description": "Staging",
        }
    ],
    docs_url=None,
    redoc_url=None,
)

app.add_middleware(LoggingMiddleware)
app.add_middleware(NoCacheStaticFilesMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Erro não tratado: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno do servidor"},
    )


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "timestamp": time.time()}


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Documentação",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    )


app.include_router(api_router)
