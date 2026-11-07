
from sqlalchemy import URL
from .load import Configuration

CONFIG = Configuration()


def MountUrlDb() -> URL:
    return URL.create(
        drivername="postgresql+psycopg2",
        username=CONFIG.postgres_user,
        password=CONFIG.postgres_password,
        host=CONFIG.postgres_host,
        port=CONFIG.postgres_port,
        database=CONFIG.postgres_db,
        query={
            "sslmode": CONFIG.postgres_sslmode
        }
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
