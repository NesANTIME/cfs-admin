import jwt
from typing import Annotated
from sqlalchemy.orm import Session
from db.controller import GetDatabase
from core.security import decodeToken
from db.template.empleado import Empleado
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error = False)


def _noAuth() -> HTTPException:
    return HTTPException(
        status_code = status.HTTP_401_UNAUTHORIZED,
        detail = "No autenticado.",
        headers = {"WWW-Authenticate": "Bearer"},
    )


def getCurrentUser(
    cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[Session, Depends(GetDatabase)],
) -> Empleado:
    if cred is None:
        raise _noAuth()
    try:
        payload = decodeToken(cred.credentials)
        if payload.get("type") != "access":     
            raise _noAuth()
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise _noAuth()

    user = db.get(Empleado, user_id)
    if user is None or not user.activo:
        raise _noAuth()
    return user


def requireTipos(*tipos: str):
    def _checker(user: Annotated[Empleado, Depends(getCurrentUser)]) -> Empleado:
        if (user.tipo not in tipos):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Permiso insuficiente.")
        return user
    return _checker


def obtenerTipoAdmin(user: Empleado) -> str:
    if user is None or not user.activo:
        return "usuario"

    if user.tipo in ("usuario_sede", "empleado"):
        return "usuario"

    rol_nombre = (user.rol.nombre if user.rol else "").strip().lower()
    nivel = getattr(user, "nivel_acceso", 0) or 0
    id_sede = getattr(user, "id_sede", None)

    if (
        (user.tipo == "tecnico_jefe" and nivel >= 5)
        or (user.tipo == "tecnico_jefe" and rol_nombre in ("administrador", "administrador general", "admin-g", "admin"))
    ):
        return "admin-g"

    if (
        user.tipo in ("tecnico", "tecnico_jefe")
        and id_sede is not None
        and rol_nombre in ("administrador de sede", "admin-s")
    ):
        return "admin-s"

    return "usuario"


def esAdminG(user: Empleado) -> bool:
    return obtenerTipoAdmin(user) == "admin-g"


def esAdminS(user: Empleado) -> bool:
    return obtenerTipoAdmin(user) == "admin-s"


def esAdminAltoRango(user: Empleado) -> bool:
    """Alias histórico para admin-g."""
    return esAdminG(user)


def requireAdminG(
    user: Annotated[Empleado, Depends(getCurrentUser)],
) -> Empleado:
    if (not esAdminG(user)):
        raise HTTPException(
            status_code = status.HTTP_403_FORBIDDEN,
            detail = "Permiso insuficiente: se requiere rango de Administrador General (admin-g).",
        )
    return user


def requireAdminAltoRango(
    user: Annotated[Empleado, Depends(getCurrentUser)],
) -> Empleado:
    return requireAdminG(user)


def requireAdmin(
    user: Annotated[Empleado, Depends(getCurrentUser)],
) -> Empleado:
    if (obtenerTipoAdmin(user) not in ("admin-g", "admin-s")):
        raise HTTPException(
            status_code = status.HTTP_403_FORBIDDEN,
            detail = "Permiso insuficiente: se requiere rango de administrador.",
        )
    return user


