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
    """Aplica todas las migraciones pendientes de Alembic y asegura el admin predeterminado."""
    from alembic import command
    from alembic.config import Config as AlembicConfig

    raiz = Path(__file__).resolve().parent.parent
    cfg = AlembicConfig(str(raiz / "alembic.ini"))
    cfg.set_main_option("script_location", str(raiz / "migrations"))

    command.upgrade(cfg, "head")
    print("[+] Base de datos actualizada hasta la última migración.")
    asegurarAdminPredeterminado()


def asegurarAdminPredeterminado(
    usuario: str = "admin",
    password: str = "admincfs",
    nombre: str = "Administrador",
) -> None:
    """Crea o actualiza el usuario administrador predeterminado (admin/admincfs)."""
    from core.security import hashearPassword, verifyPassword
    from db.template.rol import Rol
    from db.template.empleado import Empleado, TecnicoJefe
    from sqlalchemy import text

    with SessionLocal() as db:
        rol = db.execute(select(Rol).where(Rol.nombre == "Administrador")).scalar_one_or_none()
        if (rol is None):
            rol = Rol(nombre = "Administrador", descripcion = "Acceso total")
            db.add(rol)
            db.flush()

        rol_s = db.execute(select(Rol).where(Rol.nombre == "Administrador de Sede")).scalar_one_or_none()
        if (rol_s is None):
            db.add(Rol(nombre = "Administrador de Sede", descripcion = "Control exclusivo de una sede asignada"))
            db.flush()

        emp = db.execute(select(Empleado).where(Empleado.usuario == usuario)).scalar_one_or_none()
        if (emp is None):
            import uuid
            db.add(TecnicoJefe(
                nombre = nombre,
                usuario = usuario,
                contrasena_hash = hashearPassword(password),
                id_rol = rol.id_rol,
                nivel_acceso = 5,
                activo = True,
                uid_publico = str(uuid.uuid4()),
            ))
            db.commit()
            print(f"[+] Administrador predeterminado '{usuario}' creado exitosamente.")
        else:
            emp.nombre = nombre
            emp.id_rol = rol.id_rol
            emp.tipo = "tecnico_jefe"
            emp.activo = True
            emp.intentos_fallidos = 0
            emp.bloqueado_hasta = None
            if not getattr(emp, "uid_publico", None):
                import uuid
                emp.uid_publico = str(uuid.uuid4())


            db.flush()
            db.execute(
                text("INSERT INTO tecnicos (id_empleado) VALUES (:id) ON CONFLICT DO NOTHING"),
                {"id": emp.id_empleado},
            )
            db.execute(
                text("INSERT INTO tecnico_jefe (id_empleado, nivel_acceso) VALUES (:id, 5) ON CONFLICT (id_empleado) DO UPDATE SET nivel_acceso = 5"),
                {"id": emp.id_empleado},
            )

        # Sembrar dispositivos de ejemplo para la primera sede si existe y no tiene equipos
        from db.template.sede import Sede
        from db.template.dispositivo_red import DispositivoRed
        primera_sede = db.execute(select(Sede).order_by(Sede.id_sede.asc())).scalars().first()
        if (primera_sede is not None):
            hay_disp = db.execute(select(DispositivoRed).where(DispositivoRed.id_sede == primera_sede.id_sede)).scalars().first()
            if (hay_disp is None):
                db.add_all([
                    DispositivoRed(
                        nombre = "Router BGP Principal",
                        direccion_ip = "192.168.10.1",
                        mac = "00:1a:2b:3c:4d:01",
                        tipo = "Router",
                        estado = "en_linea",
                        id_sede = primera_sede.id_sede,
                    ),
                    DispositivoRed(
                        nombre = "Switch Core de Distribución",
                        direccion_ip = "192.168.10.2",
                        mac = "00:1a:2b:3c:4d:02",
                        tipo = "Switch",
                        estado = "en_linea",
                        id_sede = primera_sede.id_sede,
                    ),
                    DispositivoRed(
                        nombre = "Firewall Perimetral UTM",
                        direccion_ip = "192.168.10.254",
                        mac = "00:1a:2b:3c:4d:03",
                        tipo = "Firewall",
                        estado = "en_linea",
                        id_sede = primera_sede.id_sede,
                    ),
                ])

        db.commit()
        print(f"[+] Administrador predeterminado '{usuario}' verificado y sincronizado.")


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
