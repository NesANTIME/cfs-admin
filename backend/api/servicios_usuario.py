from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import select, or_
from sqlalchemy.orm import Session, selectinload
from db.controller import getDb
from core.deps import getCurrentUser, requireAdmin, obtenerTipoAdmin
from db.template.empleado import Empleado, Tecnico, TecnicoJefe, UsuarioSede
from db.template.servicio_usuario import ServicioUsuario, TIPOS_SERVICIO_USUARIO
from config.request import UsuarioSedeResponse

router = APIRouter(prefix="/sedes", tags=["Servicios de Usuario"])

# Tipos de empleado que se consideran administradores (no deben aparecer como
# usuarios gestionables desde la vista de usuarios de una sede)
_TIPOS_ADMIN_EXCLUIDOS = ("tecnico_jefe",)


def _verificarAccesoSede(user: Empleado, id_sede: int) -> None:
    """Lanza 403 si el admin-s intenta acceder a una sede que no es la suya."""
    tipo_admin = obtenerTipoAdmin(user)
    if tipo_admin == "admin-g":
        return
    id_sede_usuario = getattr(user, "id_sede", None)
    if id_sede_usuario != id_sede:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permiso denegado: no estás autorizado para acceder a esta sede.",
        )


def _puedeGestionarEmpleado(user: Empleado, objetivo: Empleado) -> bool:
    """
    Determina si el usuario actual puede gestionar los servicios del objetivo.
    - admin-g: puede gestionar a cualquiera.
    - admin-s: solo puede gestionar a usuarios_sede y tecnicos que no sean tecnico_jefe.
    """
    tipo_admin = obtenerTipoAdmin(user)
    if tipo_admin == "admin-g":
        return True
    # admin-s no puede gestionar admin-g ni otros admin-s (tecnico_jefe o tecnico con sede)
    if objetivo.tipo in _TIPOS_ADMIN_EXCLUIDOS:
        return False
    # Si el objetivo es un Tecnico (pero no TecnicoJefe), tampoco puede gestionarlo
    if objetivo.tipo == "tecnico":
        return False
    return True


@router.get("/{id_sede}/usuarios", response_model=list[UsuarioSedeResponse])
def _listarUsuariosSede(
    id_sede: int,
    user: Annotated[Empleado, Depends(requireAdmin)],
    db: Annotated[Session, Depends(getDb)],
):
    """Lista los usuarios de la sede (UsuarioSede) junto con sus servicios habilitados.

    - admin-g: puede listar usuarios de cualquier sede.
    - admin-s: solo puede listar usuarios de su propia sede.
    """
    _verificarAccesoSede(user, id_sede)

    # Verificar que la sede existe
    from db.template.sede import Sede
    sede = db.get(Sede, id_sede)
    if sede is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La sede con ID {id_sede} no existe.",
        )

    # Limpiar presencia vencida antes de listar
    from api.heartbeat import limpiarPresencia
    try:
        limpiarPresencia(db)
    except Exception:
        pass

    # Obtener usuarios vinculados a esta sede
    # 1. Usuarios con id_sede == id_sede
    # 2. Usuarios con al menos un registro en servicios_usuario con id_sede == id_sede
    # Excluyendo administradores generales (tecnico_jefe)
    stmt = (
        select(Empleado)
        .where(
            Empleado.tipo.in_(["usuario_sede", "tecnico"]),
            Empleado.activo == True,  # noqa: E712
        )
        .options(selectinload(Empleado.servicios_usuario), selectinload(Empleado.rol))
    )
    empleados = db.scalars(stmt).all()

    resultado = []
    for emp in empleados:
        emp_sede = getattr(emp, "id_sede", None)
        servicios_sede = [s for s in emp.servicios_usuario if s.id_sede == id_sede]

        # Incluir si está asignado a la sede o tiene servicios en ella
        if emp_sede == id_sede or servicios_sede or emp.tipo == "usuario_sede":
            resultado.append({
                "id_empleado": emp.id_empleado,
                "nombre": emp.nombre,
                "usuario": emp.usuario,
                "tipo": emp.tipo,
                "activo": emp.activo,
                "en_linea": bool(emp.en_linea),
                "uid_publico": getattr(emp, "uid_publico", None),
                "rol": emp.rol.nombre if emp.rol else emp.tipo,
                "servicios": [
                    {"tipo_servicio": s.tipo_servicio, "habilitado": s.habilitado}
                    for s in emp.servicios_usuario
                    if s.id_sede == id_sede
                ],
            })

    return resultado



