from datetime import datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_, and_
from sqlalchemy.orm import Session
from db.controller import getDb
from core.deps import getCurrentUser, obtenerTipoAdmin
from db.template.empleado import Empleado
from db.template.mensaje_chat import MensajeChat
from db.template.servicio_usuario import ServicioUsuario
from config.request import MensajeChatCreate, MensajeChatResponse

router = APIRouter(prefix="/chat", tags=["Chat Intra-Sede"])


def _obtenerSedeUsuario(emp: Empleado, db: Session) -> int | None:
    id_s = getattr(emp, "id_sede", None)
    if id_s is not None:
        return id_s
    serv = db.scalars(select(ServicioUsuario).where(ServicioUsuario.id_empleado == emp.id_empleado)).first()
    return serv.id_sede if serv else None


def _tieneServicioChat(emp: Empleado, id_sede: int, db: Session) -> bool:
    """Verifica si el usuario tiene el servicio de chat habilitado en la sede."""
    # admin-g siempre tiene acceso
    if obtenerTipoAdmin(emp) == "admin-g":
        return True

    serv = db.scalars(
        select(ServicioUsuario).where(
            ServicioUsuario.id_empleado == emp.id_empleado,
            ServicioUsuario.tipo_servicio == "chat",
            ServicioUsuario.id_sede == id_sede,
            ServicioUsuario.habilitado == True,  # noqa: E712
        )
    ).first()
    return serv is not None


@router.get("/mensajes", response_model=list[MensajeChatResponse])
def _obtenerConversacion(
    destinatario_id: Annotated[int, Query(description="ID del contacto con quien se conversa")],
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    """Retorna los mensajes intercambiados con un contacto en la misma sede y los marca como leídos."""
    dest = db.get(Empleado, destinatario_id)
    if dest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario destinatario no encontrado.")

    # Validar misma sede (a menos que sea admin-g)
    tipo_admin = obtenerTipoAdmin(user)
    sede_user = _obtenerSedeUsuario(user, db)
    sede_dest = _obtenerSedeUsuario(dest, db)

    id_sede_comun = sede_user or sede_dest
    if tipo_admin != "admin-g":
        if sede_user is None or sede_dest is None or sede_user != sede_dest:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El servicio de chat solo está disponible entre usuarios de la misma sede.",
            )

    # Validar que el usuario actual tenga habilitado el chat
    if not _tieneServicioChat(user, id_sede_comun, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu servicio de chat no está habilitado en esta sede.",
        )

    # Consultar mensajes entre ambos
    stmt = (
        select(MensajeChat)
        .where(
            or_(
                and_(MensajeChat.id_remitente == user.id_empleado, MensajeChat.id_destinatario == dest.id_empleado),
                and_(MensajeChat.id_remitente == dest.id_empleado, MensajeChat.id_destinatario == user.id_empleado),
            )
        )
        .order_by(MensajeChat.creado_en.asc())
    )
    mensajes = db.scalars(stmt).all()

    # Marcar como leídos los mensajes que recibí
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
    db: Annotated[Session, Depends(getDb)],
):
    """Envía un mensaje a un contacto de la misma sede con el servicio de chat activo."""
    if data.destinatario_id == user.id_empleado:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No puedes enviarte mensajes a ti mismo.")

    dest = db.get(Empleado, data.destinatario_id)
    if dest is None or not dest.activo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="El destinatario no existe o está inactivo.")

    # Regla: solo usuarios de la misma sede
    tipo_admin = obtenerTipoAdmin(user)
    sede_user = _obtenerSedeUsuario(user, db)
    sede_dest = _obtenerSedeUsuario(dest, db)
    id_sede_comun = sede_user or sede_dest

    if tipo_admin != "admin-g":
        if sede_user is None or sede_dest is None or sede_user != sede_dest:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo puedes enviar mensajes a usuarios de tu misma sede.",
            )

    # Validar servicio chat habilitado en ambos
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

    texto = data.contenido.strip()
    if not texto:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El mensaje no puede estar vacío.")

    nuevo_mensaje = MensajeChat(
        id_remitente=user.id_empleado,
        id_destinatario=dest.id_empleado,
        id_sede=id_sede_comun or 1,
        contenido=texto,
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
        "leido": False,
        "creado_en": nuevo_mensaje.creado_en.isoformat(),
        "es_mio": True,
        "remitente_nombre": user.nombre,
    }


@router.get("/mensajes/nuevos")
def _obtenerMensajesNuevos(
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    """Consulta rápida para polling de mensajes no leídos."""
    no_leidos = db.scalars(
        select(MensajeChat)
        .where(MensajeChat.id_destinatario == user.id_empleado, MensajeChat.leido == False)  # noqa: E712
        .order_by(MensajeChat.creado_en.asc())
    ).all()

    return {
        "total_no_leidos": len(no_leidos),
        "mensajes": [
            {
                "id": m.id,
                "id_remitente": m.id_remitente,
                "contenido": m.contenido,
                "creado_en": m.creado_en.isoformat(),
            }
            for m in no_leidos
        ],
    }


@router.patch("/mensajes/{id_mensaje}/leer", status_code=status.HTTP_200_OK)
def _marcarLeido(
    id_mensaje: int,
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    """Marca un mensaje como leído."""
    m = db.get(MensajeChat, id_mensaje)
    if m is None or m.id_destinatario != user.id_empleado:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mensaje no encontrado.")

    m.leido = True
    db.commit()
    return {"detalle": "Mensaje marcado como leído."}
