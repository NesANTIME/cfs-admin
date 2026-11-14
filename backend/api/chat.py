import re
from typing import Annotated
from sqlalchemy.orm import Session
from db.controller import GetDatabase
from datetime import datetime, timezone
from sqlalchemy import select, or_, and_
from db.template.empleado import Empleado
from db.template.contacto import Contacto
from db.template.mensaje_chat import MensajeChat
from core.deps import getCurrentUser, obtenerTipoAdmin
from db.template.servicio_usuario import ServicioUsuario
from fastapi import APIRouter, Depends, HTTPException, Query, status
from config.utils.request import MensajeChatCreate, MensajeChatResponse


router = APIRouter(prefix="/chat", tags=["Chat Intra-Sede"])


def _obtenerSedeUsuario(emp: Empleado, db: Session) -> int | None:
    id_s = getattr(emp, "id_sede", None)
    if id_s is not None:
        return id_s
    serv = db.scalars(select(ServicioUsuario).where(ServicioUsuario.id_empleado == emp.id_empleado)).first()
    return serv.id_sede if serv else None


def _contactoFormalizado(id_usuario: int, id_contacto: int, db: Session) -> bool:
    directa = db.scalars(
        select(Contacto).where(
            Contacto.id_usuario == id_usuario,
            Contacto.id_contacto == id_contacto,
        )
    ).first()
    reciproca = db.scalars(
        select(Contacto).where(
            Contacto.id_usuario == id_contacto,
            Contacto.id_contacto == id_usuario,
        )
    ).first()
    return bool(
        directa
        and reciproca
        and directa.registrado_formalmente
        and reciproca.registrado_formalmente
    )


def _tieneServicioChat(emp: Empleado, id_sede: int | None, db: Session) -> bool:
    if obtenerTipoAdmin(emp) == "admin-g":
        return True

    stmt = select(ServicioUsuario).where(
        ServicioUsuario.id_empleado == emp.id_empleado,
        ServicioUsuario.tipo_servicio == "chat",
        ServicioUsuario.habilitado == True,
    )
    if id_sede is not None:
        stmt = stmt.where(or_(ServicioUsuario.id_sede == id_sede, ServicioUsuario.id_sede.is_(None)))
    serv = db.scalars(stmt).first()
    return serv is not None


@router.get("/mensajes", response_model=list[MensajeChatResponse])
def _obtenerConversacion(
    destinatario_id: Annotated[int, Query(description="ID del contacto con quien se conversa")],
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(GetDatabase)],
    limit: Annotated[int, Query(ge=1, le=100, description="Límite de mensajes a retornar")] = 50,
    before_id: Annotated[int | None, Query(description="Cursor para paginación (ID de mensaje anterior)")] = None,
):
    """Retorna los mensajes intercambiados con un contacto en la misma sede (paginados) y los marca como leídos."""
    dest = db.get(Empleado, destinatario_id)
    if dest is None or not dest.activo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario destinatario no encontrado o inactivo.")

    tipo_admin = obtenerTipoAdmin(user)
    sede_user = _obtenerSedeUsuario(user, db)
    sede_dest = _obtenerSedeUsuario(dest, db)

    if tipo_admin == "admin-g":
        id_sede_comun = sede_dest or sede_user
    else:
        if sede_user is None or sede_dest is None or sede_user != sede_dest:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El servicio de chat solo está disponible entre usuarios de la misma sede.",
            )
        id_sede_comun = sede_user

    if not _tieneServicioChat(user, id_sede_comun, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu servicio de chat no está habilitado en esta sede.",
        )

    if not _contactoFormalizado(user.id_empleado, dest.id_empleado, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La solicitud de contacto debe ser aceptada antes de consultar mensajes.",
        )

    stmt = select(MensajeChat).where(
        or_(
            and_(MensajeChat.id_remitente == user.id_empleado, MensajeChat.id_destinatario == dest.id_empleado),
            and_(MensajeChat.id_remitente == dest.id_empleado, MensajeChat.id_destinatario == user.id_empleado),
        )
    )
    if before_id is not None:
        stmt = stmt.where(MensajeChat.id < before_id)

    stmt = stmt.order_by(MensajeChat.id.desc()).limit(limit)
    mensajes = list(reversed(db.scalars(stmt).all()))

    hubo_cambios = False
    for m in mensajes:
        if m.id_destinatario == user.id_empleado and not m.leido:
            m.leido = True
            hubo_cambios = True

    if hubo_cambios:
        db.commit()

    return [
        {
            "id": m.id,
            "id_remitente": m.id_remitente,
            "id_destinatario": m.id_destinatario,
            "id_sede": m.id_sede,
            "contenido": m.contenido,
            "tipo": getattr(m, "tipo", "texto") or "texto",
            "leido": m.leido,
            "creado_en": m.creado_en.isoformat(),
            "es_mio": m.id_remitente == user.id_empleado,
            "remitente_nombre": user.nombre if m.id_remitente == user.id_empleado else dest.nombre,
        }
        for m in mensajes
    ]


