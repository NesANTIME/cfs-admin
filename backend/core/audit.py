"""Módulo centralizado de Auditoría para CFS-Admin.
Registra eventos en la tabla de base de datos 'logs_auditoria' y en archivos de texto/json
dentro de la carpeta 'logs/'.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from db.template.empleado import Empleado

# Carpeta de logs garantizada
LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Logger específico de auditoría a archivo
_audit_file_logger = logging.getLogger("cfs.audit")
if not _audit_file_logger.handlers:
    _audit_file_logger.setLevel(logging.INFO)
    _audit_file_logger.propagate = False
    
    # Handler a archivo general
    _log_file_path = LOGS_DIR / "auditoria.log"
    _handler = logging.FileHandler(_log_file_path, encoding="utf-8")
    _formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    _handler.setFormatter(_formatter)
    _audit_file_logger.addHandler(_handler)


def registrar_log(
    db: Session,
    accion: str,
    entidad: str,
    id_entidad: int | None = None,
    detalle: str | None = None,
    actor: Empleado | None = None,
    actor_usuario: str | None = None,
    ip_origen: str | None = None,
) -> None:
    """Registra una acción de auditoría tanto en la base de datos como en la carpeta de logs.
    
    Acciones habituales:
      - PERMISO_CHAT_HABILITADO / PERMISO_CHAT_DESHABILITADO
      - PERMISO_VIDEO_HABILITADO / PERMISO_VIDEO_DESHABILITADO
      - USUARIO_CREADO / USUARIO_DESHABILITADO / USUARIO_HABILITADO / USUARIO_ELIMINADO
      - ADMIN_S_CREADO / ADMIN_S_DESHABILITADO / ADMIN_S_HABILITADO
      - DISPOSITIVO_REGISTRADO / DISPOSITIVO_VINCULADO / DISPOSITIVO_DESVINCULADO
      - SEDE_CREADA / SEDE_MODIFICADA
    """
    from db.template.log_auditoria import LogAuditoria

    id_actor = actor.id_empleado if actor else None
    usuario_actor = (actor.usuario if actor else None) or actor_usuario or "sistema"
    ahora = datetime.now(timezone.utc)

    # 1. Registro en Base de Datos
    log_db = LogAuditoria(
        accion=accion,
        entidad=entidad,
        id_entidad=id_entidad,
        detalle=detalle,
        id_actor=id_actor,
        actor_usuario=usuario_actor,
        ip_origen=ip_origen,
        creado_en=ahora,
    )
    db.add(log_db)
    try:
        db.flush()
    except Exception as e:
        # Si la tabla aún no existe o hay error de transacción, no romper la lógica principal
        pass

    # 2. Registro en carpeta de logs (archivo de auditoría en texto y jsonl)
    try:
        registro_log = {
            "timestamp": ahora.isoformat(),
            "accion": accion,
            "entidad": entidad,
            "id_entidad": id_entidad,
            "actor": usuario_actor,
            "id_actor": id_actor,
            "ip_origen": ip_origen,
            "detalle": detalle,
        }
        _audit_file_logger.info(
            f"ACCION={accion} | ENTIDAD={entidad}:{id_entidad} | ACTOR={usuario_actor} | IP={ip_origen or 'local'} | DETALLE={detalle}"
        )
        
        # Guardar también en formato JSON Lines diario para parsing exacto y backup
        archivo_diario = LOGS_DIR / f"auditoria_{ahora.strftime('%Y-%m-%d')}.jsonl"
        with open(archivo_diario, mode="a", encoding="utf-8") as f_json:
            f_json.write(json.dumps(registro_log, ensure_ascii=False) + "\n")
    except Exception as log_err:
        print(f"[!] Error al escribir en carpeta de logs: {log_err}")
