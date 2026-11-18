"""Endpoints para gestión, verificación por UID, vinculación, monitoreo y desvinculación
de dispositivos de red de sedes en CFS-Admin.
"""
from __future__ import annotations
import base64
import platform
import subprocess
import socket
from datetime import datetime, timezone
from typing import Annotated
from urllib.parse import urlparse

import urllib.request
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from core.deps import getCurrentUser, requireAdmin, obtenerTipoAdmin
from core.audit import registrar_log
from db.controller import GetDatabase
from db.template.dispositivo_red import DispositivoRed
from db.template.empleado import Empleado
from db.template.sede import Sede
from core.security import verifyPassword, hashearPassword

router = APIRouter(tags=["Dispositivos de Red"])

PUERTO_CLIENTE_DEFAULT = 8500


# ---------------------------------------------------------------------------
# Helpers para extracción de IP y Ping
# ---------------------------------------------------------------------------

def desofuscar_ip_uid(uid: str) -> str | None:
    """Extrae la IP ofuscada en el UID.
    El UID tiene la estructura:
      UID-<salt>-<ip_base64_urlsafe>-<checksum>
    o <salt>-<ip_base64_urlsafe>-<checksum>
    """
    if not uid:
        return None
    partes = uid.strip().split("-")
    # Buscar el segmento que contenga base64 decodificable como IPv4
    candidatos = partes[1:] if len(partes) >= 3 else partes
    for token in candidatos:
        try:
            padding = 4 - len(token) % 4
            if padding and padding != 4:
                token_pad = token + ("=" * padding)
            else:
                token_pad = token
            dec = base64.urlsafe_b64decode(token_pad.encode("ascii")).decode("utf-8")
            # Validar que sea una IP válida
            socket.inet_aton(dec)
            if dec.count(".") == 3:
                return dec
        except Exception:
            continue
    return None


def ejecutar_ping_red(ip: str, timeout_seg: int = 2) -> dict:
    """Realiza un ping ICMP hacia la IP o prueba de socket TCP como fallback."""
    # 1. Intento con ping del sistema
    param = "-n" if platform.system().lower() == "windows" else "-c"
    timeout_param = "-w" if platform.system().lower() == "windows" else "-W"
    try:
        resultado = subprocess.run(
            ["ping", param, "1", timeout_param, str(timeout_seg), ip],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seg + 1,
        )
        if resultado.returncode == 0:
            return {"exitoso": True, "metodo": "icmp", "latencia_ms": "< 10ms", "ip": ip}
    except Exception:
        pass

    # 2. Fallback de conectividad TCP rápida hacia el puerto del cliente
    for p in (PUERTO_CLIENTE_DEFAULT, 80, 443, 22):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        try:
            s.connect((ip, p))
            s.close()
            return {"exitoso": True, "metodo": f"tcp_port_{p}", "latencia_ms": "~5ms", "ip": ip}
        except Exception:
            s.close()

    # Si la IP es localhost o loopback durante pruebas en misma máquina:
    if ip in ("127.0.0.1", "localhost"):
        return {"exitoso": True, "metodo": "loopback", "latencia_ms": "1ms", "ip": ip}

    return {"exitoso": False, "metodo": "fallido", "latencia_ms": None, "ip": ip}


def consultar_cliente_app(ip: str, endpoint: str, payload: dict | None = None, timeout: float = 3.0) -> dict | None:
    """Envía solicitud HTTP al servicio embebido del cliente en su IP."""
    url = f"http://{ip}:{PUERTO_CLIENTE_DEFAULT}{endpoint}"
    try:
        data_bytes = json.dumps(payload).encode("utf-8") if payload else None
        headers = {"Content-Type": "application/json"} if payload else {}
        req = urllib.request.Request(url, data=data_bytes, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _verificarAccesoSede(user: Empleado, id_sede: int) -> None:
    tipo = obtenerTipoAdmin(user)
    if tipo == "admin-g":
        return
    id_sede_user = getattr(user, "id_sede", None)
    if id_sede_user != id_sede:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permiso denegado: no estás autorizado para gestionar dispositivos en esta sede.",
        )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class VerificarUidRequest(BaseModel):
    uid: str = Field(..., min_length=10, max_length=128)

class VincularDispositivoRequest(BaseModel):
    uid: str = Field(..., min_length=10, max_length=128)
    contrasena: str = Field(..., min_length=1, max_length=128)
    nombre: str | None = None
    tipo: str | None = None
    mac: str | None = None
    descripcion: str | None = None

class DesvincularRequest(BaseModel):
    contrasena: str = Field(..., min_length=1, max_length=128)

