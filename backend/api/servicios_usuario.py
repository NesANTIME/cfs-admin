from typing import Annotated
from sqlalchemy import select, or_
from db.controller import GetDatabase
from sqlalchemy.orm import Session, selectinload
from config.utils.request import UsuarioSedeResponse
from fastapi import APIRouter, Depends, HTTPException, Path, status
from core.deps import getCurrentUser, requireAdmin, obtenerTipoAdmin
from db.template.empleado import Empleado, Tecnico, TecnicoJefe, UsuarioSede
from db.template.servicio_usuario import ServicioUsuario, TIPOS_SERVICIO_USUARIO


router = APIRouter(prefix="/sedes", tags=["Servicios de Usuario"])

_TIPOS_ADMIN_EXCLUIDOS = ("tecnico_jefe",)


def _verificarAccesoSede(user: Empleado, id_sede: int) -> None:
    tipo_admin = obtenerTipoAdmin(user)
    if tipo_admin == "admin-g":
        return
    id_sede_usuario = getattr(user, "id_sede", None)
    if id_sede_usuario != id_sede:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permiso denegado: no estás autorizado para acceder a esta sede.",
        )


def _verificarSedeObjetivo(objetivo: Empleado, id_sede: int) -> None:
    id_sede_objetivo = getattr(objetivo, "id_sede", None)
    if id_sede_objetivo is not None and id_sede_objetivo != id_sede:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario no pertenece a la sede indicada.",
        )


def _puedeGestionarEmpleado(user: Empleado, objetivo: Empleado) -> bool:
    tipo_admin = obtenerTipoAdmin(user)
    if tipo_admin == "admin-g":
        return True
    if objetivo.tipo in _TIPOS_ADMIN_EXCLUIDOS:
        return False
    if objetivo.tipo == "tecnico":
        return False
    rol_nombre = (objetivo.rol.nombre if objetivo.rol else "").strip().lower()
    if rol_nombre in ("administrador de sede", "admin-s", "administrador", "admin-g"):
        return False
    return True


@router.get("/{id_sede}/usuarios", response_model=list[UsuarioSedeResponse])
def _listarUsuariosSede(
    id_sede: int,
    user: Annotated[Empleado, Depends(requireAdmin)],
    db: Annotated[Session, Depends(GetDatabase)],
):
    _verificarAccesoSede(user, id_sede)

    from db.template.sede import Sede
    sede = db.get(Sede, id_sede)
    if sede is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La sede con ID {id_sede} no existe.",
        )

    from api.heartbeat import limpiarPresencia
    try:
        limpiarPresencia(db)
    except Exception:
        pass

    from sqlalchemy.orm import with_polymorphic

    tipo_admin = obtenerTipoAdmin(user)
    emp_poly = with_polymorphic(Empleado, [Tecnico, UsuarioSede])

    condiciones = [
        emp_poly.tipo.in_(["usuario_sede", "tecnico"]),
        or_(
            emp_poly.Tecnico.id_sede == id_sede,
            emp_poly.UsuarioSede.id_sede == id_sede,
        ),
    ]

    # Admin-S solo ve usuarios activos; Admin-G ve activos e inactivos para gestionarlos
    if tipo_admin == "admin-s":
        condiciones.append(emp_poly.activo == True)

    stmt = (
        select(emp_poly)
        .where(*condiciones)
        .options(selectinload(emp_poly.servicios_usuario), selectinload(emp_poly.rol))
        .order_by(emp_poly.id_empleado.asc())
    )
    empleados = db.scalars(stmt).all()

    resultado = []
    for emp in empleados:
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
    db: Annotated[Session, Depends(GetDatabase)],
):
    _verificarAccesoSede(user, id_sede)
    _validarTipoServicio(tipo_servicio)

    objetivo = db.get(Empleado, id_empleado)
    if objetivo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El empleado con ID {id_empleado} no existe.",
        )

    _verificarSedeObjetivo(objetivo, id_sede)
    if not _puedeGestionarEmpleado(user, objetivo):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permiso denegado: no puedes gestionar los servicios de este usuario.",
        )

    registro = db.scalars(
        select(ServicioUsuario).where(
            ServicioUsuario.id_empleado == id_empleado,
            ServicioUsuario.tipo_servicio == tipo_servicio,
            or_(ServicioUsuario.id_sede == id_sede, ServicioUsuario.id_sede.is_(None)),
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
        registro.id_sede = id_sede

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
    db: Annotated[Session, Depends(GetDatabase)],
):
    _verificarAccesoSede(user, id_sede)
    _validarTipoServicio(tipo_servicio)

    objetivo = db.get(Empleado, id_empleado)
    if objetivo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El empleado con ID {id_empleado} no existe.",
        )

    _verificarSedeObjetivo(objetivo, id_sede)
    if not _puedeGestionarEmpleado(user, objetivo):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permiso denegado: no puedes gestionar los servicios de este usuario.",
        )

    registro = db.scalars(
        select(ServicioUsuario).where(
            ServicioUsuario.id_empleado == id_empleado,
            ServicioUsuario.tipo_servicio == tipo_servicio,
            or_(ServicioUsuario.id_sede == id_sede, ServicioUsuario.id_sede.is_(None)),
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
        registro.id_sede = id_sede

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
