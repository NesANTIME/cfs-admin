import asyncio
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config.config import CONFIG
from config.request import (
    IceConfigResponse,
    IceServerConfig,
    InvitacionVideoconfResponse,
    SalaVideoconfCreate,
    SalaVideoconfResponse,
    SenalVideoconfCreate,
)
from core.deps import getCurrentUser, obtenerTipoAdmin
from db.controller import SessionLocal, getDb
from db.template.contacto import Contacto
from db.template.empleado import Empleado, Tecnico, UsuarioSede
from db.template.invitacion_videoconf import InvitacionVideoconf
from db.template.sala_videoconf import SalaVideoconf
from db.template.sede import Sede
from db.template.servicio_usuario import ServicioUsuario

router = APIRouter(prefix="/videoconferencia", tags=["Videoconferencia"])

PATRON_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
ESTADOS_INVITACION = {
    "pendiente",
    "aceptada",
    "rechazada",
    "cancelada",
    "expirada",
    "finalizada",
}


# ---------------------------------------------------------------------------
# Helpers de usuarios, sedes y permisos
# ---------------------------------------------------------------------------

def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _obtenerSedeUsuario(emp: Empleado | None, db: Session) -> int | None:
    """Sede principal del empleado. No se infiere desde servicios_usuario."""
    if emp is None:
        return None
    id_s = getattr(emp, "id_sede", None)
    if id_s is not None:
        return id_s
    serv = db.scalars(
        select(ServicioUsuario).where(
            ServicioUsuario.id_empleado == emp.id_empleado,
            ServicioUsuario.id_sede.is_not(None),
        )
    ).first()
    return serv.id_sede if serv else None


def _obtenerIdsEmpleadosDeSede(id_sede: int | None, db: Session) -> set[int]:
    if id_sede is None:
        return set()
    ids: set[int] = set()
    ids.update(
        db.scalars(select(Tecnico.id_empleado).where(Tecnico.id_sede == id_sede)).all()
    )
    ids.update(
        db.scalars(select(UsuarioSede.id_empleado).where(UsuarioSede.id_sede == id_sede)).all()
    )
    return ids


def _nombreSede(id_sede: int | None, db: Session) -> str | None:
    if id_sede is None:
        return None
    sede = db.get(Sede, id_sede)
    return sede.nombre if sede else None


def _tieneServicioVideo(emp: Empleado | None, db: Session) -> bool:
    """Servicio de videoconferencia habilitado en la sede propia del empleado.

    Se mantiene la excepción histórica para admin-g, igual que en chat.
    """
    if emp is None or not emp.activo:
        return False
    if obtenerTipoAdmin(emp) == "admin-g":
        return True

    id_sede = _obtenerSedeUsuario(emp, db)
    stmt = select(ServicioUsuario).where(
        ServicioUsuario.id_empleado == emp.id_empleado,
        ServicioUsuario.tipo_servicio == "videoconferencia",
        ServicioUsuario.habilitado == True,  # noqa: E712
    )
    if id_sede is not None:
        stmt = stmt.where(
            or_(
                ServicioUsuario.id_sede == id_sede,
                ServicioUsuario.id_sede.is_(None),
            )
        )
    return db.scalars(stmt).first() is not None


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


def _tieneLlamadaActiva(user_id: int, db: Session) -> bool:
    stmt = (
        select(InvitacionVideoconf.id)
        .join(SalaVideoconf, SalaVideoconf.id == InvitacionVideoconf.id_sala)
        .where(
            InvitacionVideoconf.estado == "aceptada",
            SalaVideoconf.activa.is_(True),
            or_(
                InvitacionVideoconf.id_invitador == user_id,
                InvitacionVideoconf.id_invitado == user_id,
            ),
        )
    )
    return db.scalars(stmt).first() is not None


