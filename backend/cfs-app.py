
import argparse
import sys
from getpass import getpass

import uvicorn

from config.config import CONFIG


def main():
    parser = argparse.ArgumentParser(
        prog = "cfs-admin-auxiliary",
        description = "Herramienta de despliegue de CFS-Admin",
    )

    subparser = parser.add_subparsers(dest = "accion", required = True)
    subparser.add_parser("run-app", help = "Iniciar la API")
    subparser.add_parser("migrate-db", help = "Aplicar las migraciones de Alembic")
    subparser.add_parser("create-db", help = "Alias histórico de migrate-db")
    subparser.add_parser("create-admin", help = "Crear el administrador inicial")
    subparser.add_parser("seed-admin", help = "Crear o verificar el administrador predeterminado (admin/admincfs)")

    args = parser.parse_args()


    if (args.accion == "run-app"):
        uvicorn.run(
            "core.app:app",
            host = CONFIG.host_app,
            port = CONFIG.port_app,
            proxy_headers = True,
            forwarded_allow_ips = CONFIG.trusted_proxies,
        )

    elif (args.accion in ("migrate-db", "create-db")):
        from db.controller import migrateDb
        migrateDb()

    elif (args.accion == "create-admin"):
        from db.controller import createAdmin

        usuario = input("Usuario administrador: ").strip()
        nombre = input("Nombre completo: ").strip()
        password = getpass("Contraseña (mínimo 8 caracteres): ")
        confirmar = getpass("Repite la contraseña: ")

        if not usuario or not nombre:
            raise SystemExit(
                "[!] El usuario y el nombre son obligatorios."
            )

        if password != confirmar:
            raise SystemExit("[!] Las contraseñas no coinciden.")

        createAdmin(usuario, nombre, password)

    elif (args.accion == "seed-admin"):
        from db.controller import asegurarAdminPredeterminado
        asegurarAdminPredeterminado()

    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
