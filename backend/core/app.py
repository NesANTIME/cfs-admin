from fastapi import FastAPI
from config.config import CONFIG
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from core.limiter import limiter
from fastapi.middleware.cors import CORSMiddleware

prod = CONFIG.app_env == "production"
app = FastAPI(
    title = "cfs-admin-api",
    docs_url = None if prod else "/docs",       # sin Swagger en producción
    redoc_url = None,
    openapi_url = None if prod else "/openapi.json",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---
import db.template  # registra todos los modelos
from api.login import router as router_login
# ---

app.add_middleware(
    CORSMiddleware,
    allow_origins = CONFIG.cors_allow_origins,
    allow_headers = CONFIG.cors_allow_headers,
    allow_methods = CONFIG.cors_allow_methods,
    allow_credentials = CONFIG.cors_allow_credentials,
)

app.include_router(router_login)