def _resolverInvitado(
    data: SalaVideoconfCreate,
    user: Empleado,
    db: Session,
) -> Empleado:
    sede_user = _obtenerSedeUsuario(user, db)

    if data.id_contacto is not None:
        invitado = db.get(Empleado, data.id_contacto)
        if invitado is None or not invitado.activo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado.",
            )
        sede_invitado = _obtenerSedeUsuario(invitado, db)
        if sede_user is None or sede_invitado is None or sede_user != sede_invitado:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo puedes invitar contactos de tu misma sede.",
            )
        if not _contactoFormalizado(user.id_empleado, invitado.id_empleado, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El contacto debe estar formalizado para iniciar una videollamada.",
            )
        return invitado

    ident = (data.identificador or "").strip()

    if PATRON_UUID.match(ident):
        # UID completo: búsqueda global exacta, permite otra sede.
        ident = ident.lower()
        invitado = db.scalars(
            select(Empleado).where(
                Empleado.uid_publico == ident,
                Empleado.activo.is_(True),
            )
        ).first()
    else:
        # Username: solo misma sede, coincidencia exacta.
        if sede_user is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Necesitas una sede asignada o usar el UID completo.",
            )
        ids_sede = _obtenerIdsEmpleadosDeSede(sede_user, db)
        if not ids_sede:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado.",
            )
        invitado = db.scalars(
            select(Empleado).where(
                func.lower(Empleado.usuario) == ident.lower(),
                Empleado.activo.is_(True),
                Empleado.id_empleado.in_(ids_sede),
            )
        ).first()

    if invitado is None:
        # 404 genérico: no revelar si el UID existe en otra sede.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado.",
        )
    if invitado.id_empleado == user.id_empleado:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes invitarte a ti mismo.",
        )
    if not _tieneServicioVideo(invitado, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario no tiene habilitada la videoconferencia.",
        )
    return invitado


def _expirarInvitacionesVencidas(
    db: Session,
    id_sala: int | None = None,
) -> list[InvitacionVideoconf]:
    """Marca invitaciones pendientes vencidas y desactiva salas sin aceptadas."""
    ahora = _ahora()
    stmt = select(InvitacionVideoconf).where(
        InvitacionVideoconf.estado == "pendiente",
        InvitacionVideoconf.expira_en <= ahora,
    )
    if id_sala is not None:
        stmt = stmt.where(InvitacionVideoconf.id_sala == id_sala)
    vencidas = db.scalars(stmt).all()

    salas_afectadas: set[int] = set()
    for inv in vencidas:
        inv.estado = "expirada"
        inv.respondida_en = ahora
        salas_afectadas.add(inv.id_sala)

    for id_s in salas_afectadas:
        sala = db.get(SalaVideoconf, id_s)
        if sala is None or not sala.activa:
            continue
        aceptada = db.scalars(
            select(InvitacionVideoconf.id).where(
                InvitacionVideoconf.id_sala == id_s,
                InvitacionVideoconf.estado == "aceptada",
            )
        ).first()
        if aceptada is None:
            sala.activa = False

    if vencidas:
        db.flush()
    return vencidas


def _invitacionDeParticipante(
    sala: SalaVideoconf,
    user: Empleado,
    db: Session,
) -> InvitacionVideoconf | None:
    return db.scalars(
        select(InvitacionVideoconf)
        .where(
            InvitacionVideoconf.id_sala == sala.id,
            or_(
                InvitacionVideoconf.id_invitador == user.id_empleado,
                InvitacionVideoconf.id_invitado == user.id_empleado,
            ),
        )
        .order_by(InvitacionVideoconf.creada_en.desc())
    ).first()


def _participanteAceptado(
    sala: SalaVideoconf,
    user: Empleado,
    db: Session,
) -> InvitacionVideoconf | None:
    """Devuelve la invitación aceptada que autoriza al usuario, o None."""
    if sala.id_iniciador == user.id_empleado:
        return db.scalars(
            select(InvitacionVideoconf).where(
                InvitacionVideoconf.id_sala == sala.id,
                InvitacionVideoconf.estado == "aceptada",
            )
        ).first()
    return db.scalars(
        select(InvitacionVideoconf).where(
            InvitacionVideoconf.id_sala == sala.id,
            InvitacionVideoconf.id_invitado == user.id_empleado,
            InvitacionVideoconf.estado == "aceptada",
        )
    ).first()


# ---------------------------------------------------------------------------
# Serialización con reglas de privacidad cross-sede
# ---------------------------------------------------------------------------

