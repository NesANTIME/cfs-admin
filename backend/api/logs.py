"""Endpoints de consulta y exportación de Logs de Auditoría (Exclusivo Admin-G)."""
from __future__ import annotations
import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session

from core.deps import getCurrentUser, requireAdminG
from core.audit import LOGS_DIR
from db.controller import GetDatabase
from db.template.empleado import Empleado
from db.template.log_auditoria import LogAuditoria

router = APIRouter(prefix="/logs", tags=["Auditoría y Logs"])


class LogItemResponse(BaseModel):
    id: int
    accion: str
    entidad: str
    id_entidad: int | None = None
    detalle: str | None = None
    id_actor: int | None = None
    actor_usuario: str | None = None
    ip_origen: str | None = None
    creado_en: datetime


@router.get("", response_model=list[LogItemResponse])
def consultarLogsAuditoria(
    admin: Annotated[Empleado, Depends(requireAdminG)],
    db: Annotated[Session, Depends(GetDatabase)],
    accion: str | None = Query(None, description="Filtrar por acción"),
    entidad: str | None = Query(None, description="Filtrar por entidad (empleado, sede, dispositivo, servicio_usuario)"),
    actor: str | None = Query(None, description="Username del actor"),
    q: str | None = Query(None, description="Búsqueda libre en detalle o acción"),
    desde: datetime | None = Query(None),
    hasta: datetime | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Consulta registros de auditoría filtrados (exclusivo Admin-G)."""
    stmt = select(LogAuditoria)
    condiciones = []

    if accion:
        condiciones.append(LogAuditoria.accion.ilike(f"%{accion}%"))
    if entidad:
        condiciones.append(LogAuditoria.entidad == entidad)
    if actor:
        condiciones.append(LogAuditoria.actor_usuario.ilike(f"%{actor}%"))
    if q:
        condiciones.append(
            or_(
                LogAuditoria.detalle.ilike(f"%{q}%"),
                LogAuditoria.accion.ilike(f"%{q}%"),
                LogAuditoria.actor_usuario.ilike(f"%{q}%"),
            )
        )
    if desde:
        condiciones.append(LogAuditoria.creado_en >= desde)
    if hasta:
        condiciones.append(LogAuditoria.creado_en <= hasta)

    if condiciones:
        stmt = stmt.where(and_(*condiciones))

    stmt = stmt.order_by(LogAuditoria.creado_en.desc(), LogAuditoria.id.desc()).limit(limit).offset(offset)
    return db.scalars(stmt).all()


@router.get("/archivos")
def listarArchivosCarpetaLogs(
    admin: Annotated[Empleado, Depends(requireAdminG)],
):
    """Lista los archivos físicos almacenados en la carpeta de logs del software."""
    archivos = []
    if LOGS_DIR.exists():
        for p in sorted(LOGS_DIR.glob("*"), reverse=True):
            if p.is_file():
                archivos.append({
                    "nombre": p.name,
                    "tamano_bytes": p.stat().st_size,
                    "modificado": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(),
                })
    return {"carpeta": str(LOGS_DIR), "archivos": archivos}


@router.get("/exportar/csv")
def exportarLogsCsv(
    admin: Annotated[Empleado, Depends(requireAdminG)],
    db: Annotated[Session, Depends(GetDatabase)],
    limit: int = Query(5000, ge=1, le=20000),
):
    """Descarga los logs en formato CSV."""
    logs = db.scalars(
        select(LogAuditoria).order_by(LogAuditoria.creado_en.desc()).limit(limit)
    ).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["ID", "Fecha/Hora (UTC)", "Acción", "Entidad", "ID Entidad", "Actor", "IP Origen", "Detalle"])
    for l in logs:
        writer.writerow([
            l.id,
            l.creado_en.isoformat() if l.creado_en else "",
            l.accion,
            l.entidad,
            l.id_entidad or "",
            l.actor_usuario or "",
            l.ip_origen or "",
            l.detalle or "",
        ])

    buffer.seek(0)
    nombre_archivo = f"cfs_admin_logs_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={nombre_archivo}"},
    )


@router.get("/exportar/html-imprimible")
def exportarLogsHtmlImprimible(
    admin: Annotated[Empleado, Depends(requireAdminG)],
    db: Annotated[Session, Depends(GetDatabase)],
    limit: int = Query(500, ge=1, le=2000),
):
    """Genera una página HTML estructurada lista para imprimir o guardar como PDF en el navegador."""
    logs = db.scalars(
        select(LogAuditoria).order_by(LogAuditoria.creado_en.desc()).limit(limit)
    ).all()

    filas = "".join(f"""
        <tr>
            <td>#{l.id}</td>
            <td>{l.creado_en.strftime('%Y-%m-%d %H:%M:%S') if l.creado_en else '—'}</td>
            <td><strong>{l.accion}</strong></td>
            <td>{l.entidad}</td>
            <td>{l.actor_usuario or 'sistema'}</td>
            <td>{l.ip_origen or 'local'}</td>
            <td>{l.detalle or '—'}</td>
        </tr>
    """ for l in logs)

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Reporte Oficial de Auditoría · CFS-Admin</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 24px; color: #111; }}
  .header {{ border-bottom: 2px solid #2563eb; padding-bottom: 12px; margin-bottom: 18px; display:flex; justify-content:space-between; align-items:flex-end; }}
  h1 {{ margin: 0; font-size: 20px; color: #1e3a8a; }}
  .meta {{ font-size: 12px; color: #555; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
  th, td {{ border: 1px solid #cbd5e1; padding: 6px 8px; text-align: left; }}
  th {{ background: #f1f5f9; font-weight: 600; color: #334155; }}
  tr:nth-child(even) {{ background: #f8fafc; }}
  @media print {{
    .no-print {{ display: none; }}
    body {{ margin: 0; }}
  }}
</style>
</head>
<body>
<div class="no-print" style="margin-bottom:16px; display:flex; gap:10px;">
  <button onclick="window.print()" style="background:#2563eb;color:#fff;border:none;padding:8px 16px;border-radius:6px;cursor:pointer;font-weight:600;">🖨️ Imprimir / Guardar en PDF</button>
  <button onclick="window.close()" style="background:#e2e8f0;border:none;padding:8px 16px;border-radius:6px;cursor:pointer;">Cerrar</button>
</div>
<div class="header">
  <div>
    <h1>CFS-ADMIN · REPORTE OFICIAL DE AUDITORÍA Y PERMISOS</h1>
    <div class="meta">Generado por: {admin.nombre} ({admin.usuario}) · Total registros: {len(logs)}</div>
  </div>
  <div class="meta">Fecha de emisión: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC</div>
</div>
<table>
  <thead>
    <tr>
      <th style="width:40px;">ID</th>
      <th style="width:130px;">Fecha/Hora (UTC)</th>
      <th style="width:180px;">Acción</th>
      <th style="width:90px;">Entidad</th>
      <th style="width:90px;">Actor</th>
      <th style="width:90px;">IP</th>
      <th>Detalle del Evento</th>
    </tr>
  </thead>
  <tbody>
    {filas}
  </tbody>
</table>
<script>
  // Si el query param autiprint=1 está presente, abrir diálogo de impresión
  if (new URLSearchParams(window.location.search).get("autoprint") === "1") {{
    window.onload = () => {{ window.print(); }};
  }}
</script>
</body>
</html>"""

    return Response(content=html, media_type="text/html; charset=utf-8")