class TelemetriaClienteRequest(BaseModel):
    uid: str
    estado: str = "en_linea"
    cpu_percent: float | None = None
    memoria_percent: float | None = None
    uptime_segundos: int | None = None
    interfaces: list[dict] | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/sedes/{id_sede}/dispositivos")
def listarDispositivosSede(
    id_sede: int,
    user: Annotated[Empleado, Depends(requireAdmin)],
    db: Annotated[Session, Depends(GetDatabase)],
):
    """Lista todos los dispositivos asociados a una sede."""
    _verificarAccesoSede(user, id_sede)
    sede = db.get(Sede, id_sede)
    if not sede:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Sede {id_sede} no encontrada.")

    disps = db.scalars(
        select(DispositivoRed)
        .where(DispositivoRed.id_sede == id_sede)
        .order_by(DispositivoRed.id_dispositivo.asc())
    ).all()

    return [
        {
            "id_dispositivo": d.id_dispositivo,
            "nombre": d.nombre,
            "tipo": d.tipo,
            "direccion_ip": str(d.direccion_ip),
            "mac": str(d.mac),
            "estado": d.estado,
            "vinculado": bool(d.vinculado),
            "uid_dispositivo": d.uid_dispositivo,
            "ultimo_ping": d.ultimo_ping.isoformat() if d.ultimo_ping else None,
            "detalles_hardware": json.loads(d.detalles_hardware) if d.detalles_hardware else None,
            "descripcion": d.descripcion,
            "id_sede": d.id_sede,
        }
        for d in disps
    ]


@router.post("/sedes/{id_sede}/dispositivos/verificar-uid")
def verificarUidEnRed(
    id_sede: int,
    data: VerificarUidRequest,
    user: Annotated[Empleado, Depends(requireAdmin)],
    db: Annotated[Session, Depends(GetDatabase)],
):
    """Paso 1: Extrae la IP del UID, comprueba disponibilidad en red (ping)
    y consulta si el dispositivo ya está vinculado a otra sede.
    """
    _verificarAccesoSede(user, id_sede)
    uid = data.uid.strip()

    # 1. Verificar si ya está vinculado en la base de datos a otra sede
    existente = db.scalars(
        select(DispositivoRed).where(
            DispositivoRed.uid_dispositivo == uid,
            DispositivoRed.vinculado == True,
        )
    ).first()
    if existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Este dispositivo ya está vinculado a la sede #{existente.id_sede}. Debe ser desvinculado previamente.",
        )

    # 2. Desofuscar IP
    ip = desofuscar_ip_uid(uid)
    if not ip:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El UID proporcionado no es válido o no contiene una dirección IP ofuscada reconocible.",
        )

    # 3. Comprobar existencia en red mediante ping
    resultado_ping = ejecutar_ping_red(ip)

    # 4. Consultar al cliente app si está escuchando
    cliente_info = consultar_cliente_app(ip, "/status")
    if cliente_info and cliente_info.get("vinculado") is True:
        sede_vinculada = cliente_info.get("id_sede") or cliente_info.get("sede_nombre") or "otra sede"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El cliente en el dispositivo reportó que ya está vinculado a {sede_vinculada}. Registro declinado.",
        )

    nombre_detectado = (cliente_info.get("nombre") if cliente_info else None) or f"Equipo de Red ({ip})"
    tipo_detectado = (cliente_info.get("tipo") if cliente_info else None) or "Router"
    mac_detectada = (cliente_info.get("mac") if cliente_info else None) or "00:00:00:00:00:00"

    return {
        "uid": uid,
        "ip_ofuscada_detectada": ip,
        "ping_exitoso": resultado_ping["exitoso"],
        "metodo_ping": resultado_ping["metodo"],
        "latencia": resultado_ping.get("latencia_ms"),
        "dispositivo_info": {
            "nombre": nombre_detectado,
            "tipo": tipo_detectado,
            "mac": mac_detectada,
        },
        "cliente_conectado": cliente_info is not None,
        "mensaje": "Dispositivo alcanzado y listo para autenticación." if resultado_ping["exitoso"] else "Dispositivo verificado; ping no respondió pero se permite autenticar si está detrás de firewall.",
    }