def _serializarSala(
    sala: SalaVideoconf,
    invitacion: InvitacionVideoconf | None,
    user: Empleado,
    db: Session,
) -> dict:
    invitado = sala.invitado
    sede_iniciador = _obtenerSedeUsuario(sala.iniciador, db)
    sede_invitado = _obtenerSedeUsuario(invitado, db)
    misma_sede = (
        sede_iniciador is not None
        and sede_invitado is not None
        and sede_iniciador == sede_invitado
    )
    es_iniciador = user.id_empleado == sala.id_iniciador
    estado = invitacion.estado if invitacion else None
    aceptada = estado == "aceptada"
    es_invitado = invitado is not None and user.id_empleado == invitado.id_empleado

    revelar_invitado = bool(es_invitado or misma_sede or aceptada)

    return {
        "codigo_sala": sala.codigo_sala,
        "id_sala": sala.id,
        "id_sede": sala.id_sede,
        "id_iniciador": sala.id_iniciador,
        "id_invitado": sala.id_invitado,
        "nombre_iniciador": sala.iniciador.nombre if sala.iniciador else None,
        "nombre_invitado": invitado.nombre if (invitado and revelar_invitado) else None,
        "usuario_invitado": invitado.usuario if (invitado and revelar_invitado) else None,
        "uid_invitado": invitado.uid_publico if invitado else None,
        "sede_invitado": _nombreSede(sede_invitado, db) if (invitado and revelar_invitado) else None,
        "sede_iniciador": _nombreSede(sede_iniciador, db),
        "estado_invitacion": estado,
        "invitacion_id": invitacion.id if invitacion else None,
        "expira_en": invitacion.expira_en if invitacion else None,
        "activa": bool(sala.activa),
        "es_iniciador": es_iniciador,
        "puede_entrar": bool(
            sala.activa
            and aceptada
            and _tieneServicioVideo(user, db)
        ),
    }


def _serializarInvitacion(
    inv: InvitacionVideoconf,
    user: Empleado,
    db: Session,
) -> dict:
    sala = inv.sala
    invitador = inv.invitador
    invitado = inv.invitado
    es_recibida = inv.id_invitado == user.id_empleado

    sede_invitador = _obtenerSedeUsuario(invitador, db)
    sede_invitado = _obtenerSedeUsuario(invitado, db)
    misma_sede = (
        sede_invitador is not None
        and sede_invitado is not None
        and sede_invitador == sede_invitado
    )
    revelar_invitado = bool(
        es_recibida
        or misma_sede
        or inv.estado in ("aceptada", "finalizada")
    )

    # El invitado siempre ve quién lo invita. En enviadas cross-sede pendientes
    # solo se revela el UID del invitado.
    nombre_invitador = invitador.nombre if invitador else None
    usuario_invitador = invitador.usuario if invitador else None
    uid_invitador = invitador.uid_publico if invitador else None
    sede_invitador_nombre = _nombreSede(sede_invitador, db)

    puede_aceptar = bool(
        es_recibida
        and inv.estado == "pendiente"
        and inv.expira_en > _ahora()
        and sala.activa
        and _tieneServicioVideo(user, db)
        and not _tieneLlamadaActiva(user.id_empleado, db)
    )

    return {
        "id": inv.id,
        "id_sala": inv.id_sala,
        "codigo_sala": sala.codigo_sala,
        "id_invitador": inv.id_invitador,
        "nombre_invitador": nombre_invitador,
        "usuario_invitador": usuario_invitador,
        "uid_invitador": uid_invitador,
        "sede_invitador": sede_invitador_nombre,
        "id_invitado": inv.id_invitado,
        "nombre_invitado": invitado.nombre if (invitado and revelar_invitado) else None,
        "usuario_invitado": invitado.usuario if (invitado and revelar_invitado) else None,
        "uid_invitado": invitado.uid_publico if invitado else None,
        "estado": inv.estado,
        "creada_en": inv.creada_en,
        "expira_en": inv.expira_en,
        "respondida_en": inv.respondida_en,
        "puede_aceptar": puede_aceptar,
        "es_recibida": es_recibida,
    }


def _obtenerSalaPorCodigo(codigo_sala: str, db: Session) -> SalaVideoconf:
    sala = db.scalars(
        select(SalaVideoconf).where(SalaVideoconf.codigo_sala == codigo_sala)
    ).first()
    if sala is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sala de videoconferencia no encontrada.",
        )
    return sala


def _cerrarSala(sala: SalaVideoconf, db: Session, motivo: str) -> None:
    ahora = _ahora()
    sala.activa = False
    for inv in sala.invitaciones:
        if inv.estado == "aceptada":
            inv.estado = "finalizada"
            inv.respondida_en = ahora
        elif inv.estado == "pendiente":
            inv.estado = "cancelada"
            inv.respondida_en = ahora
    db.flush()


