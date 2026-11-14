from fastapi import FastAPI
from config.load import CONFIG
from core.limiter import limiter
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(
    title = "cfs-admin-api",
    redoc_url = None,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins = CONFIG.Cors.Allow_origins,
    allow_headers = CONFIG.Cors.Allow_headers,
    allow_methods = CONFIG.Cors.Allow_methods,
    allow_credentials = CONFIG.Cors.Allow_credentials,
)

# ---
import db.template 
from api.login import router as router_login
from api.sedes import router as router_sedes
from api.servicios_usuario import router as router_servicios_usuario
from api.usuarios import router as router_usuarios
from api.perfil import router as router_perfil
from api.heartbeat import router as router_heartbeat
from api.contactos import router as router_contactos
from api.chat import router as router_chat
from api.videoconferencia import router as router_videoconferencia
# ---

app.include_router(router_login)
app.include_router(router_sedes)
app.include_router(router_servicios_usuario)
app.include_router(router_usuarios)
app.include_router(router_perfil)
app.include_router(router_heartbeat)
app.include_router(router_contactos)
app.include_router(router_chat)
app.include_router(router_videoconferencia)

