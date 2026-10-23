#!/usr/bin/env python3

from __future__ import annotations

import getpass
import ipaddress
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _asegurar_dependencias() -> None:
    try:
        import argon2 
        import psycopg2
        return
    except ImportError:
        pass

    venv = ROOT / "backend" / "venv"
    venv_python = venv / "bin" / "python"
    if venv_python.exists() and Path(sys.prefix).resolve() != venv.resolve():
        try:
            os.execv(
                str(venv_python),
                [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]],
            )
        except OSError:
            pass

    print(
        "[!] Faltan las dependencias 'psycopg2' y 'argon2'.\n"
        "    Ejecuta el script con backend/venv/bin/python o dentro del contenedor api.",
        file=sys.stderr,
    )
    raise SystemExit(1)


_asegurar_dependencias()

import psycopg2 
from argon2 import PasswordHasher  

HASHER = PasswordHasher()


class ErrorCreacionUsuario(Exception):
    """Error controlado durante la creación del usuario."""


def valor_env(clave: str) -> str | None:
    if clave in os.environ:
        return os.environ[clave]

    archivo = ROOT / ".env"
    if not archivo.is_file():
        return None

    for linea in archivo.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        nombre, valor = linea.split("=", 1)
        if nombre.strip() != clave:
            continue
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in ("'", '"'):
            valor = valor[1:-1]
        return valor
    return None


