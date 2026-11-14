from typing import Annotated
from sqlalchemy import select
from db.template.rol import Rol
from db.template.sede import Sede
from db.controller import GetDatabase
from sqlalchemy.orm import Session, selectinload
from db.template.empleado import Empleado, Tecnico
from fastapi import APIRouter, Depends, HTTPException, status
from core.deps import getCurrentUser, requireAdminG, obtenerTipoAdmin
from config.utils.request import SedeCreate, SedeResponse, SedeDetalleResponse, SedeTecnicoUpdate, AdminSedeInfo


router = APIRouter(prefix = "/sedes", tags = ["Sedes"])


def _construirSedeResponse(sede: Sede, db: Session, rol_admin_s_id: int | None = None) -> SedeResponse:
    admins_list = []
    if rol_admin_s_id is not None:
        tecnicos = [t for t in sede.tecnicos if t.id_rol == rol_admin_s_id]
        tecnicos.sort(key=lambda t: t.nombre)
        admins_list = [
            AdminSedeInfo(
                id_empleado=t.id_empleado,
                nombre=t.nombre,
                usuario=t.usuario,
                activo=t.activo,
            )
            for t in tecnicos
        ]

    admin_actual = next((a for a in admins_list if a.activo), None)

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
    db: Annotated[Session, Depends(GetDatabase)],
):
    tipo_admin = obtenerTipoAdmin(user)
    rol_admin_s = db.execute(
        select(Rol).where(Rol.nombre == "Administrador de Sede")
    ).scalar_one_or_none()
    rol_id = rol_admin_s.id_rol if rol_admin_s else None

    if (tipo_admin == "admin-g"):
        sedes = db.scalars(
            select(Sede)
            .options(selectinload(Sede.tecnicos))
            .order_by(Sede.id_sede.asc())
        ).all()
        return [_construirSedeResponse(s, db, rol_id) for s in sedes]

    id_sede_usuario = getattr(user, "id_sede", None)
    if (id_sede_usuario is not None):
        sedes = db.scalars(
            select(Sede)
            .where(Sede.id_sede == id_sede_usuario)
            .options(selectinload(Sede.tecnicos))
            .order_by(Sede.id_sede.asc())
        ).all()
        return [_construirSedeResponse(s, db, rol_id) for s in sedes]

    return []


@router.get("/{id_sede}", response_model = SedeDetalleResponse)
def _obtenerSede(
    id_sede: int,
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(GetDatabase)],
):
    tipo_admin = obtenerTipoAdmin(user)

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
    db: Annotated[Session, Depends(GetDatabase)],
):
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
    db: Annotated[Session, Depends(GetDatabase)],
):
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

        tecnico.id_sede = id_sede
    else:
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
