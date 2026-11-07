from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from db.controller import getDb
from core.deps import getCurrentUser, requireAdminG, obtenerTipoAdmin
from db.template.sede import Sede
from db.template.empleado import Empleado, Tecnico
from db.template.rol import Rol
from config.request import SedeCreate, SedeResponse, SedeDetalleResponse, SedeTecnicoUpdate, AdminSedeInfo

router = APIRouter(prefix = "/sedes", tags = ["Sedes"])


def _construirSedeResponse(sede: Sede, db: Session) -> SedeResponse:
    rol_admin_s = db.execute(
        select(Rol).where(Rol.nombre == "Administrador de Sede")
    ).scalar_one_or_none()

    admins_list = []
    if rol_admin_s is not None:
        tecnicos = db.scalars(
            select(Tecnico)
            .where(Tecnico.id_sede == sede.id_sede)
            .where(Tecnico.id_rol == rol_admin_s.id_rol)
            .where(Tecnico.activo == True)
            .order_by(Tecnico.nombre.asc())
        ).all()
        admins_list = [
            AdminSedeInfo(
                id_empleado=t.id_empleado,
                nombre=t.nombre,
                usuario=t.usuario,
                activo=t.activo,
            )
            for t in tecnicos
        ]

    admin_actual = admins_list[0] if admins_list else None

    return SedeResponse(
        id_sede=sede.id_sede,
        nombre=sede.nombre,
        ubicacion=sede.ubicacion,
        descripcion=sede.descripcion,
        id_tecnico_jefe=sede.id_tecnico_jefe,
        admin_s=admin_actual,
        admins_s_disponibles=admins_list,
    )


@router.get("", response_model = list[SedeResponse])
def _listarSedes(
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    """Retorna las sedes disponibles para el usuario con su técnico admin-s asignado."""
    tipo_admin = obtenerTipoAdmin(user)

    if (tipo_admin == "admin-g"):
        sedes = db.scalars(select(Sede).order_by(Sede.id_sede.asc())).all()
        return [_construirSedeResponse(s, db) for s in sedes]

    id_sede_usuario = getattr(user, "id_sede", None)
    if (id_sede_usuario is not None):
        sedes = db.scalars(
            select(Sede).where(Sede.id_sede == id_sede_usuario).order_by(Sede.id_sede.asc())
        ).all()
        return [_construirSedeResponse(s, db) for s in sedes]

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
    return _construirSedeResponse(nueva_sede, db)


@router.put("/{id_sede}/tecnico", response_model = SedeResponse)
def _asignarTecnicoSede(
    id_sede: int,
    data: SedeTecnicoUpdate,
    admin: Annotated[Empleado, Depends(requireAdminG)],
    db: Annotated[Session, Depends(getDb)],
):
    """Asigna o reasigna el técnico Administrador de Sede (admin-s) de una sede."""
    sede = db.get(Sede, id_sede)
    if sede is None:
        raise HTTPException(
            status_code = status.HTTP_404_NOT_FOUND,
            detail = f"La sede con ID {id_sede} no existe.",
        )

    rol_admin_s = db.execute(
        select(Rol).where(Rol.nombre == "Administrador de Sede")
    ).scalar_one_or_none()
    if rol_admin_s is None:
        rol_admin_s = Rol(nombre="Administrador de Sede", descripcion="Control exclusivo de una sede asignada")
        db.add(rol_admin_s)
        db.flush()

    if data.id_empleado is not None:
        tecnico = db.get(Tecnico, data.id_empleado)
        if tecnico is None or not tecnico.activo:
            raise HTTPException(
                status_code = status.HTTP_404_NOT_FOUND,
                detail = "El técnico seleccionado no existe o no está activo.",
            )
        if tecnico.id_rol != rol_admin_s.id_rol:
            raise HTTPException(
                status_code = status.HTTP_400_BAD_REQUEST,
                detail = "El usuario seleccionado debe tener rol de Administrador de Sede (admin-s).",
            )

        # Asignar la sede al técnico
        tecnico.id_sede = id_sede
    else:
        # Desvincular admin-s existente si lo hubiera
        tecnicos_sede = db.scalars(
            select(Tecnico)
            .where(Tecnico.id_sede == id_sede)
            .where(Tecnico.id_rol == rol_admin_s.id_rol)
        ).all()
        for t in tecnicos_sede:
            t.id_sede = None

    db.commit()
    db.refresh(sede)
    return _construirSedeResponse(sede, db)
