from sqlalchemy import URL
from config.config import Configuration

def mount_url_database(CONFIG: Configuration) -> str:
    return URL.create(
        "postgresql+psycopg2", 
        username = CONFIG.Database.User, 
        password = CONFIG.Database.Password, 
        host = CONFIG.Database.Host, 
        port = CONFIG.Database.Port, 
        database = CONFIG.Database.Db,
    )

def getLongHashPassword() -> int:
    return 8

_DUMMY_PASSWORD_CONSTANT = "cfs_dummy_password_timing_equalization_constant_32b"

def HashDummy() -> str:
    return _DUMMY_PASSWORD_CONSTANT

def ConfigBloq() -> tuple[int, int]:
    maximoIntentos = 5
    bloqueoMinutos = 15

    return maximoIntentos, bloqueoMinutos