def ip_contenedor_db() -> str | None:
    if not shutil.which("docker"):
        return None

    try:
        resultado = subprocess.run(
            ["docker", "compose", "ps", "-q", "db"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if resultado.returncode != 0:
            return None

        contenedores = resultado.stdout.strip().splitlines()
        if not contenedores:
            return None

        inspeccion = subprocess.run(
            [
                "docker",
                "inspect",
                "-f",
                "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}",
                contenedores[0],
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if inspeccion.returncode != 0:
            return None

        for candidata in inspeccion.stdout.split():
            try:
                ipaddress.ip_address(candidata)
            except ValueError:
                continue
            return candidata
    except (OSError, subprocess.SubprocessError):
        return None

    return None


def host_por_defecto() -> str:
    host_entorno = os.environ.get("POSTGRES_HOST")

    if Path("/.dockerenv").exists():
        return host_entorno or "db"

    if host_entorno == "db":
        try:
            socket.getaddrinfo("db", None)
        except OSError:
            pass
        else:
            return "db"

    if host_entorno and host_entorno not in ("localhost", "127.0.0.1", "db"):
        return host_entorno

    return ip_contenedor_db() or "127.0.0.1"


def preguntar(
    texto: str,
    defecto: str | None = None,
    *,
    secreto: bool = False,
) -> str:
    if secreto:
        sufijo = " [Enter para usar el valor configurado]" if defecto else ""
    else:
        sufijo = f" [{defecto}]" if defecto else ""

    while True:
        if secreto:
            valor = getpass.getpass(f"{texto}{sufijo}: ")
            if valor:
                return valor
        else:
            valor = input(f"{texto}{sufijo}: ").strip()
            if valor:
                return valor

        if defecto is not None:
            return defecto
        print("Este valor es obligatorio.")


def preguntar_puerto(defecto: str) -> int:
    while True:
        valor = preguntar("Puerto", defecto)
        try:
            puerto = int(valor)
        except ValueError:
            print("El puerto debe ser un número entero.")
            continue
        if 1 <= puerto <= 65535:
            return puerto
        print("El puerto debe estar entre 1 y 65535.")


def validar_usuario(usuario: str) -> str:
    if len(usuario) < 3:
        raise ErrorCreacionUsuario("El usuario debe tener al menos 3 caracteres.")
    if len(usuario) > 50:
        raise ErrorCreacionUsuario("El usuario no puede superar los 50 caracteres.")
    if any(caracter.isspace() for caracter in usuario):
        raise ErrorCreacionUsuario("El usuario no puede contener espacios.")
    return usuario


def validar_nombre(nombre: str) -> str:
    if not nombre:
        raise ErrorCreacionUsuario("El nombre completo es obligatorio.")
    if len(nombre) > 100:
        raise ErrorCreacionUsuario(
            "El nombre completo no puede superar los 100 caracteres."
        )
    return nombre


def validar_rol(rol: str) -> str:
    if not rol:
        raise ErrorCreacionUsuario("El rol no puede estar vacío.")
    if len(rol) > 50:
        raise ErrorCreacionUsuario("El rol no puede superar los 50 caracteres.")
    return rol


def conectar(
    host: str,
    puerto: int,
    base_datos: str,
    usuario: str,
    contrasena: str,
):
    return psycopg2.connect(
        host=host,
        port=puerto,
        dbname=base_datos,
        user=usuario,
        password=contrasena,
        connect_timeout=5,
        application_name="cfs-admin-crear-usuario",
    )


def crear_usuario(
    conexion,
    *,
    usuario: str,
    nombre: str,
    contrasena_hash: str,
    rol: str,
) -> int:
    with conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO roles (nombre, descripcion)
                VALUES (%s, %s)
                ON CONFLICT (nombre) DO NOTHING
                """,
                (rol, "Creado desde examples/crear_usuario.py"),
            )

            cursor.execute("SELECT id_rol FROM roles WHERE nombre = %s", (rol,))
            fila_rol = cursor.fetchone()
            if fila_rol is None:
                raise ErrorCreacionUsuario(f"No se encontró el rol '{rol}'.")

            cursor.execute(
                """
                INSERT INTO empleados (
                    nombre,
                    usuario,
                    contrasena_hash,
                    tipo,
                    activo,
                    intentos_fallidos,
                    id_rol
                )
                VALUES (%s, %s, %s, 'empleado', true, 0, %s)
                ON CONFLICT (usuario) DO NOTHING
                RETURNING id_empleado
                """,
                (nombre, usuario, contrasena_hash, fila_rol[0]),
            )
            fila = cursor.fetchone()
            if fila is None:
                cursor.execute(
                    "SELECT 1 FROM empleados WHERE usuario = %s",
                    (usuario,),
                )
                if cursor.fetchone() is not None:
                    raise ErrorCreacionUsuario(
                        f"El usuario '{usuario}' ya existe."
                    )
                raise ErrorCreacionUsuario(
                    "No se pudo insertar el usuario. Revisa el rol indicado."
                )

            return int(fila[0])


def main() -> int:
    print("\n=== Crear usuario en CFS-Admin ===\n")
    print("Conexión a PostgreSQL")

    host = preguntar("Host", host_por_defecto())
    puerto = preguntar_puerto(valor_env("POSTGRES_PORT") or "5432")
    base_datos = preguntar(
        "Base de datos",
        valor_env("POSTGRES_DB") or "cfs-admin",
    )
    usuario_db = preguntar(
        "Usuario de la base de datos",
        valor_env("POSTGRES_USER") or "cfs_user",
    )
    contrasena_db = preguntar(
        "Contraseña de la base de datos",
        valor_env("POSTGRES_PASSWORD") or None,
        secreto=True,
    )

    print("\nComprobando conexión... ", end="", flush=True)
    conexion = None
    try:
        conexion = conectar(
            host,
            puerto,
            base_datos,
            usuario_db,
            contrasena_db,
        )
        with conexion.cursor() as cursor:
            cursor.execute("SELECT 1")
    except psycopg2.Error as error:
        if conexion is not None:
            conexion.close()
        print("ERROR", flush=True)
        print(
            f"[!] No se pudo conectar a PostgreSQL: {error}",
            file=sys.stderr,
        )
        print(
            "    Verifica las credenciales y que el stack esté levantado "
            "(docker compose up -d).",
            file=sys.stderr,
        )
        return 1

    print("OK\n")

    try:
        print("Datos del nuevo usuario")
        usuario = validar_usuario(preguntar("Usuario (mínimo 3 caracteres)"))
        nombre = validar_nombre(preguntar("Nombre completo", usuario))
        rol = validar_rol(preguntar("Rol", "Usuario"))

        contrasena = preguntar(
            "Contraseña (mínimo 8 caracteres)",
            secreto=True,
        )
        if len(contrasena) < 8:
            raise ErrorCreacionUsuario(
                "La contraseña debe tener al menos 8 caracteres."
            )

        confirmacion = preguntar("Repite la contraseña", secreto=True)
        if contrasena != confirmacion:
            raise ErrorCreacionUsuario("Las contraseñas no coinciden.")

        print("\nGenerando hash Argon2... ", end="", flush=True)
        try:
            contrasena_hash = HASHER.hash(contrasena)
        except Exception as error:
            print("ERROR", flush=True)
            print(
                f"[!] No se pudo generar el hash de la contraseña: {error}",
                file=sys.stderr,
            )
            return 1
        print("OK")

        print(
            f'Creando rol "{rol}" e insertando usuario "{usuario}"... ',
            end="",
            flush=True,
        )
        try:
            id_empleado = crear_usuario(
                conexion,
                usuario=usuario,
                nombre=nombre,
                contrasena_hash=contrasena_hash,
                rol=rol,
            )
        except ErrorCreacionUsuario as error:
            print("ERROR", flush=True)
            print(f"[!] {error}", file=sys.stderr)
            return 1
        except psycopg2.Error as error:
            print("ERROR", flush=True)
            print(f"[!] Error de PostgreSQL: {error}", file=sys.stderr)
            return 1
        print("OK")
    except ErrorCreacionUsuario as error:
        print(f"\n[!] {error}", file=sys.stderr)
        return 1
    finally:
        conexion.close()

    print(f"\n[+] Usuario creado correctamente (id={id_empleado}).")
    print(f"    Usuario: {usuario}")
    print(f"    Nombre:  {nombre}")
    print(f"    Rol:     {rol}")
    print("    Tipo:    empleado")
    print("\nLa contraseña se almacenó hasheada con Argon2.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EOFError, KeyboardInterrupt):
        print("\n[!] Cancelado.", file=sys.stderr)
        raise SystemExit(130)