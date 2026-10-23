from typing import Generator
from pathlib import Path
from config.config import MountUrlDb, CONFIG
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, Session


engine = create_engine(MountUrlDb(), echo = CONFIG.postgres_sql_echo, pool_pre_ping = True)
SessionLocal = sessionmaker(bind = engine, autoflush = False, autocommit = False)



def getDb() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrateDb() -> None:
    """Aplica todas las migraciones pendientes de Alembic."""
    from alembic import command
    from alembic.config import Config as AlembicConfig

    raiz = Path(__file__).resolve().parent.parent
    cfg = AlembicConfig(str(raiz / "alembic.ini"))
    cfg.set_main_option("script_location", str(raiz / "migrations"))

    command.upgrade(cfg, "head")
    print("[+] Base de datos actualizada hasta la última migración.")


def createAdmin(usuario: str, nombre: str, password: str) -> None:
    from core.security import hashearPassword
    from db.template.rol import Rol
    from db.template.empleado import Empleado, TecnicoJefe

    with SessionLocal() as db:
        if db.execute(select(Empleado).where(Empleado.usuario == usuario)).scalar_one_or_none():
            raise SystemExit(f"[!] El usuario '{usuario}' ya existe.")

        rol = db.execute(select(Rol).where(Rol.nombre == "Administrador")).scalar_one_or_none()
        if rol is None:
            rol = Rol(nombre = "Administrador", descripcion = "Acceso total")
            db.add(rol)
            db.flush()

        db.add(TecnicoJefe(
            nombre = nombre, usuario = usuario, contrasena_hash = hashearPassword(password),
            id_rol = rol.id_rol, nivel_acceso = 5,
        ))
        db.commit()
        print(f"[+] Administrador '{usuario}' creado.")
