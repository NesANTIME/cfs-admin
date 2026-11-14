from typing import Annotated
from sqlalchemy.orm import Session
from core.deps import getCurrentUser
from db.controller import GetDatabase
from db.template.empleado import Empleado
from config.utils.db import getLongHashPassword
from config.utils.request import ChangePasswordRequest
from core.security import verifyPassword, hashearPassword
from fastapi import APIRouter, Depends, HTTPException, status


router = APIRouter(prefix="/me", tags=["Perfil"])


@router.post("/password", status_code=status.HTTP_200_OK)
def _cambiarPassword(
    data: ChangePasswordRequest,
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(GetDatabase)],
):
    if not verifyPassword(user.contrasena_hash, data.contrasena_actual):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual no es correcta.",
        )

    min_len = getLongHashPassword()
    nueva_contrasena = data.contrasena_nueva.strip()
    if len(nueva_contrasena) < min_len:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"La nueva contraseña debe tener al menos {min_len} caracteres.",
        )

    user.contrasena_hash = hashearPassword(nueva_contrasena)
    db.commit()

    return {"detalle": "Contraseña actualizada exitosamente."}
