from typing import Literal
from .utils.timeset import SetDays, SetMinutes
from pydantic import BaseModel, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from typing import Literal
from .utils.timeset import SetDays, SetMinutes
from pydantic import BaseModel, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class RedSettings(BaseModel):
    Trusted_proxies: str = "127.0.0.1"
    Host: str = "127.0.0.1"
    Port: int = 8000

class JWTSettings(BaseModel):
    Secret_key: SecretStr
    Algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    Access_token: int = SetMinutes(15)
    Refresh_token: int = SetDays(7)

    @field_validator("Secret_key")
    @classmethod
    def isTokenValidate(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value().strip()
        if (len(secret) < 32) or (secret.startswith("tu_")):
            raise ValueError(
                "JWTSETTINGS__Secret_Key debe tener al menos 32 caracteres y no puede ser la clave de ejemplo."
            ) 
        if len(set(secret)) < 8:
            raise ValueError(
                "JWTSETTINGS__Secret_Key tiene una entropía insuficiente (demasiados caracteres repetidos)."
            )
        return value

class CORSSettings(BaseModel):
    Allow_origins: list[str] = ["http://localhost:8080"]
    Allow_methods: list[str] = ["GET", "POST", "PATCH", "DELETE", "OPTIONS"]
    Allow_headers: list[str] = ["Content-Type", "Authorization"]
    Allow_credentials: bool = False   

    @field_validator("Allow_origins")
    @classmethod
    def validateCors(cls, value: list[str]) -> list[str]:
        if ("*" in value):
            raise ValueError(
                "CORSSETTINGS__Allow_origins debe contener orígenes especificos."
            )
        return value 

class VideoconferenciaSettings(BaseModel):
    Invitacion: int = SetMinutes(2)
    Stun_urls: list[str] = ["stun:stun.l.google.com:19302"]
    Turn_url: str | None = None
    Turn_username: str | None = None
    Turn_credential: str | None = None

    @field_validator("Invitacion")
    @classmethod
    def validateVideoExpira(cls, value: int) -> int:
        if (value < 1) or (value > 30):
            raise ValueError(
                "VIDEOCONFERENCIASETTINGS__Invitacion debe estar entre 1 y 30."
            )
        return value

class DatabaseSettings(BaseModel):
    Host: str = "db"
    Port: int = 5432
    User: str
    Password: str
    Db: str
    SQLecho: bool = False


class Configuration(BaseSettings):
    model_config = SettingsConfigDict(
        env_nested_delimiter = "__",
        case_sensitive = False,
        env_file = ".env",
        extra = "ignore"
    )

    Red: RedSettings = RedSettings()
    Jwt: JWTSettings = None  # type: ignore
    Cors: CORSSettings = CORSSettings()
    VideoConferencia: VideoconferenciaSettings = VideoconferenciaSettings()
    Database: DatabaseSettings = None  # type: ignore
