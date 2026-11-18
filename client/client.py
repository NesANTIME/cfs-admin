#!/usr/bin/env python3
"""
CFS-Admin · Programa Cliente de Dispositivo de Red
===================================================
Genera información falsa de hardware de red (conforme a los campos requeridos por la tabla),
crea un UID con la dirección IP embebida de manera ofuscada y establece una contraseña local.

Al ejecutarse:
- Expone un servicio HTTP local en el puerto 8500 para responder a verificaciones de vinculación y desvinculación.
- Si otra sede intenta registrarlo mientras ya está vinculado, declina automáticamente el registro.
- Soporta monitoreo en tiempo real (heartbeat y telemetría de CPU, memoria y uptime).
- Al recibir la desvinculación (con contraseña), se libera para permitir ser enlazado por otra sede.
"""

from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
import random
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

STATE_FILE = Path(__file__).resolve().parent / "device_state.json"
DEFAULT_PORT = 8500
DEFAULT_API_URL = "http://localhost:8080/api"

# Catálogo para generación de datos falsos realistas
NOMBRES_EQUIPOS = [
    ("Router Core Troncal BGP", "Router"),
    ("Switch de Distribución Cisco Catalyst 3850", "Switch"),
    ("Firewall Perimetral UTM FortiGate 60F", "Firewall"),
    ("Access Point Empresarial UniFi U6-Pro", "Access Point"),
    ("Switch de Acceso Gigabit EdgeSwitch 24", "Switch"),
    ("Router de Borde MikroTik Cloud Core 1036", "Router"),
    ("Servidor de Monitoreo & Syslog Local", "Servidor"),
]