# ---------------------------------------------------------------------------
# Gestor de conexiones WebSocket y señales HTTP
# ---------------------------------------------------------------------------

class ConnectionManager:
    def __init__(self):
        self.rooms: dict[str, dict[int, WebSocket]] = {}
        self.fallback_signals: dict[str, dict[int, list[dict]]] = {}
        self.pending_disconnects: dict[tuple[str, int], asyncio.Task] = {}

    async def connect(self, codigo: str, user_id: int, websocket: WebSocket) -> bool:
        await websocket.accept()
        room = self.rooms.setdefault(codigo, {})
        if len(room) >= 2 and user_id not in room:
            await websocket.close(code=4005, reason="Sala completa.")
            return False
        anterior = room.get(user_id)
        if anterior is not None:
            try:
                await anterior.close(code=1000, reason="Reemplazada por una nueva conexión.")
            except Exception:
                pass
        room[user_id] = websocket
        return True

    def disconnect(self, codigo: str, user_id: int, websocket: WebSocket | None = None) -> None:
        room = self.rooms.get(codigo)
        if room is not None:
            actual = room.get(user_id)
            if websocket is None or actual is websocket:
                room.pop(user_id, None)
            if not room:
                self.rooms.pop(codigo, None)

    def peer_of(self, codigo: str, user_id: int) -> int | None:
        for other in self.rooms.get(codigo, {}):
            if other != user_id:
                return other
        return None

    def has_user(self, codigo: str, user_id: int) -> bool:
        return user_id in self.rooms.get(codigo, {})

    async def send_to(self, codigo: str, user_id: int, payload: dict) -> None:
        ws = self.rooms.get(codigo, {}).get(user_id)
        if ws is not None:
            try:
                await ws.send_json(payload)
            except Exception:
                pass

    async def close_room(self, codigo: str, code: int = 1000, reason: str = "Llamada finalizada.") -> None:
        room = self.rooms.pop(codigo, {})
        for ws in list(room.values()):
            try:
                await ws.close(code=code, reason=reason)
            except Exception:
                pass


manager = ConnectionManager()


async def _finalizarTrasAusencia(codigo: str, user_id: int) -> None:
    await asyncio.sleep(15)
    manager.pending_disconnects.pop((codigo, user_id), None)
    if manager.has_user(codigo, user_id):
        return

    with SessionLocal() as db:
        sala = db.scalars(
            select(SalaVideoconf).where(SalaVideoconf.codigo_sala == codigo)
        ).first()
        if sala is None or not sala.activa:
            return
        aceptada = db.scalars(
            select(InvitacionVideoconf).where(
                InvitacionVideoconf.id_sala == sala.id,
                InvitacionVideoconf.estado == "aceptada",
            )
        ).first()
        if aceptada is None:
            if user_id == sala.id_iniciador and sala.activa:
                _cerrarSala(sala, db, "desconexion")
                db.commit()
            return
        _cerrarSala(sala, db, "desconexion")
        db.commit()
        otro = (
            sala.id_invitado
            if user_id == sala.id_iniciador
            else sala.id_iniciador
        )
        await manager.send_to(
            codigo,
            otro,
            {"type": "sala_finalizada", "motivo": "desconexion"},
        )
        await manager.close_room(codigo)


def _programarFinalizacion(codigo: str, user_id: int) -> None:
    key = (codigo, user_id)
    anterior = manager.pending_disconnects.pop(key, None)
    if anterior is not None:
        anterior.cancel()
    manager.pending_disconnects[key] = asyncio.create_task(
        _finalizarTrasAusencia(codigo, user_id)
    )


# ---------------------------------------------------------------------------
# Endpoints REST
# ---------------------------------------------------------------------------