@router.post("/mensajes", response_model=MensajeChatResponse, status_code=status.HTTP_201_CREATED)
def _enviarMensaje(
    data: MensajeChatCreate,
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(GetDatabase)],
):
    if data.destinatario_id == user.id_empleado:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No puedes enviarte mensajes a ti mismo.")

    dest = db.get(Empleado, data.destinatario_id)
    if dest is None or not dest.activo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="El destinatario no existe o está inactivo.")

    tipo_admin = obtenerTipoAdmin(user)
    sede_user = _obtenerSedeUsuario(user, db)
    sede_dest = _obtenerSedeUsuario(dest, db)

    if tipo_admin == "admin-g":
        id_sede_comun = sede_dest or sede_user
    else:
        if sede_user is None or sede_dest is None or sede_user != sede_dest:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo puedes enviar mensajes a usuarios de tu misma sede.",
            )
        id_sede_comun = sede_user

    if id_sede_comun is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo determinar la sede para este mensaje.",
        )

    if not _tieneServicioChat(user, id_sede_comun, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu servicio de chat se encuentra deshabilitado por el administrador.",
        )

    if not _tieneServicioChat(dest, id_sede_comun, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El destinatario no tiene habilitado el servicio de chat.",
        )

    if not _contactoFormalizado(user.id_empleado, dest.id_empleado, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La solicitud de contacto debe ser aceptada antes de enviar mensajes.",
        )

    texto = data.contenido.strip()
    if not texto:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El mensaje no puede estar vacío.")

    tipo_msg = data.tipo or "texto"
    if tipo_msg == "imagen":
        if not texto.startswith("data:image/"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Formato de imagen inválido. Solo se admiten PNG, JPEG, WEBP o GIF en data URI base64.",
            )
        partes = texto.split(",", 1)
        if len(partes) != 2:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Formato base64 inválido.",
            )
        header, base64_data = partes
        header_match = re.match(r"^data:image/(png|jpeg|jpg|webp|gif);base64$", header)
        if not header_match:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Formato de imagen inválido. Solo se admiten PNG, JPEG, WEBP o GIF.",
            )

        base64_limpio = re.sub(r"\s+", "", base64_data)
        tamano_aproximado = len(base64_limpio.rstrip("=")) * 3 // 4
        if tamano_aproximado > int(2.5 * 1024 * 1024):
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="La imagen excede el tamaño máximo permitido (2.5 MB).",
            )

    nuevo_mensaje = MensajeChat(
        id_remitente=user.id_empleado,
        id_destinatario=dest.id_empleado,
        id_sede=id_sede_comun,
        contenido=texto,
        tipo=tipo_msg,
        leido=False,
        creado_en=datetime.now(timezone.utc),
    )
    db.add(nuevo_mensaje)
    db.commit()
    db.refresh(nuevo_mensaje)

    return {
        "id": nuevo_mensaje.id,
        "id_remitente": nuevo_mensaje.id_remitente,
        "id_destinatario": nuevo_mensaje.id_destinatario,
        "id_sede": nuevo_mensaje.id_sede,
        "contenido": nuevo_mensaje.contenido,
        "tipo": nuevo_mensaje.tipo,
        "leido": False,
        "creado_en": nuevo_mensaje.creado_en.isoformat(),
        "es_mio": True,
        "remitente_nombre": user.nombre,
    }


@router.get("/mensajes/nuevos")
def _obtenerMensajesNuevos(
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(GetDatabase)],
):
    no_leidos = db.scalars(
        select(MensajeChat)
        .where(MensajeChat.id_destinatario == user.id_empleado, MensajeChat.leido == False)
        .order_by(MensajeChat.creado_en.asc())
    ).all()

    return {
        "total_no_leidos": len(no_leidos),
        "mensajes": [
            {
                "id": m.id,
                "id_remitente": m.id_remitente,
                "contenido": m.contenido,
                "tipo": getattr(m, "tipo", "texto") or "texto",
                "creado_en": m.creado_en.isoformat(),
            }
            for m in no_leidos
        ],
    }


@router.patch("/mensajes/{id_mensaje}/leer", status_code=status.HTTP_200_OK)
def _marcarLeido(
    id_mensaje: int,
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(GetDatabase)],
):
    m = db.get(MensajeChat, id_mensaje)
    if m is None or m.id_destinatario != user.id_empleado:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mensaje no encontrado.")

    m.leido = True
    db.commit()
    return {"detalle": "Mensaje marcado como leído."}