def detectar_ip_local() -> str:
    """Detecta la IP local de la máquina en la red LAN o retorna 127.0.0.1 como fallback."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No realiza conexión real hacia internet, solo determina la interfaz saliente
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def generar_mac_aleatoria() -> str:
    """Genera una dirección MAC con formato hexadecimal válido para PostgreSQL."""
    octetos = [0x00, 0x1A, 0x2B] + [random.randint(0x00, 0xFF) for _ in range(3)]
    return ":".join(f"{b:02X}" for b in octetos)


def ofuscar_ip(ip: str) -> str:
    """Ofusca la IP en formato base64 URL-safe sin padding."""
    return base64.urlsafe_b64encode(ip.encode("utf-8")).decode("ascii").rstrip("=")


def desofuscar_ip(token: str) -> str | None:
    """Recupera la IP a partir del token ofuscado."""
    try:
        padding = 4 - len(token) % 4
        if padding and padding != 4:
            token += "=" * padding
        return base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
    except Exception:
        return None


def generar_uid(ip: str) -> str:
    """Genera un identificador único con la IP ofuscada en su estructura:
    UID-<prefijo_aleatorio>-<ip_ofuscada>-<checksum_sha256>
    """
    prefijo = hashlib.sha256(os.urandom(16)).hexdigest()[:6]
    ip_encoded = ofuscar_ip(ip)
    checksum = hashlib.sha256((ip + prefijo).encode("utf-8")).hexdigest()[:6]
    return f"UID-{prefijo}-{ip_encoded}-{checksum}"


class EstadoDispositivo:
    def __init__(self):
        self.lock = threading.Lock()
        self.datos = self.cargar_o_crear()

    def cargar_o_crear(self, forzar_nuevo: bool = False) -> dict:
        if not forzar_nuevo and STATE_FILE.exists():
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        nombre_sug, tipo_sug = random.choice(NOMBRES_EQUIPOS)
        ip = detectar_ip_local()
        mac = generar_mac_aleatoria()
        uid = generar_uid(ip)
        pass_default = "cfs12345"

        nuevo = {
            "uid": uid,
            "nombre": nombre_sug,
            "tipo": tipo_sug,
            "direccion_ip": ip,
            "mac": mac,
            "contrasena": pass_default,
            "contrasena_hash": hashlib.sha256(pass_default.encode("utf-8")).hexdigest(),
            "vinculado": False,
            "id_sede": None,
            "sede_nombre": None,
            "creado_en": datetime.now(timezone.utc).isoformat(),
            "descripcion": f"Equipo {tipo_sug} simulado por CFS-Client en host {socket.gethostname()}",
            "puerto": DEFAULT_PORT,
            "api_url": DEFAULT_API_URL,
        }
        self.guardar_archivo(nuevo)
        return nuevo

    def guardar_archivo(self, datos: dict) -> None:
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(datos, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[!] Error al persistir estado en {STATE_FILE}: {e}")

    def obtener(self) -> dict:
        with self.lock:
            return dict(self.datos)

    def actualizar(self, **kwargs) -> dict:
        with self.lock:
            self.datos.update(kwargs)
            self.guardar_archivo(self.datos)
            return dict(self.datos)


estado_global = EstadoDispositivo()


# ---------------------------------------------------------------------------
# Servidor HTTP embebido en el dispositivo cliente
# ---------------------------------------------------------------------------

class ClienteHTTPHandler(BaseHTTPRequestHandler):
    def _enviar_json(self, codigo: int, datos: dict):
        contenido = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(contenido)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(contenido)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        ruta = urlparse(self.path).path
        d = estado_global.obtener()

        if ruta == "/status" or ruta == "/":
            # Métricas simuladas en tiempo real para monitoreo
            self._enviar_json(200, {
                "online": True,
                "uid": d["uid"],
                "nombre": d["nombre"],
                "tipo": d["tipo"],
                "direccion_ip": d["direccion_ip"],
                "mac": d["mac"],
                "vinculado": d["vinculado"],
                "id_sede": d.get("id_sede"),
                "sede_nombre": d.get("sede_nombre"),
                "descripcion": d.get("descripcion"),
                "telemetria": {
                    "cpu_percent": round(random.uniform(8.5, 35.0), 1),
                    "memoria_percent": round(random.uniform(22.0, 54.0), 1),
                    "uptime_segundos": int(time.time() - (time.time() - 3600)),
                    "latencia_ms": round(random.uniform(0.8, 3.2), 2),
                    "interfaces": [
                        {"nombre": "eth0", "estado": "UP", "velocidad": "1000Mbps"},
                        {"nombre": "eth1", "estado": "UP", "velocidad": "1000Mbps"},
                    ]
                }
            })
        else:
            self._enviar_json(404, {"error": "Ruta no encontrada"})

    def do_POST(self):
        ruta = urlparse(self.path).path
        longitud = int(self.headers.get("Content-Length", 0))
        cuerpo_bytes = self.rfile.read(longitud) if longitud > 0 else b"{}"
        try:
            body = json.loads(cuerpo_bytes.decode("utf-8"))
        except Exception:
            body = {}

        d = estado_global.obtener()

        if ruta == "/vincular":
            # Requisito: Si ya está vinculado a otra sede, DECLINAR el registro
            id_sede_solicitada = body.get("id_sede")
            sede_nom_solicitada = body.get("sede_nombre") or f"Sede #{id_sede_solicitada}"
            contrasena_ingresada = body.get("contrasena", "")

            if d["vinculado"]:
                sede_actual = d.get("sede_nombre") or f"Sede #{d.get('id_sede')}"
                print(f"[!] DECLINADO: Intento de vinculación desde '{sede_nom_solicitada}', pero el dispositivo YA ESTÁ VINCULADO a '{sede_actual}'.")
                self._enviar_json(409, {
                    "exito": False,
                    "error": f"Dispositivo declinó el registro: actualmente está vinculado a '{sede_actual}'. Debe ser desvinculado primero.",
                })
                return

            # Verificar contraseña del dispositivo
            if contrasena_ingresada != d["contrasena"]:
                print(f"[!] Autenticación fallida: contraseña incorrecta recibida desde {self.client_address[0]}.")
                self._enviar_json(401, {
                    "exito": False,
                    "error": "Contraseña de seguridad del dispositivo incorrecta.",
                })
                return

            # Vinculación exitosa
            estado_global.actualizar(
                vinculado=True,
                id_sede=id_sede_solicitada,
                sede_nombre=sede_nom_solicitada,
            )
            print(f"\n[+] ✅ VINCULACIÓN EXITOSA: Dispositivo enlazado formalmente a '{sede_nom_solicitada}' (ID: {id_sede_solicitada})")
            print(f"    Notificado por administrador: {body.get('admin_usuario', 'admin')}")

            d_actualizado = estado_global.obtener()
            self._enviar_json(200, {
                "exito": True,
                "mensaje": f"Dispositivo vinculado correctamente a '{sede_nom_solicitada}'.",
                "dispositivo": {
                    "uid": d_actualizado["uid"],
                    "nombre": d_actualizado["nombre"],
                    "tipo": d_actualizado["tipo"],
                    "direccion_ip": d_actualizado["direccion_ip"],
                    "mac": d_actualizado["mac"],
                    "descripcion": d_actualizado["descripcion"],
                }
            })

        elif ruta == "/desvincular":
            contrasena_ingresada = body.get("contrasena", "")
            if contrasena_ingresada != d["contrasena"]:
                print(f"[!] Intento de desvinculación rechazado: contraseña incorrecta.")
                self._enviar_json(401, {
                    "exito": False,
                    "error": "Contraseña del dispositivo incorrecta para desvincular.",
                })
                return

            sede_previa = d.get("sede_nombre") or "sede anterior"
            estado_global.actualizar(
                vinculado=False,
                id_sede=None,
                sede_nombre=None,
            )
            print(f"\n[!] 🔓 DESVINCULACIÓN NOTIFICADA: El dispositivo fue desvinculado de '{sede_previa}'.")
            print("    El cliente ahora queda LIBRE y habilitado para ser enlazado por otra sede.")

            self._enviar_json(200, {
                "exito": True,
                "mensaje": "Dispositivo desvinculado exitosamente. Ahora está habilitado para ser registrado por otra sede.",
            })

        else:
            self._enviar_json(404, {"error": "Endpoint POST no encontrado"})

    def log_message(self, format, *args):
        # Silenciar logs HTTP rutinarios para mantener limpia la consola interactiva
        return


def iniciar_servidor_cliente(puerto: int):
    try:
        servidor = HTTPServer(("0.0.0.0", puerto), ClienteHTTPHandler)
        t = threading.Thread(target=servidor.serve_forever, daemon=True)
        t.start()
        return servidor
    except Exception as e:
        print(f"[!] Advertencia: no se pudo enlazar el servidor HTTP en puerto {puerto}: {e}")
        return None


def enviar_telemetria_a_cfs(api_url: str):
    """Envía telemetría de monitoreo periódico hacia el servidor CFS-Admin si está vinculado."""
    import urllib.request
    d = estado_global.obtener()
    if not d.get("vinculado"):
        return

    payload = {
        "uid": d["uid"],
        "estado": "en_linea",
        "cpu_percent": round(random.uniform(5.0, 40.0), 1),
        "memoria_percent": round(random.uniform(20.0, 60.0), 1),
        "uptime_segundos": 7200,
        "interfaces": [{"nombre": "eth0", "status": "UP"}],
    }

    try:
        req = urllib.request.Request(
            f"{api_url}/dispositivos/telemetria",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            pass
    except Exception:
        pass


def bucle_monitoreo(api_url: str):
    while True:
        try:
            enviar_telemetria_a_cfs(api_url)
        except Exception:
            pass
        time.sleep(15)


# ---------------------------------------------------------------------------
# CLI y Modo Interactivo
# ---------------------------------------------------------------------------

def imprimir_banner(d: dict):
    print("=" * 70)
    print("           CFS-ADMIN · DISPOSITIVO CLIENTE DE RED")
    print("=" * 70)
    print(f"  Nombre del Equipo : {d['nombre']}")
    print(f"  Tipo de Dispositivo: {d['tipo']}")
    print(f"  Dirección IP Real  : {d['direccion_ip']} (Detectada)")
    print(f"  Dirección MAC      : {d['mac']}")
    print(f"  UID de Registro    : {d['uid']}")
    print(f"  Contraseña Local   : {d['contrasena']}")
    estado_vinculo = f"Enlazado a '{d.get('sede_nombre')}' (Sede #{d.get('id_sede')})" if d["vinculado"] else "LIBRE (Listo para vincular a una sede)"
    print(f"  Estado de Vínculo  : {estado_vinculo}")
    print(f"  Servicio Local HTTP: http://{d['direccion_ip']}:{d.get('puerto', DEFAULT_PORT)}/")
    print("=" * 70)
    print("  INSTRUCCIONES DE USO:")
    print("  1. Copia el 'UID de Registro' y pégalo en el software CFS-Admin")
    print("     en la sede deseada (el software verificará con ping a la IP ofuscada).")
    print("  2. Cuando el software te pida la contraseña, usa la 'Contraseña Local'.")
    print("  3. Al quedar vinculado, cualquier otra sede que intente registrarlo")
    print("     será declinada automáticamente por esta app cliente.")
    print("  4. Para liberarlo, desvincúlalo desde el software ingresando la contraseña.")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="CFS-Admin Cliente de Dispositivo de Red")
    parser.add_argument("--puerto", type=int, default=DEFAULT_PORT, help="Puerto HTTP local (default: 8500)")
    parser.add_argument("--ip", type=str, default=None, help="Forzar IP local específica")
    parser.add_argument("--password", type=str, default=None, help="Establecer contraseña personalizada")
    parser.add_argument("--nuevo", action="store_true", help="Generar nuevos datos falsos de dispositivo")
    parser.add_argument("--api-url", type=str, default=DEFAULT_API_URL, help="URL de la API CFS-Admin")
    args = parser.parse_args()

    if args.nuevo:
        estado_global.cargar_o_crear(forzar_nuevo=True)

    d = estado_global.obtener()

    actualizaciones = {}
    if args.ip:
        actualizaciones["direccion_ip"] = args.ip
        actualizaciones["uid"] = generar_uid(args.ip)
    if args.password:
        actualizaciones["contrasena"] = args.password
        actualizaciones["contrasena_hash"] = hashlib.sha256(args.password.encode("utf-8")).hexdigest()
    if args.puerto:
        actualizaciones["puerto"] = args.puerto
    if args.api_url:
        actualizaciones["api_url"] = args.api_url

    if actualizaciones:
        d = estado_global.actualizar(**actualizaciones)

    # Iniciar servidor HTTP en segundo plano
    puerto = d.get("puerto", DEFAULT_PORT)
    servidor = iniciar_servidor_cliente(puerto)
    if servidor:
        print(f"[*] Servidor de dispositivo escuchando en puerto {puerto}...")

    # Iniciar thread de telemetría hacia CFS-Admin
    t_telemetria = threading.Thread(target=bucle_monitoreo, args=(d.get("api_url", DEFAULT_API_URL),), daemon=True)
    t_telemetria.start()

    imprimir_banner(d)
    print("\nPresiona Ctrl+C para detener el dispositivo cliente.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Deteniendo cliente...")
        if servidor:
            servidor.shutdown()
        sys.exit(0)


if __name__ == "__main__":
    main()