@router.post(
    "/salas",
    response_model=SalaVideoconfResponse,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/sala",
    response_model=SalaVideoconfResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def _crearSala(
    data: SalaVideoconfCreate,
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    """Crea una sala e invitación para una videollamada 1:1."""
    # Serializa la creación de invitaciones del mismo usuario.
    db.execute(
        select(Empleado.id_empleado)
        .where(Empleado.id_empleado == user.id_empleado)
        .with_for_update()
    )
    _expirarInvitacionesVencidas(db)

    if not _tieneServicioVideo(user, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu servicio de videoconferencia no está habilitado.",
        )

    sede_user = _obtenerSedeUsuario(user, db)
    if sede_user is None and obtenerTipoAdmin(user) != "admin-g":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tienes una sede asignada.",
        )

    invitado = _resolverInvitado(data, user, db)
    sede_invitado = _obtenerSedeUsuario(invitado, db)
    id_sede_sala = sede_user or sede_invitado
    if id_sede_sala is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo determinar la sede de la sala.",
        )

    if _tieneLlamadaActiva(user.id_empleado, db):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya tienes una videollamada activa.",
        )

    pendiente = db.scalars(
        select(InvitacionVideoconf).where(
            InvitacionVideoconf.id_invitador == user.id_empleado,
            InvitacionVideoconf.estado == "pendiente",
        )
    ).first()
    if pendiente is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya tienes una invitación pendiente. Cancélala o espera a que expire.",
        )

    ahora = _ahora()
    sala = SalaVideoconf(
        codigo_sala=str(uuid.uuid4()),
        id_sede=id_sede_sala,
        id_iniciador=user.id_empleado,
        id_invitado=invitado.id_empleado,
        activa=True,
    )
    db.add(sala)
    db.flush()

    invitacion = InvitacionVideoconf(
        id_sala=sala.id,
        id_invitador=user.id_empleado,
        id_invitado=invitado.id_empleado,
        estado="pendiente",
        creada_en=ahora,
        expira_en=ahora + timedelta(minutes=CONFIG.video_invitacion_expira_minutos),
    )
    db.add(invitacion)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una invitación pendiente.",
        )

    db.refresh(sala)
    db.refresh(invitacion)
    return _serializarSala(sala, invitacion, user, db)


@router.get("/invitaciones", response_model=list[InvitacionVideoconfResponse])
def _listarInvitaciones(
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
    tipo: Annotated[str, Query(pattern="^(recibidas|enviadas)$")] = "recibidas",
    estado: Annotated[str, Query()] = "pendiente",
):
    """Bandeja de invitaciones recibidas o enviadas."""
    if estado != "todas" and estado not in ESTADOS_INVITACION:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Estado de invitación inválido.",
        )

    vencidas = _expirarInvitacionesVencidas(db)
    if vencidas:
        db.commit()

    stmt = select(InvitacionVideoconf)
    if tipo == "recibidas":
        stmt = stmt.where(InvitacionVideoconf.id_invitado == user.id_empleado)
    else:
        stmt = stmt.where(InvitacionVideoconf.id_invitador == user.id_empleado)

    if estado != "todas":
        stmt = stmt.where(InvitacionVideoconf.estado == estado)

    stmt = stmt.order_by(InvitacionVideoconf.creada_en.desc()).limit(50)
    invitaciones = db.scalars(stmt).all()
    return [_serializarInvitacion(inv, user, db) for inv in invitaciones]


