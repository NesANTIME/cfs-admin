import uuid
from typing import Annotated
from sqlalchemy import select
from db.template.rol import Rol
from db.template.sede import Sede
from sqlalchemy.orm import Session
from db.controller import GetDatabase
from core.security import hashearPassword
from config.utils.db import getLongHashPassword
from db.template.servicio_usuario import ServicioUsuario
from fastapi import APIRouter, Depends, HTTPException, status
from db.template.empleado import Empleado, Tecnico, UsuarioSede
from config.utils.request import UsuarioCreate, UsuarioResponse, UsuarioEstadoUpdate
from core.deps import getCurrentUser, requireAdmin, obtenerTipoAdmin
from db.template.refresh_token import RefreshToken
from sqlalchemy import delete, func


router = APIRouter(prefix="/sedes", tags=["Usuarios de Sede"])


def _verificarAccesoSede(user: Empleado, id_sede: int) -> None:
    tipo_admin = obtenerTipoAdmin(user)
    if tipo_admin == "admin-g":
        return
    id_sede_usuario = getattr(user, "id_sede", None)
    if id_sede_usuario != id_sede:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permiso denegado: no estás autorizado para gestionar esta sede.",
        )


@router.post(
    "/{id_sede}/usuarios",
    response_model=UsuarioResponse,
    status_code=status.HTTP_201_CREATED,
)
def _crearUsuarioEnSede(
    id_sede: int,
    data: UsuarioCreate,
    user: Annotated[Empleado, Depends(requireAdmin)],
    db: Annotated[Session, Depends(GetDatabase)],
):
    _verificarAccesoSede(user, id_sede)
    tipo_admin = obtenerTipoAdmin(user)

    sede = db.get(Sede, id_sede)
    if sede is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La sede con ID {id_sede} no existe.",
        )

    if tipo_admin == "admin-s":
        if data.es_admin_s or data.tipo != "usuario_sede":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permiso denegado: un Administrador de Sede solo puede registrar usuarios normales (clientes/empleados).",
            )

    nombre = data.nombre.strip()
    usuario = data.usuario.strip()
    contrasena = data.contrasena.strip()

    if not nombre or not usuario:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Nombre y usuario son obligatorios.",
        )

    min_len = getLongHashPassword()
    if len(contrasena) < min_len:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"La contraseña debe tener al menos {min_len} caracteres.",
        )

    existente = db.execute(select(Empleado).where(Empleado.usuario == usuario)).scalar_one_or_none()
    if existente is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El nombre de usuario '{usuario}' ya está en uso. Por favor elija otro.",
        )

    uid_publico = str(uuid.uuid4())
    contrasena_hash = hashearPassword(contrasena)

    if data.es_admin_s:
        rol_admin_s = db.execute(
            select(Rol).where(Rol.nombre == "Administrador de Sede")
        ).scalar_one_or_none()
        if rol_admin_s is None:
            rol_admin_s = Rol(nombre="Administrador de Sede", descripcion="Control exclusivo de una sede asignada")
            db.add(rol_admin_s)
            db.flush()

        admins_s_count = db.scalar(
            select(func.count(Tecnico.id_empleado))
            .where(
                Tecnico.id_sede == id_sede,
                Tecnico.id_rol == rol_admin_s.id_rol,
                Tecnico.activo == True,
            )
        ) or 0

        if admins_s_count >= 3:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Límite alcanzado: cada sede puede tener como máximo 3 Administradores de Sede (admin-s) activos (actuales: {admins_s_count}).",
            )

        nuevo_emp = Tecnico(
            nombre=nombre,
            usuario=usuario,
            contrasena_hash=contrasena_hash,
            id_rol=rol_admin_s.id_rol,
            id_sede=id_sede,
            uid_publico=uid_publico,
            activo=True,
        )
    else:
        rol_usuario = db.scalars(
            select(Rol).where(Rol.nombre == "Usuario Sede")
        ).first()
        if rol_usuario is None:
            rol_usuario = db.scalars(
                select(Rol).where(Rol.nombre.in_(["Empleado", "Cliente"]))
            ).first()
        if rol_usuario is None:
            rol_usuario = Rol(nombre="Usuario Sede", descripcion="Usuario cliente de servicios de sede")
            db.add(rol_usuario)
            db.flush()

        nuevo_emp = UsuarioSede(
            nombre=nombre,
            usuario=usuario,
            contrasena_hash=contrasena_hash,
            id_rol=rol_usuario.id_rol,
            id_sede=id_sede,
            direccion=data.direccion.strip() if data.direccion else None,
            uid_publico=uid_publico,
            activo=True,
        )

    db.add(nuevo_emp)
    db.flush()

    db.add_all([
        ServicioUsuario(
            id_empleado=nuevo_emp.id_empleado,
            tipo_servicio="videoconferencia",
            habilitado=False,
            id_sede=id_sede,
        ),
        ServicioUsuario(
            id_empleado=nuevo_emp.id_empleado,
            tipo_servicio="chat",
            habilitado=False,
            id_sede=id_sede,
        ),
    ])

    db.commit()
    db.refresh(nuevo_emp)

    return nuevo_emp


