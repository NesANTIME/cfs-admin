
from typing import Literal

from pydantic import ConfigDict, field_validator
from pydantic_settings import BaseSettings


class Configuration(BaseSettings):
    app_env: Literal["development", "production"] = "development"
    host_app: str = "127.0.0.1"
    port_app: int = 8000
    trusted_proxies: str = "127.0.0.1"

    jwt_secret_key: str
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    cors_allow_origins: list[str] = ["http://localhost:8080"]
    cors_allow_methods: list[str] = ["GET", "POST", "OPTIONS"]
    cors_allow_headers: list[str] = ["Content-Type", "Authorization"]
    cors_allow_credentials: bool = False

    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_sql_echo: bool = False



    @field_validator("jwt_secret_key")
    @classmethod
    def validateJwtSecret(cls, value: str) -> str:
        if (len(value.strip()) < 32) or (value.startswith("tu_")):
            raise ValueError("JWT_SECRET_KEY debe tener al menos 32 caracteres y no puede ser la clave de ejemplo.")
        return value


    @field_validator("cors_allow_origins")
    @classmethod
    def validateCors(cls, value: list[str]) -> list[str]:
        if ("*" in value):
            raise ValueError("CORS_ALLOW_ORIGINS debe contener orígenes específicos.")
        
        return value