@router.post(
    "/{id_sede}/usuarios/{id_empleado}/servicios/{tipo_servicio}/habilitar",
    status_code=status.HTTP_200_OK,
)
def _habilitarServicio(
    id_sede: int,
    id_empleado: int,
    tipo_servicio: str,
    user: Annotated[Empleado, Depends(requireAdmin)],
    db: Annotated[Session, Depends(getDb)],
):
    """Habilita un servicio de aplicación para un usuario en una sede.

    - admin-g: puede habilitar en cualquier sede.
    - admin-s: solo puede habilitar en su sede y solo a usuarios_sede.
    - tipo_servicio debe ser 'videoconferencia' o 'chat'.
    """
    _verificarAccesoSede(user, id_sede)
    _validarTipoServicio(tipo_servicio)

    objetivo = db.get(Empleado, id_empleado)
    if objetivo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El empleado con ID {id_empleado} no existe.",
        )

    if not _puedeGestionarEmpleado(user, objetivo):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permiso denegado: no puedes gestionar los servicios de este usuario.",
        )

    registro = db.scalars(
        select(ServicioUsuario).where(
            ServicioUsuario.id_empleado == id_empleado,
            ServicioUsuario.tipo_servicio == tipo_servicio,
            ServicioUsuario.id_sede == id_sede,
        )
    ).first()

    if registro is None:
        registro = ServicioUsuario(
            id_empleado=id_empleado,
            tipo_servicio=tipo_servicio,
            habilitado=True,
            id_sede=id_sede,
        )
        db.add(registro)
    else:
        registro.habilitado = True

    db.commit()
    return {"detalle": f"Servicio '{tipo_servicio}' habilitado para el empleado {id_empleado}."}


@router.post(
    "/{id_sede}/usuarios/{id_empleado}/servicios/{tipo_servicio}/deshabilitar",
    status_code=status.HTTP_200_OK,
)
def _deshabilitarServicio(
    id_sede: int,
    id_empleado: int,
    tipo_servicio: str,
    user: Annotated[Empleado, Depends(requireAdmin)],
    db: Annotated[Session, Depends(getDb)],
):
    """Deshabilita un servicio de aplicación para un usuario en una sede.

    - admin-g: puede deshabilitar en cualquier sede.
    - admin-s: solo puede deshabilitar en su sede y solo a usuarios_sede.
    - tipo_servicio debe ser 'videoconferencia' o 'chat'.
    """
    _verificarAccesoSede(user, id_sede)
    _validarTipoServicio(tipo_servicio)

    objetivo = db.get(Empleado, id_empleado)
    if objetivo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El empleado con ID {id_empleado} no existe.",
        )

    if not _puedeGestionarEmpleado(user, objetivo):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permiso denegado: no puedes gestionar los servicios de este usuario.",
        )

    registro = db.scalars(
        select(ServicioUsuario).where(
            ServicioUsuario.id_empleado == id_empleado,
            ServicioUsuario.tipo_servicio == tipo_servicio,
            ServicioUsuario.id_sede == id_sede,
        )
    ).first()

    if registro is None:
        registro = ServicioUsuario(
            id_empleado=id_empleado,
            tipo_servicio=tipo_servicio,
            habilitado=False,
            id_sede=id_sede,
        )
        db.add(registro)
    else:
        registro.habilitado = False

    db.commit()
    return {"detalle": f"Servicio '{tipo_servicio}' deshabilitado para el empleado {id_empleado}."}


def _validarTipoServicio(tipo_servicio: str) -> None:
    """Lanza 422 si el tipo_servicio no es válido."""
    if tipo_servicio not in TIPOS_SERVICIO_USUARIO:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Tipo de servicio inválido: '{tipo_servicio}'. "
                   f"Los valores válidos son: {', '.join(TIPOS_SERVICIO_USUARIO)}.",
        )
