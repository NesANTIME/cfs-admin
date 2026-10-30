from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from db.controller import getDb
from core.deps import getCurrentUser
from db.template.empleado import Empleado
from config.request import ChangePasswordRequest
from core.security import verifyPassword, hashearPassword
from config.config import getLongHashPassword

router = APIRouter(prefix="/me", tags=["Perfil"])


@router.post("/password", status_code=status.HTTP_200_OK)
def _cambiarPassword(
    data: ChangePasswordRequest,
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    """Permite al usuario autenticado cambiar su propia contraseña."""
    # Verificar contraseña actual
    if not verifyPassword(user.contrasena_hash, data.contrasena_actual):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual no es correcta.",
        )

    # Validar longitud mínima
    min_len = getLongHashPassword()
    if len(data.contrasena_nueva.strip()) < min_len:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"La nueva contraseña debe tener al menos {min_len} caracteres.",
        )

    # Hashear y actualizar
    user.contrasena_hash = hashearPassword(data.contrasena_nueva)
    db.commit()

    return {"detalle": "Contraseña actualizada exitosamente."}