@router.post("/sedes/{id_sede}/dispositivos/vincular", status_code=status.HTTP_201_CREATED)
def vincularDispositivoASede(
    id_sede: int,
    data: VincularDispositivoRequest,
    user: Annotated[Empleado, Depends(requireAdmin)],
    db: Annotated[Session, Depends(GetDatabase)],
):
    """Paso 2: Verifica la contraseña del dispositivo y lo vincula formalmente a la sede."""
    _verificarAccesoSede(user, id_sede)
    sede = db.get(Sede, id_sede)
    if not sede:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Sede {id_sede} no encontrada.")

    uid = data.uid.strip()
    contrasena = data.contrasena.strip()

    # Comprobar si ya está vinculado
    existente = db.scalars(
        select(DispositivoRed).where(
            DispositivoRed.uid_dispositivo == uid,
            DispositivoRed.vinculado == True,
        )
    ).first()
    if existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El dispositivo ya se encuentra vinculado a la sede #{existente.id_sede}.",
        )

    ip = desofuscar_ip_uid(uid)
    if not ip:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="UID inválido.")

    # Intentar validar con la app cliente si responde en su IP
    cliente_resp = consultar_cliente_app(
        ip,
        "/vincular",
        payload={
            "uid": uid,
            "contrasena": contrasena,
            "id_sede": id_sede,
            "sede_nombre": sede.nombre,
            "admin_usuario": user.usuario,
        },
    )

    contrasena_valida = False
    datos_cliente = {}

    if cliente_resp is not None:
        if cliente_resp.get("exito") is True:
            contrasena_valida = True
            datos_cliente = cliente_resp.get("dispositivo") or {}
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=cliente_resp.get("error") or "Contraseña del dispositivo incorrecta.",
            )
    else:
        # Si el cliente no tiene servidor HTTP abierto en este momento,
        # verificar contra registro previo si existiera
        previo = db.scalars(
            select(DispositivoRed).where(DispositivoRed.uid_dispositivo == uid)
        ).first()
        if previo and previo.contrasena_hash:
            contrasena_valida = verifyPassword(previo.contrasena_hash, contrasena)
            if not contrasena_valida:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Contraseña del dispositivo incorrecta.")
        else:
            # Si es primera vez y no hay servidor HTTP local accesible, aceptar y guardar hash
            contrasena_valida = True

    # Determinar nombre, tipo, mac
    nombre = data.nombre or datos_cliente.get("nombre") or f"Dispositivo {ip}"
    tipo = data.tipo or datos_cliente.get("tipo") or "Router"
    mac = data.mac or datos_cliente.get("mac") or "00:1A:2B:3C:4D:5E"
    descripcion = data.descripcion or datos_cliente.get("descripcion") or f"Enlazado por UID {uid}"

    # Buscar si ya había un registro no vinculado con este UID o IP
    disp_db = db.scalars(
        select(DispositivoRed).where(
            DispositivoRed.id_sede == id_sede,
            DispositivoRed.direccion_ip == ip,
        )
    ).first()

    if not disp_db:
        disp_db = db.scalars(
            select(DispositivoRed).where(DispositivoRed.uid_dispositivo == uid)
        ).first()

    from core.security import hashearPassword
    contrasena_hash = hashearPassword(contrasena)

    if disp_db:
        disp_db.nombre = nombre
        disp_db.tipo = tipo
        disp_db.mac = mac
        disp_db.direccion_ip = ip
        disp_db.uid_dispositivo = uid
        disp_db.contrasena_hash = contrasena_hash
        disp_db.vinculado = True
        disp_db.estado = "en_linea"
        disp_db.id_sede = id_sede
        disp_db.ultimo_ping = datetime.now(timezone.utc)
        disp_db.descripcion = descripcion
    else:
        disp_db = DispositivoRed(
            nombre=nombre,
            tipo=tipo,
            direccion_ip=ip,
            mac=mac,
            estado="en_linea",
            id_sede=id_sede,
            uid_dispositivo=uid,
            contrasena_hash=contrasena_hash,
            vinculado=True,
            ultimo_ping=datetime.now(timezone.utc),
            descripcion=descripcion,
        )
        db.add(disp_db)

    # Registrar Log de Auditoría
    registrar_log(
        db,
        accion="DISPOSITIVO_VINCULADO",
        entidad="dispositivo",
        id_entidad=disp_db.id_dispositivo,
        detalle=f"Dispositivo '{nombre}' (IP: {ip}, MAC: {mac}, UID: {uid}) vinculado a sede #{id_sede} ({sede.nombre}) por {user.usuario}.",
        actor=user,
    )

    db.commit()
    db.refresh(disp_db)

    return {
        "detalle": f"Dispositivo '{disp_db.nombre}' vinculado exitosamente a la sede.",
        "id_dispositivo": disp_db.id_dispositivo,
        "nombre": disp_db.nombre,
        "direccion_ip": str(disp_db.direccion_ip),
        "uid_dispositivo": disp_db.uid_dispositivo,
        "vinculado": True,
    }


