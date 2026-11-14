import jwt
from typing import Annotated
from config.load import CONFIG
from core.limiter import limiter
from sqlalchemy.orm import Session
from db.controller import GetDatabase
from sqlalchemy import select, update
from config.utils.db import ConfigBloq
from db.template.refresh_token import RefreshToken
from datetime import datetime, timedelta, timezone
from db.template.empleado import Empleado, UsuarioSede
from core.deps import getCurrentUser, esAdminAltoRango, obtenerTipoAdmin
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from config.utils.request import TokenResponse, LoginRequest, RefreshRequest, MeResponse
from core.security import (
    verifyPassword, requireReHash, rehashearPassword, get_dummy_hash,
    createAccessToken, createRefreshToken, decodeToken,
)


router = APIRouter(tags = ['Autenticacion'])

MAX_INTENTOS, BLOQUEO_MINUTOS = ConfigBloq()


def _error401(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers = {'WWW-Authenticate': 'Bearer'})


def _emitirTokens(db: Session, user: Empleado) -> dict:
    access = createAccessToken(subject = user.id_empleado)
    refresh = createRefreshToken(subject = user.id_empleado)
    p = decodeToken(refresh)
    db.add(RefreshToken(
        jti = p["jti"], id_empleado = user.id_empleado,
        expira = datetime.fromtimestamp(p["exp"], timezone.utc),
    ))
    db.commit()
    return {
        "access_token": access, "refresh_token": refresh,
        "token_type": "bearer", "expires_in": CONFIG.Jwt.Access_token * 60,
    }


@router.post('/login', response_model = TokenResponse)
@limiter.limit("5/minute")
def _login(request: Request, data: LoginRequest, db: Annotated[Session, Depends(GetDatabase)]):
    ahora = datetime.now(timezone.utc)
    user = db.execute(select(Empleado).where(Empleado.usuario == data.username)).scalar_one_or_none()

    bloqueado = bool(user and user.bloqueado_hasta and user.bloqueado_hasta > ahora)
    valida = verifyPassword(user.contrasena_hash if user else get_dummy_hash(), data.password)

    if (not user) or bloqueado or (not user.activo) or (not valida):
        if user and (not bloqueado) and (not valida):
            user.intentos_fallidos += 1
            if user.intentos_fallidos >= MAX_INTENTOS:
                user.bloqueado_hasta = ahora + timedelta(minutes = BLOQUEO_MINUTOS)
                user.intentos_fallidos = 0
            db.commit()
        raise _error401("Usuario o contraseña incorrectos.")

    user.intentos_fallidos = 0
    user.bloqueado_hasta = None
    if requireReHash(user.contrasena_hash):
        user.contrasena_hash = rehashearPassword(data.password)

    return _emitirTokens(db, user)


@router.post('/refresh', response_model = TokenResponse)
@limiter.limit("30/minute")
def _refresh(request: Request, data: RefreshRequest, db: Annotated[Session, Depends(GetDatabase)]):
    try:
        p = decodeToken(data.refresh_token)
    except jwt.PyJWTError:
        raise _error401("Refresh token no válido o expirado.")
    if p.get("type") != "refresh":
        raise _error401("Refresh token no válido o expirado.")

    row = db.get(RefreshToken, p["jti"])
    if row is None:
        raise _error401("Refresh token no válido o expirado.")

    if row.revocado:
        db.execute(update(RefreshToken).where(RefreshToken.id_empleado == row.id_empleado).values(revocado = True))
        db.commit()
        raise _error401("Refresh token no válido o expirado.")

    user = db.get(Empleado, row.id_empleado)
    if user is None or not user.activo:
        raise _error401("Refresh token no válido o expirado.")

    row.revocado = True
    db.flush()
    return _emitirTokens(db, user)


@router.post('/logout', status_code = status.HTTP_204_NO_CONTENT)
def _logout(
    data: RefreshRequest,
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(GetDatabase)],
):
    try:
        payload = decodeToken(data.refresh_token)
        if int(payload.get("sub", -1)) != user.id_empleado:
            return Response(status_code = status.HTTP_204_NO_CONTENT)
        row = db.get(RefreshToken, payload["jti"])
        if row and row.id_empleado == user.id_empleado:
            row.revocado = True
            db.commit()
    except (jwt.PyJWTError, ValueError):
        pass
    return Response(status_code = status.HTTP_204_NO_CONTENT)


@router.get('/me')
def _me(user: Annotated[Empleado, Depends(getCurrentUser)], db: Annotated[Session, Depends(GetDatabase)]):
    tipo_admin = obtenerTipoAdmin(user)
    id_sede = getattr(user, "id_sede", None)
    sede_nombre = None
    if id_sede is not None:
        from db.template.sede import Sede
        sede_obj = db.get(Sede, id_sede)
        if sede_obj:
            sede_nombre = sede_obj.nombre

    return {
        "id": user.id_empleado,
        "nombre": user.nombre,
        "usuario": user.usuario,
        "tipo": user.tipo,
        "rol": user.rol.nombre if user.rol else "Sin rol",
        "tipo_admin": tipo_admin,
        "nivel_acceso": getattr(user, "nivel_acceso", None),
        "id_sede": id_sede,
        "sede_nombre": sede_nombre,
        "uid_publico": getattr(user, "uid_publico", None),
        "es_admin": tipo_admin in ("admin-g", "admin-s"),
        "es_admin_g": tipo_admin == "admin-g",
        "es_admin_s": tipo_admin == "admin-s",
        "direccion": user.direccion if isinstance(user, UsuarioSede) else None,
        "servicios": [
            {"tipo_servicio": s.tipo_servicio, "habilitado": s.habilitado if tipo_admin != "admin-g" else True}
            for s in user.servicios_usuario
            if id_sede is None or s.id_sede == id_sede or s.id_sede is None
        ] if user.servicios_usuario else (
            [{"tipo_servicio": "videoconferencia", "habilitado": True}, {"tipo_servicio": "chat", "habilitado": True}]
            if tipo_admin == "admin-g" else []
        ),
    }

