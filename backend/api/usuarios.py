import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from db.controller import getDb
from core.deps import getCurrentUser, requireAdmin, obtenerTipoAdmin
from db.template.empleado import Empleado, Tecnico, UsuarioSede
from db.template.rol import Rol
from db.template.sede import Sede
from db.template.servicio_usuario import ServicioUsuario
from config.request import UsuarioCreate, UsuarioResponse
from core.security import hashearPassword
from config.config import getLongHashPassword

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
    db: Annotated[Session, Depends(getDb)],
):
    """Crea un usuario (cliente/empleado) o un admin-s para una sede.

    - admin-g: puede crear usuarios_sede o tecnicos (admin-s) en cualquier sede.
    - admin-s: solo puede crear usuarios_sede en su propia sede.
    """
    _verificarAccesoSede(user, id_sede)
    tipo_admin = obtenerTipoAdmin(user)

    # Verificar que la sede exista
    sede = db.get(Sede, id_sede)
    if sede is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La sede con ID {id_sede} no existe.",
        )

    # Restricciones para admin-s: solo puede crear usuario_sede
    if tipo_admin == "admin-s":
        if data.es_admin_s or data.tipo != "usuario_sede":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permiso denegado: un Administrador de Sede solo puede registrar usuarios normales (clientes/empleados).",
            )

    # Validaciones de campos
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

    # Validar unicidad del nombre de usuario
    existente = db.execute(select(Empleado).where(Empleado.usuario == usuario)).scalar_one_or_none()
    if existente is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El nombre de usuario '{usuario}' ya está en uso. Por favor elija otro.",
        )

    uid_publico = str(uuid.uuid4())
    contrasena_hash = hashearPassword(contrasena)

    if data.es_admin_s:
        # Es un administrador de sede (Tecnico asignado a la sede)
        rol_admin_s = db.execute(
            select(Rol).where(Rol.nombre == "Administrador de Sede")
        ).scalar_one_or_none()
        if rol_admin_s is None:
            rol_admin_s = Rol(nombre="Administrador de Sede", descripcion="Control exclusivo de una sede asignada")
            db.add(rol_admin_s)
            db.flush()

        # Validar que la sede no tenga ya un admin-s asignado
        existing_admin_s = db.execute(
            select(Tecnico)
            .where(Tecnico.id_sede == id_sede)
            .where(Tecnico.id_rol == rol_admin_s.id_rol)
        ).scalar_one_or_none()
        if existing_admin_s is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya existe un Administrador de Sede asignado a esta sede. Cada sede solo puede tener un admin-s activo.",
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
        # Es un usuario común de sede (UsuarioSede)
        rol_usuario = db.execute(
            select(Rol).where(Rol.nombre.in_(["Usuario Sede", "Empleado", "Cliente"]))
        ).scalar_one_or_none()
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

    # Inicializar servicios de aplicación por defecto (videoconferencia y chat deshabilitados inicialmente)
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


@router.delete(
    "/{id_sede}/usuarios/{id_empleado}",
    status_code=status.HTTP_200_OK,
)
def _eliminarUsuarioDeSede(
    id_sede: int,
    id_empleado: int,
    user: Annotated[Empleado, Depends(requireAdmin)],
    db: Annotated[Session, Depends(getDb)],
):
    """Desactiva o elimina un usuario de una sede."""
    _verificarAccesoSede(user, id_sede)
    tipo_admin = obtenerTipoAdmin(user)

    objetivo = db.get(Empleado, id_empleado)
    if objetivo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El empleado con ID {id_empleado} no existe.",
        )

    # Restricciones
    if tipo_admin == "admin-s":
        if objetivo.tipo != "usuario_sede":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permiso denegado: no puedes gestionar administradores ni técnicos.",
            )

    # No se puede eliminar a uno mismo
    if objetivo.id_empleado == user.id_empleado:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes eliminar tu propia cuenta.",
        )

    objetivo.activo = False
    db.commit()
    return {"detalle": f"El usuario {objetivo.usuario} ha sido desactivado."}
