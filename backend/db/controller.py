from pathlib import Path
from typing import Generator
from config.load import CONFIG
from sqlalchemy import create_engine, select
from config.utils.db import mount_url_database
from sqlalchemy.orm import sessionmaker, Session

engine = create_engine(
    mount_url_database(CONFIG), 
    echo = CONFIG.Database.SQLecho, 
    pool_pre_ping = True
)

SessionLocal = sessionmaker(bind = engine, autoflush = False, autocommit = False)


def GetDatabase() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def MigrateDatabase() -> None:
    from alembic import command
    from alembic.config import Config as AlembicConfig

    raiz = Path(__file__).resolve().parent
    cfg = AlembicConfig(str(raiz / "alembic.ini"))
    cfg.set_main_option("script_location", str(raiz / "migrations"))

    command.upgrade(cfg, "head")
    print("[+] Base de datos actualizada hasta la última migración.")