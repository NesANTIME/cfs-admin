import json
import uuid
from typing import Annotated, Dict, List
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from db.controller import getDb
from core.deps import getCurrentUser, obtenerTipoAdmin
from db.template.empleado import Empleado
from db.template.sala_videoconf import SalaVideoconf
from db.template.servicio_usuario import ServicioUsuario
from db.template.contacto import Contacto
from config.request import SalaVideoconfCreate, SalaVideoconfResponse

router = APIRouter(prefix="/videoconferencia", tags=["Videoconferencia"])

# Gestor de conexiones WebSocket en memoria para señalización WebRTC
class ConnectionManager:
    def __init__(self):
        # Map: codigo_sala -> list[WebSocket]
        self.active_rooms: Dict[str, List[WebSocket]] = {}
        # Fallback HTTP signals: codigo_sala -> list[{from, to, signal}]
        self.fallback_signals: Dict[str, List[dict]] = {}

    async def connect(self, room: str, websocket: WebSocket):
        await websocket.accept()
        if room not in self.active_rooms:
            self.active_rooms[room] = []
        self.active_rooms[room].append(websocket)

    def disconnect(self, room: str, websocket: WebSocket):
        if room in self.active_rooms:
            if websocket in self.active_rooms[room]:
                self.active_rooms[room].remove(websocket)
            if not self.active_rooms[room]:
                del self.active_rooms[room]

    async def broadcast(self, room: str, sender: WebSocket, message: str):
        if room in self.active_rooms:
            for connection in self.active_rooms[room]:
                if connection != sender:
                    try:
                        await connection.send_text(message)
                    except Exception:
                        pass


manager = ConnectionManager()


def _obtenerSedeUsuario(emp: Empleado, db: Session) -> int | None:
    id_s = getattr(emp, "id_sede", None)
    if id_s is not None:
        return id_s
    serv = db.scalars(select(ServicioUsuario).where(ServicioUsuario.id_empleado == emp.id_empleado)).first()
    return serv.id_sede if serv else None


def _tieneServicioVideo(emp: Empleado, id_sede: int, db: Session) -> bool:
    if obtenerTipoAdmin(emp) == "admin-g":
        return True
    serv = db.scalars(
        select(ServicioUsuario).where(
            ServicioUsuario.id_empleado == emp.id_empleado,
            ServicioUsuario.tipo_servicio == "videoconferencia",
            ServicioUsuario.id_sede == id_sede,
            ServicioUsuario.habilitado == True,  # noqa: E712
        )
    ).first()
    return serv is not None


@router.post("/sala", response_model=SalaVideoconfResponse, status_code=status.HTTP_201_CREATED)
def _crearSala(
    data: SalaVideoconfCreate,
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    """Crea una sala de videoconferencia para usuarios de la misma sede con el servicio habilitado."""
    sede_user = _obtenerSedeUsuario(user, db)
    if sede_user is None and obtenerTipoAdmin(user) != "admin-g":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No tienes una sede asignada.")

    id_sede_final = sede_user or 1

    if not _tieneServicioVideo(user, id_sede_final, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu servicio de videoconferencia no está habilitado por el administrador.",
        )

    # Si se invitó a un contacto específico, validar que sea de la misma sede y tenga el servicio
    id_invitado = None
    if data.id_contacto:
        invitado = db.get(Empleado, data.id_contacto)
        if invitado:
            sede_inv = _obtenerSedeUsuario(invitado, db)
            if sede_inv != id_sede_final and obtenerTipoAdmin(user) != "admin-g":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Solo puedes iniciar videoconferencias con contactos de tu misma sede.",
                )
            if not _tieneServicioVideo(invitado, id_sede_final, db):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="El contacto invitado no tiene habilitado el servicio de videoconferencia.",
                )
            id_invitado = invitado.id_empleado

    codigo = str(uuid.uuid4())[:18]
    nueva_sala = SalaVideoconf(
        codigo_sala=codigo,
        id_sede=id_sede_final,
        id_iniciador=user.id_empleado,
        id_invitado=id_invitado,
        activa=True,
    )
    db.add(nueva_sala)
    db.commit()
    db.refresh(nueva_sala)

    return nueva_sala


@router.get("/sala/{codigo_sala}", response_model=SalaVideoconfResponse)
def _obtenerSala(
    codigo_sala: str,
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    """Consulta la sala de videoconferencia y verifica que el usuario pertenezca a la misma sede."""
    sala = db.scalars(select(SalaVideoconf).where(SalaVideoconf.codigo_sala == codigo_sala)).first()
    if sala is None or not sala.activa:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="La sala de videoconferencia no existe o ya ha finalizado.")

    sede_user = _obtenerSedeUsuario(user, db)
    if obtenerTipoAdmin(user) != "admin-g":
        if sede_user is None or sede_user != sala.id_sede:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Esta sala pertenece a otra sede. No estás autorizado para ingresar.",
            )

    return sala


@router.post("/sala/{codigo_sala}/finalizar", status_code=status.HTTP_200_OK)
def _finalizarSala(
    codigo_sala: str,
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    """Finaliza una sala de videoconferencia."""
    sala = db.scalars(select(SalaVideoconf).where(SalaVideoconf.codigo_sala == codigo_sala)).first()
    if sala:
        sala.activa = False
        db.commit()
    return {"detalle": "Videoconferencia finalizada."}


# --- Señalización HTTP Fallback (para navegadores o proxies que no soportan WebSocket) ---

@router.post("/sala/{codigo_sala}/signal", status_code=status.HTTP_200_OK)
def _enviarSenalHttp(
    codigo_sala: str,
    signal_data: dict,
    user: Annotated[Empleado, Depends(getCurrentUser)],
):
    """Guarda una señal WebRTC (offer/answer/ice) para fallback HTTP."""
    if codigo_sala not in manager.fallback_signals:
        manager.fallback_signals[codigo_sala] = []
    manager.fallback_signals[codigo_sala].append({
        "sender_id": user.id_empleado,
        "data": signal_data,
    })
    # Mantener máximo 50 señales
    if len(manager.fallback_signals[codigo_sala]) > 50:
        manager.fallback_signals[codigo_sala].pop(0)
    return {"status": "ok"}


@router.get("/sala/{codigo_sala}/signal")
def _obtenerSenalesHttp(
    codigo_sala: str,
    user: Annotated[Empleado, Depends(getCurrentUser)],
):
    """Obtiene señales pendientes enviadas por el otro par."""
    signals = manager.fallback_signals.get(codigo_sala, [])
    # Extraer señales de otros remitentes
    remotas = [s["data"] for s in signals if s["sender_id"] != user.id_empleado]
    # Limpiar las consumidas de ese remitente
    manager.fallback_signals[codigo_sala] = [s for s in signals if s["sender_id"] == user.id_empleado]
    return {"signals": remotas}


# --- Señalización WebSocket WebRTC ---

@router.websocket("/ws/{codigo_sala}")
async def _videoconferenciaWebSocket(websocket: WebSocket, codigo_sala: str):
    """Canal WebSocket para señalización WebRTC (ofertas, respuestas y candidatos ICE)."""
    await manager.connect(codigo_sala, websocket)
    try:
        while True:
            raw_text = await websocket.receive_text()
            # Retransmitir al otro participante de la llamada
            await manager.broadcast(codigo_sala, websocket, raw_text)
    except WebSocketDisconnect:
        manager.disconnect(codigo_sala, websocket)
        # Notificar al otro participante que el par se desconectó
        await manager.broadcast(codigo_sala, websocket, json.dumps({"type": "peer_disconnected"}))
    except Exception:
        manager.disconnect(codigo_sala, websocket)