@router.get("/invitaciones/{id_invitacion}", response_model=InvitacionVideoconfResponse)
def _obtenerInvitacion(
    id_invitacion: int,
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    inv = db.get(InvitacionVideoconf, id_invitacion)
    if (
        inv is None
        or user.id_empleado not in (inv.id_invitador, inv.id_invitado)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitación no encontrada.",
        )

    if _expirarInvitacionesVencidas(db, id_sala=inv.id_sala):
        db.commit()
        db.refresh(inv)

    return _serializarInvitacion(inv, user, db)


@router.post("/invitaciones/{id_invitacion}/aceptar", response_model=SalaVideoconfResponse)
async def _aceptarInvitacion(
    id_invitacion: int,
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    """Acepta una invitación y habilita la sala para ambos participantes."""
    # Serializa aceptaciones concurrentes del mismo invitado.
    db.execute(
        select(Empleado.id_empleado)
        .where(Empleado.id_empleado == user.id_empleado)
        .with_for_update()
    )

    inv = db.scalars(
        select(InvitacionVideoconf)
        .where(InvitacionVideoconf.id == id_invitacion)
        .with_for_update()
    ).first()
    if inv is None or inv.id_invitado != user.id_empleado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitación no encontrada.",
        )

    ahora = _ahora()
    if inv.estado == "pendiente" and inv.expira_en <= ahora:
        inv.estado = "expirada"
        inv.respondida_en = ahora
        if not db.scalars(
            select(InvitacionVideoconf.id).where(
                InvitacionVideoconf.id_sala == inv.id_sala,
                InvitacionVideoconf.estado == "aceptada",
            )
        ).first():
            inv.sala.activa = False
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="La invitación expiró.",
        )

    if inv.estado != "pendiente":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La invitación ya está {inv.estado}.",
        )
    if not inv.sala.activa:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La sala ya no está activa.",
        )
    if not _tieneServicioVideo(user, db) or not _tieneServicioVideo(inv.invitador, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La videoconferencia no está habilitada para ambos usuarios.",
        )
    if _tieneLlamadaActiva(user.id_empleado, db):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya tienes otra videollamada activa.",
        )
    if _tieneLlamadaActiva(inv.id_invitador, db):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El iniciador ya está en otra videollamada.",
        )

    inv.estado = "aceptada"
    inv.respondida_en = ahora
    inv.sala.id_invitado = user.id_empleado
    inv.sala.activa = True
    db.commit()
    db.refresh(inv)
    db.refresh(inv.sala)

    respuesta = _serializarSala(inv.sala, inv, user, db)
    await manager.send_to(
        inv.sala.codigo_sala,
        inv.id_invitador,
        {
            "type": "invitacion_aceptada",
            "invitacion_id": inv.id,
            "peer_id": user.id_empleado,
        },
    )
    return respuesta


@router.post("/invitaciones/{id_invitacion}/rechazar", status_code=status.HTTP_200_OK)
async def _rechazarInvitacion(
    id_invitacion: int,
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    inv = db.scalars(
        select(InvitacionVideoconf)
        .where(InvitacionVideoconf.id == id_invitacion)
        .with_for_update()
    ).first()
    if inv is None or inv.id_invitado != user.id_empleado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitación no encontrada.",
        )
    if inv.estado != "pendiente":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La invitación ya está {inv.estado}.",
        )

    ahora = _ahora()
    inv.estado = "rechazada" if inv.expira_en > ahora else "expirada"
    inv.respondida_en = ahora
    if not db.scalars(
        select(InvitacionVideoconf.id).where(
            InvitacionVideoconf.id_sala == inv.id_sala,
            InvitacionVideoconf.estado == "aceptada",
        )
    ).first():
        inv.sala.activa = False
    db.commit()

    await manager.send_to(
        inv.sala.codigo_sala,
        inv.id_invitador,
        {
            "type": "invitacion_rechazada",
            "invitacion_id": inv.id,
        },
    )
    return {"detalle": "Invitación rechazada."}


@router.get("/salas/{codigo_sala}", response_model=SalaVideoconfResponse)
@router.get("/sala/{codigo_sala}", response_model=SalaVideoconfResponse, include_in_schema=False)
def _obtenerSala(
    codigo_sala: str,
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    """Estado de la sala solo para sus participantes."""
    sala = _obtenerSalaPorCodigo(codigo_sala, db)
    if _expirarInvitacionesVencidas(db, id_sala=sala.id):
        db.commit()
        db.refresh(sala)

    invitacion = _invitacionDeParticipante(sala, user, db)
    if invitacion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sala de videoconferencia no encontrada.",
        )

    # El invitado solo puede ver la sala después de aceptar.
    if (
        user.id_empleado == sala.id_invitado
        and invitacion.estado != "aceptada"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debes aceptar la invitación para entrar a la sala.",
        )

    return _serializarSala(sala, invitacion, user, db)


@router.post("/salas/{codigo_sala}/cancelar", status_code=status.HTTP_200_OK)
async def _cancelarSala(
    codigo_sala: str,
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    sala = _obtenerSalaPorCodigo(codigo_sala, db)
    if sala.id_iniciador != user.id_empleado:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el iniciador puede cancelar la invitación.",
        )
    if not sala.activa:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La sala ya no está activa.",
        )

    _cerrarSala(sala, db, "cancelada_por_iniciador")
    db.commit()

    if sala.id_invitado is not None:
        await manager.send_to(
            codigo_sala,
            sala.id_invitado,
            {"type": "sala_cancelada", "motivo": "cancelada_por_iniciador"},
        )
    await manager.close_room(codigo_sala, reason="Invitación cancelada.")
    return {"detalle": "Invitación cancelada."}


