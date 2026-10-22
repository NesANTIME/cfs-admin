import sys
from db.template.base import Base
from typing import Generator
from config.config import MountUrlDb, CONFIG
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker, Session


engine = create_engine(MountUrlDb(), echo = CONFIG.postgres_sql_echo, pool_pre_ping = True)
SessionLocal = sessionmaker(bind = engine, autoflush = False, autocommit = False)



def getDb() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def createDb(verificar: bool = True):
    try:
        import db.template
        
        Base.metadata.create_all(engine)
        
        inspector = inspect(engine)
        tablas_existentes = inspector.get_table_names()

        print("[+] Tablas creadas / verificadas exitosamente:")
        for tabla in tablas_existentes:
            columnas = [col["name"] for col in inspector.get_columns(tabla)]
            print(f"    - {tabla}: ({', '.join(columnas)})")

    except Exception as exc:
        print(f"[!] Error al crear las tablas en la base de datos: {exc}", file=sys.stderr)
        raise exc


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