def _verificarAccesoObjetivo(objetivo: Empleado, id_sede: int, db: Session) -> None:
    id_sede_objetivo = getattr(objetivo, "id_sede", None)
    if id_sede_objetivo != id_sede:
        tiene_servicio_en_sede = db.scalars(
            select(ServicioUsuario).where(
                ServicioUsuario.id_empleado == objetivo.id_empleado,
                ServicioUsuario.id_sede == id_sede,
            )
        ).first()
        if tiene_servicio_en_sede is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"El empleado con ID {objetivo.id_empleado} no pertenece a la sede {id_sede}.",
            )


@router.patch(
    "/{id_sede}/usuarios/{id_empleado}/estado",
    status_code=status.HTTP_200_OK,
)
def _actualizarEstadoUsuarioSede(
    id_sede: int,
    id_empleado: int,
    data: UsuarioEstadoUpdate,
    user: Annotated[Empleado, Depends(requireAdmin)],
    db: Annotated[Session, Depends(GetDatabase)],
):
    _verificarAccesoSede(user, id_sede)
    tipo_admin = obtenerTipoAdmin(user)

    objetivo = db.get(Empleado, id_empleado)
    if objetivo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El empleado con ID {id_empleado} no existe.",
        )

    _verificarAccesoObjetivo(objetivo, id_sede, db)

    # Si el usuario actual es admin-s, no puede modificar el estado de técnicos ni administradores
    if tipo_admin == "admin-s":
        rol_obj = (objetivo.rol.nombre if objetivo.rol else "").strip().lower()
        if objetivo.tipo != "usuario_sede" or rol_obj in ("administrador de sede", "admin-s", "administrador", "admin-g"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permiso denegado: los Administradores de Sede no pueden modificar el estado de otros administradores o técnicos.",
            )

    if objetivo.id_empleado == user.id_empleado and not data.activo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes desactivar tu propia cuenta de acceso.",
        )

    # Si se intenta reactivar un admin-s, verificar que no supere el límite de 3 activos
    if data.activo and not objetivo.activo and objetivo.tipo == "tecnico":
        rol_admin_s = db.execute(
            select(Rol).where(Rol.nombre == "Administrador de Sede")
        ).scalar_one_or_none()
        if rol_admin_s and objetivo.id_rol == rol_admin_s.id_rol:
            admins_s_count = db.scalar(
                select(func.count(Tecnico.id_empleado))
                .where(
                    Tecnico.id_sede == id_sede,
                    Tecnico.id_rol == rol_admin_s.id_rol,
                    Tecnico.activo == True,
                )
            ) or 0
            if admins_s_count >= 3:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="No se puede reactivar: la sede ya cuenta con 3 Administradores de Sede activos (máximo permitido).",
                )

    objetivo.activo = data.activo

    if not data.activo:
        db.execute(
            delete(RefreshToken).where(RefreshToken.id_empleado == objetivo.id_empleado)
        )

    db.commit()
    db.refresh(objetivo)

    estado_str = "activado" if objetivo.activo else "desactivado"
    return {
        "detalle": f"El usuario {objetivo.usuario} ha sido {estado_str} exitosamente.",
        "id_empleado": objetivo.id_empleado,
        "activo": objetivo.activo,
    }


@router.delete(
    "/{id_sede}/usuarios/{id_empleado}",
    status_code=status.HTTP_200_OK,
)
def _eliminarUsuarioDeSede(
    id_sede: int,
    id_empleado: int,
    user: Annotated[Empleado, Depends(requireAdmin)],
    db: Annotated[Session, Depends(GetDatabase)],
):
    _verificarAccesoSede(user, id_sede)
    tipo_admin = obtenerTipoAdmin(user)

    objetivo = db.get(Empleado, id_empleado)
    if objetivo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El empleado con ID {id_empleado} no existe.",
        )

    _verificarAccesoObjetivo(objetivo, id_sede, db)

    if tipo_admin == "admin-s":
        rol_obj = (objetivo.rol.nombre if objetivo.rol else "").strip().lower()
        if objetivo.tipo != "usuario_sede" or rol_obj in ("administrador de sede", "admin-s", "administrador", "admin-g"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permiso denegado: no puedes gestionar administradores ni técnicos.",
            )

    if objetivo.id_empleado == user.id_empleado:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes eliminar tu propia cuenta.",
        )

    objetivo.activo = False
    db.execute(
        delete(RefreshToken).where(RefreshToken.id_empleado == objetivo.id_empleado)
    )
    db.commit()
    return {"detalle": f"El usuario {objetivo.usuario} ha sido desactivado."}
