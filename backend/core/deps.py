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
        if user.tipo not in tipos:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Permiso insuficiente.")
        return user
    return _checker
