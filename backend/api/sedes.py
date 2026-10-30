from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from db.controller import getDb
from core.deps import getCurrentUser, requireAdminG, obtenerTipoAdmin
from db.template.sede import Sede
from db.template.empleado import Empleado
from config.request import SedeCreate, SedeResponse, SedeDetalleResponse

router = APIRouter(prefix = "/sedes", tags = ["Sedes"])


@router.get("", response_model = list[SedeResponse])
def _listarSedes(
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    """Retorna las sedes disponibles para el usuario:
    - admin-g: puede ver y gestionar todas las sedes registradas.
    - admin-s: solo puede ver su sede asignada.
    - usuario normal: solo ve su sede asignada (si tiene).
    """
    tipo_admin = obtenerTipoAdmin(user)

    if (tipo_admin == "admin-g"):
        sedes = db.scalars(select(Sede).order_by(Sede.id_sede.asc())).all()
        return sedes

    id_sede_usuario = getattr(user, "id_sede", None)
    if (id_sede_usuario is not None):
        sedes = db.scalars(
            select(Sede).where(Sede.id_sede == id_sede_usuario).order_by(Sede.id_sede.asc())
        ).all()
        return sedes

    return []


@router.get("/{id_sede}", response_model = SedeDetalleResponse)
def _obtenerSede(
    id_sede: int,
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    """Retorna la información específica de una sede y sus dispositivos asociados."""
    tipo_admin = obtenerTipoAdmin(user)

    # El admin-s o usuario común solo puede acceder a su propia sede
    if (tipo_admin != "admin-g"):
        id_sede_usuario = getattr(user, "id_sede", None)
        if (id_sede_usuario != id_sede):
            raise HTTPException(
                status_code = status.HTTP_403_FORBIDDEN,
                detail = "Permiso denegado: no estás autorizado para acceder a esta sede.",
            )

    sede = db.execute(
        select(Sede).where(Sede.id_sede == id_sede).options(selectinload(Sede.dispositivos))
    ).scalar_one_or_none()

    if (sede is None):
        raise HTTPException(
            status_code = status.HTTP_404_NOT_FOUND,
            detail = f"La sede con ID {id_sede} no existe.",
        )

    return sede


@router.post("", response_model = SedeResponse, status_code = status.HTTP_201_CREATED)
def _crearSede(
    data: SedeCreate,
    admin: Annotated[Empleado, Depends(requireAdminG)],
    db: Annotated[Session, Depends(getDb)],
):
    """Crea una nueva sede con nombre, ubicación y descripción (exclusivo para admin-g)."""
    nombre = data.nombre.strip()
    ubicacion = data.ubicacion.strip()
    descripcion = data.descripcion.strip()

    if (not nombre or not ubicacion or not descripcion):
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = "El nombre, la ubicación y la descripción son obligatorios y no pueden estar vacíos.",
        )

    existente = db.execute(select(Sede).where(Sede.nombre == nombre)).scalar_one_or_none()
    if (existente is not None):
        raise HTTPException(
            status_code = status.HTTP_409_CONFLICT,
            detail = f"Ya existe una sede registrada con el nombre '{nombre}'.",
        )

    nueva_sede = Sede(
        nombre = nombre,
        ubicacion = ubicacion,
        descripcion = descripcion,
        id_tecnico_jefe = admin.id_empleado if admin.tipo == "tecnico_jefe" else None,
    )
    db.add(nueva_sede)
    db.commit()
    db.refresh(nueva_sede)
    return nueva_sede