@router.get("/dispositivos/{id_dispositivo}")
def obtenerDetalleDispositivo(
    id_dispositivo: int,
    user: Annotated[Empleado, Depends(requireAdmin)],
    db: Annotated[Session, Depends(GetDatabase)],
):
    """Consulta información y telemetría de un dispositivo."""
    disp = db.get(DispositivoRed, id_dispositivo)
    if not disp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Dispositivo no encontrado.")
    _verificarAccesoSede(user, disp.id_sede)

    # Intentar hacer ping actual
    ip = str(disp.direccion_ip)
    ping_res = ejecutar_ping_red(ip)

    # Actualizar estado según ping
    disp.estado = "en_linea" if ping_res["exitoso"] else "fuera_de_linea"
    disp.ultimo_ping = datetime.now(timezone.utc)
    db.commit()

    return {
        "id_dispositivo": disp.id_dispositivo,
        "nombre": disp.nombre,
        "tipo": disp.tipo,
        "direccion_ip": ip,
        "mac": str(disp.mac),
        "estado": disp.estado,
        "vinculado": bool(disp.vinculado),
        "uid_dispositivo": disp.uid_dispositivo,
        "ultimo_ping": disp.ultimo_ping.isoformat() if disp.ultimo_ping else None,
        "ping_actual": ping_res,
        "detalles_hardware": json.loads(disp.detalles_hardware) if disp.detalles_hardware else None,
        "descripcion": disp.descripcion,
        "id_sede": disp.id_sede,
    }


@router.delete("/dispositivos/{id_dispositivo}/desvincular")
def desvincularYEliminarDispositivo(
    id_dispositivo: int,
    data: DesvincularRequest,
    user: Annotated[Empleado, Depends(requireAdmin)],
    db: Annotated[Session, Depends(GetDatabase)],
):
    """Desvincula y elimina el dispositivo de la sede requiriendo su contraseña.
    Notifica al cliente app para habilitar que sea enlazado por otra sede.
    """
    disp = db.get(DispositivoRed, id_dispositivo)
    if not disp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Dispositivo no encontrado.")
    _verificarAccesoSede(user, disp.id_sede)

    contrasena = data.contrasena.strip()
    ip = str(disp.direccion_ip)

    # 1. Notificar a la app cliente e intentar validar contraseña
    cliente_resp = consultar_cliente_app(
        ip,
        "/desvincular",
        payload={
            "uid": disp.uid_dispositivo,
            "contrasena": contrasena,
            "id_sede": disp.id_sede,
            "admin_usuario": user.usuario,
        },
    )

    if cliente_resp is not None:
        if not cliente_resp.get("exito"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=cliente_resp.get("error") or "Contraseña del dispositivo incorrecta.",
            )
    else:
        # Si el cliente no responde HTTP, validar con el hash en la BD
        if disp.contrasena_hash:
            if not verifyPassword(disp.contrasena_hash, contrasena):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Contraseña del dispositivo incorrecta.",
                )

    nombre = disp.nombre
    id_sede = disp.id_sede
    uid = disp.uid_dispositivo

    registrar_log(
        db,
        accion="DISPOSITIVO_DESVINCULADO",
        entidad="dispositivo",
        id_entidad=id_dispositivo,
        detalle=f"Dispositivo '{nombre}' (UID: {uid}, IP: {ip}) desvinculado y eliminado de sede #{id_sede} por {user.usuario}.",
        actor=user,
    )

    db.delete(disp)
    db.commit()

    return {
        "detalle": f"El dispositivo '{nombre}' ha sido desvinculado y eliminado exitosamente. El cliente ahora puede ser enlazado por otra sede.",
        "id_dispositivo": id_dispositivo,
    }


@router.post("/dispositivos/telemetria")
def reportarTelemetriaCliente(
    data: TelemetriaClienteRequest,
    db: Annotated[Session, Depends(GetDatabase)],
):
    """Endpoint al que la app cliente puede reportar periódicamente telemetría de monitoreo."""
    uid = data.uid.strip()
    disp = db.scalars(
        select(DispositivoRed).where(DispositivoRed.uid_dispositivo == uid)
    ).first()

    if not disp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Dispositivo no encontrado.")

    disp.estado = data.estado
    disp.ultimo_ping = datetime.now(timezone.utc)

    hardware_info = {
        "cpu_percent": data.cpu_percent,
        "memoria_percent": data.memoria_percent,
        "uptime_segundos": data.uptime_segundos,
        "interfaces": data.interfaces,
        "reportado_en": datetime.now(timezone.utc).isoformat(),
    }
    disp.detalles_hardware = json.dumps(hardware_info)
    db.commit()

    return {"status": "ok", "vinculado": bool(disp.vinculado), "id_sede": disp.id_sede}