@router.post("/salas/{codigo_sala}/salir", status_code=status.HTTP_200_OK)
@router.post("/sala/{codigo_sala}/finalizar", status_code=status.HTTP_200_OK, include_in_schema=False)
async def _salirSala(
    codigo_sala: str,
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    """Cuelga la llamada. Cualquiera de los dos participantes puede hacerlo."""
    sala = _obtenerSalaPorCodigo(codigo_sala, db)

    es_iniciador = sala.id_iniciador == user.id_empleado
    es_invitado_aceptado = bool(
        _participanteAceptado(sala, user, db)
    )
    if not es_iniciador and not es_invitado_aceptado:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No participas en esta videollamada.",
        )

    otro = sala.id_invitado if es_iniciador else sala.id_iniciador
    if sala.activa:
        _cerrarSala(sala, db, "colgo_participante")
        db.commit()

    await manager.send_to(
        codigo_sala,
        otro,
        {"type": "sala_finalizada", "motivo": "colgo_el_otro_participante"},
    )
    await manager.close_room(codigo_sala, reason="Llamada finalizada.")
    return {"detalle": "Videollamada finalizada."}


@router.get("/ice", response_model=IceConfigResponse)
def _obtenerIce(
    user: Annotated[Empleado, Depends(getCurrentUser)],
):
    """Servidores ICE para WebRTC. Incluye TURN solo si está configurado."""
    ice_servers = [IceServerConfig(urls=list(CONFIG.stun_urls))]
    if CONFIG.turn_url:
        ice_servers.append(
            IceServerConfig(
                urls=[CONFIG.turn_url],
                username=CONFIG.turn_username,
                credential=CONFIG.turn_credential,
            )
        )
    return IceConfigResponse(iceServers=ice_servers)


# ---------------------------------------------------------------------------
# Señalización HTTP de respaldo
# ---------------------------------------------------------------------------

def _validarSenalizacion(
    sala: SalaVideoconf,
    user: Empleado,
    db: Session,
) -> int:
    """Valida participación aceptada y devuelve el ID del otro participante."""
    if not sala.activa:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sala de videoconferencia no encontrada o finalizada.",
        )
    if _participanteAceptado(sala, user, db) is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No participas en esta videollamada.",
        )
    if not _tieneServicioVideo(user, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu servicio de videoconferencia no está habilitado.",
        )
    if user.id_empleado == sala.id_iniciador:
        if sala.id_invitado is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="La llamada aún no tiene invitado.",
            )
        return sala.id_invitado
    return sala.id_iniciador


@router.post("/salas/{codigo_sala}/signal", status_code=status.HTTP_200_OK)
@router.post("/sala/{codigo_sala}/signal", status_code=status.HTTP_200_OK, include_in_schema=False)
def _enviarSenalHttp(
    codigo_sala: str,
    data: SenalVideoconfCreate,
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    sala = _obtenerSalaPorCodigo(codigo_sala, db)
    otro = _validarSenalizacion(sala, user, db)

    if data.para_id != otro:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El destinatario de la señal no es el otro participante.",
        )
    if data.tipo == "offer" and user.id_empleado != sala.id_iniciador:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el iniciador puede generar la oferta.",
        )
    if data.tipo == "answer" and user.id_empleado == sala.id_iniciador:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El iniciador no responde su propia oferta.",
        )

    cola = manager.fallback_signals.setdefault(codigo_sala, {}).setdefault(otro, [])
    cola.append(
        {
            "type": data.tipo,
            "from": user.id_empleado,
            "sdp": data.sdp,
            "candidate": data.candidate,
        }
    )
    if len(cola) > 50:
        cola.pop(0)
    return {"status": "ok"}


