import jwt
from typing import Annotated
from sqlalchemy.orm import Session
from db.controller import getDb
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
    db: Annotated[Session, Depends(getDb)],
) -> Empleado:
    if cred is None:
        raise _noAuth()
    try:
        payload = decodeToken(cred.credentials)
        if payload.get("type") != "access":      # un refresh token NO sirve como access
            raise _noAuth()
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise _noAuth()

    user = db.get(Empleado, user_id)
    if user is None or not user.activo:
        raise _noAuth()
    return user


def requireTipos(*tipos: str):
    """Uso: Depends(requireTipos("tecnico_jefe"))"""
    def _checker(user: Annotated[Empleado, Depends(getCurrentUser)]) -> Empleado:
        if (user.tipo not in tipos):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Permiso insuficiente.")
        return user
    return _checker


def obtenerTipoAdmin(user: Empleado) -> str:
    """Clasifica al usuario en 'admin-g', 'admin-s' o 'usuario'."""
    if (user is None or not user.activo):
        return "usuario"
    rol_nombre = (user.rol.nombre if user.rol else "").strip().lower()
    nivel = getattr(user, "nivel_acceso", 0) or 0
    id_sede = getattr(user, "id_sede", None)

    # admin-g: Administrador general / rango más alto (acceso a todas las sedes)
    if (
        rol_nombre in ("administrador", "administrador general", "admin-g", "admin")
        or (user.tipo == "tecnico_jefe" and nivel >= 5)
    ):
        return "admin-g"

    # admin-s: Administrador de sede (acceso exclusivo a una sede)
    if (
        rol_nombre in ("administrador de sede", "admin-s")
        or (id_sede is not None and nivel < 5)
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
    """Exige rol de Administrador General (admin-g)."""
    if (not esAdminG(user)):
        raise HTTPException(
            status_code = status.HTTP_403_FORBIDDEN,
            detail = "Permiso insuficiente: se requiere rango de Administrador General (admin-g).",
        )
    return user


def requireAdminAltoRango(
    user: Annotated[Empleado, Depends(getCurrentUser)],
) -> Empleado:
    """Alias histórico para requireAdminG."""
    return requireAdminG(user)


def requireAdmin(
    user: Annotated[Empleado, Depends(getCurrentUser)],
) -> Empleado:
    """Permite tanto a admin-g como a admin-s."""
    if (obtenerTipoAdmin(user) not in ("admin-g", "admin-s")):
        raise HTTPException(
            status_code = status.HTTP_403_FORBIDDEN,
            detail = "Permiso insuficiente: se requiere rango de administrador.",
        )
    return user