@router.get("/salas/{codigo_sala}/signal")
@router.get("/sala/{codigo_sala}/signal", include_in_schema=False)
def _obtenerSenalesHttp(
    codigo_sala: str,
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    sala = _obtenerSalaPorCodigo(codigo_sala, db)
    otro = _validarSenalizacion(sala, user, db)

    cola = manager.fallback_signals.setdefault(codigo_sala, {}).pop(
        user.id_empleado, []
    )
    return {
        "signals": cola,
        "sala_activa": bool(sala.activa),
        "peer_conectado": manager.has_user(codigo_sala, otro),
    }


# ---------------------------------------------------------------------------
# WebSocket de señalización
# ---------------------------------------------------------------------------

def _autenticarWebSocket(token: str | None, websocket: WebSocket) -> int:
    auth_token = token or websocket.query_params.get("token")
    if not auth_token:
        auth_header = websocket.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            auth_token = auth_header[7:]
    if not auth_token:
        raise ValueError("Token de autenticación requerido.")
    from core.security import decodeToken

    payload = decodeToken(auth_token)
    if payload.get("type") != "access":
        raise ValueError("Tipo de token inválido.")
    return int(payload["sub"])


@router.websocket("/ws/{codigo_sala}")
async def _videoconferenciaWebSocket(
    websocket: WebSocket,
    codigo_sala: str,
    token: str | None = None,
):
    """Canal de señalización WebRTC con autorización por participante."""
    try:
        user_id = _autenticarWebSocket(token, websocket)
    except Exception:
        await websocket.close(code=4001, reason="Token inválido o expirado.")
        return

    with SessionLocal() as db:
        emp = db.get(Empleado, user_id)
        if emp is None or not emp.activo:
            await websocket.close(code=4003, reason="Usuario inactivo o no encontrado.")
            return

        sala = db.scalars(
            select(SalaVideoconf).where(SalaVideoconf.codigo_sala == codigo_sala)
        ).first()
        if sala is None or not sala.activa:
            await websocket.close(code=4004, reason="Sala no encontrada o inactiva.")
            return
        if _participanteAceptado(sala, emp, db) is None:
            await websocket.close(code=4003, reason="No participas en esta videollamada.")
            return
        if not _tieneServicioVideo(emp, db):
            await websocket.close(code=4003, reason="Servicio de videoconferencia deshabilitado.")
            return

        es_iniciador = sala.id_iniciador == emp.id_empleado
        invitado_id = sala.id_invitado

    # Si el usuario se reconecta, cancelar la finalización programada.
    tarea = manager.pending_disconnects.pop((codigo_sala, user_id), None)
    if tarea is not None:
        tarea.cancel()

    conectado = await manager.connect(codigo_sala, user_id, websocket)
    if not conectado:
        return

    peer_id = manager.peer_of(codigo_sala, user_id)
    await websocket.send_json(
        {
            "type": "sala_info",
            "es_iniciador": es_iniciador,
            "peer_id": peer_id,
            "estado": "aceptada",
            "user_id": user_id,
            "invitado_id": invitado_id,
        }
    )
    if peer_id is not None:
        # El nuevo participante ya recibió peer_id en sala_info; solo el
        # participante que ya estaba necesita el aviso de entrada.
        await manager.send_to(
            codigo_sala,
            peer_id,
            {"type": "peer_joined", "peer_id": user_id},
        )

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                mensaje = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "detail": "JSON inválido."})
                continue

            tipo = mensaje.get("type")
            if tipo == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            if tipo not in ("offer", "answer", "candidate"):
                await websocket.send_json(
                    {"type": "error", "detail": "Tipo de señal no permitido."}
                )
                continue
            if tipo == "offer" and not es_iniciador:
                await websocket.send_json(
                    {"type": "error", "detail": "Solo el iniciador puede ofertar."}
                )
                continue
            if tipo == "answer" and es_iniciador:
                await websocket.send_json(
                    {"type": "error", "detail": "El iniciador no responde su propia oferta."}
                )
                continue

            destino = manager.peer_of(codigo_sala, user_id)
            if destino is None:
                await websocket.send_json(
                    {"type": "error", "detail": "El otro participante no está conectado."}
                )
                continue

            payload = {"type": tipo, "from": user_id}
            if tipo == "candidate":
                payload["candidate"] = mensaje.get("candidate")
            else:
                payload["sdp"] = mensaje.get("sdp")
            await manager.send_to(codigo_sala, destino, payload)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        manager.disconnect(codigo_sala, user_id, websocket)
        # Si otra pestaña/dispositivo reemplazó esta conexión, no notificar salida.
        if not manager.has_user(codigo_sala, user_id):
            peer_id = manager.peer_of(codigo_sala, user_id)
            if peer_id is not None:
                await manager.send_to(
                    codigo_sala,
                    peer_id,
                    {"type": "peer_left", "peer_id": user_id},
                )
            _programarFinalizacion(codigo_sala, user_id)
