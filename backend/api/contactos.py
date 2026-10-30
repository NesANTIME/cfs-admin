from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from db.controller import getDb
from core.deps import getCurrentUser, obtenerTipoAdmin
from db.template.empleado import Empleado
from db.template.contacto import Contacto
from db.template.sede import Sede
from db.template.servicio_usuario import ServicioUsuario
from config.request import ContactoAgregarRequest, ContactoResponse

router = APIRouter(prefix="/contactos", tags=["Contactos"])


def _obtenerSedeUsuario(emp: Empleado, db: Session) -> int | None:
    """Determina la sede de un empleado."""
    id_s = getattr(emp, "id_sede", None)
    if id_s is not None:
        return id_s
    # Buscar en ServicioUsuario
    serv = db.scalars(select(ServicioUsuario).where(ServicioUsuario.id_empleado == emp.id_empleado)).first()
    return serv.id_sede if serv else None


@router.get("", response_model=list[ContactoResponse])
def _listarContactos(
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    """Retorna la lista de contactos del usuario actual."""
    from api.heartbeat import limpiarPresencia
    try:
        limpiarPresencia(db)
    except Exception:
        pass

    rels = db.scalars(
        select(Contacto).where(Contacto.id_usuario == user.id_empleado).order_by(Contacto.id.desc())
    ).all()

    resultado = []
    for rel in rels:
        target = db.get(Empleado, rel.id_contacto)
        if target is None:
            continue

        id_sede_target = _obtenerSedeUsuario(target, db)
        sede_obj = db.get(Sede, id_sede_target) if id_sede_target else None

        # Servicios habilitados del contacto
        servicios_hab = [
            s.tipo_servicio
            for s in target.servicios_usuario
            if s.habilitado and (id_sede_target is None or s.id_sede == id_sede_target)
        ]

        if rel.registrado_formalmente:
            # Contacto registrado formalmente: se revela nombre, sede y estado online real
            resultado.append({
                "id_contacto_rel": rel.id,
                "id_empleado": target.id_empleado,
                "nombre": target.nombre,
                "usuario": target.usuario,
                "uid_publico": target.uid_publico,
                "id_sede": id_sede_target,
                "sede_nombre": sede_obj.nombre if sede_obj else "Sede principal",
                "en_linea": bool(target.en_linea),
                "registrado_formalmente": True,
                "alias": rel.alias,
                "servicios": servicios_hab,
            })
        else:
            # Contacto sin registrar formalmente: nombre genérico con UID, sin sede ni online visibles
            resultado.append({
                "id_contacto_rel": rel.id,
                "id_empleado": target.id_empleado,
                "nombre": rel.alias or f"Usuario [{target.uid_publico[:8]}…]",
                "usuario": None,
                "uid_publico": target.uid_publico,
                "id_sede": None,
                "sede_nombre": "Pendiente de registro",
                "en_linea": False,
                "registrado_formalmente": False,
                "alias": rel.alias,
                "servicios": servicios_hab,
            })

    return resultado


@router.post("", response_model=ContactoResponse, status_code=status.HTTP_201_CREATED)
def _agregarContacto(
    data: ContactoAgregarRequest,
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    """Agrega un contacto usando su UID único.
    
    Regla: Solo se pueden agregar contactos de la MISMA sede (los usuarios admin-g pueden gestionar todas).
    Inicialmente se agrega sin registro formal hasta que el receptor lo confirme formalmente.
    """
    uid_buscado = data.uid_publico.strip()

    if uid_buscado == user.uid_publico:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes agregarte a ti mismo como contacto.",
        )

    target = db.scalars(select(Empleado).where(Empleado.uid_publico == uid_buscado)).first()
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró ningún usuario con el UID especificado.",
        )

    # Validar que estén en la misma sede (regla intra-sede)
    tipo_admin = obtenerTipoAdmin(user)
    if tipo_admin != "admin-g":
        sede_user = _obtenerSedeUsuario(user, db)
        sede_target = _obtenerSedeUsuario(target, db)
        if sede_user is None or sede_target is None or sede_user != sede_target:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo puedes contactar a usuarios que pertenezcan a tu misma sede.",
            )

    # Verificar si ya existe el vínculo en mis contactos
    rel = db.scalars(
        select(Contacto).where(
            Contacto.id_usuario == user.id_empleado,
            Contacto.id_contacto == target.id_empleado,
        )
    ).first()

    if rel is None:
        rel = Contacto(
            id_usuario=user.id_empleado,
            id_contacto=target.id_empleado,
            alias=data.alias.strip() if data.alias else None,
            registrado_formalmente=False,
        )
        db.add(rel)

    # Asegurar también que exista el vínculo inverso para que el receptor pueda verlo y registrarlo
    rev = db.scalars(
        select(Contacto).where(
            Contacto.id_usuario == target.id_empleado,
            Contacto.id_contacto == user.id_empleado,
        )
    ).first()
    if rev is None:
        db.add(Contacto(
            id_usuario=target.id_empleado,
            id_contacto=user.id_empleado,
            alias=None,
            registrado_formalmente=False,
        ))

    db.commit()
    db.refresh(rel)

    id_sede_target = _obtenerSedeUsuario(target, db)
    sede_obj = db.get(Sede, id_sede_target) if id_sede_target else None

    return {
        "id_contacto_rel": rel.id,
        "id_empleado": target.id_empleado,
        "nombre": rel.alias or f"Usuario [{target.uid_publico[:8]}…]",
        "usuario": None,
        "uid_publico": target.uid_publico,
        "id_sede": None,
        "sede_nombre": "Pendiente de registro",
        "en_linea": False,
        "registrado_formalmente": rel.registrado_formalmente,
        "alias": rel.alias,
        "servicios": [],
    }


@router.post("/{id_contacto_rel}/registrar", status_code=status.HTTP_200_OK)
def _registrarContactoFormalmente(
    id_contacto_rel: int,
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    """El receptor registra formalmente al contacto.
    
    A partir de este momento, se revela la información completa (nombre, sede y conexión)
    y se habilita formalmente la videoconferencia.
    """
    rel = db.get(Contacto, id_contacto_rel)
    if rel is None or rel.id_usuario != user.id_empleado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Relación de contacto no encontrada.",
        )

    rel.registrado_formalmente = True

    # Marcar también como formal la relación inversa si existe
    rev = db.scalars(
        select(Contacto).where(
            Contacto.id_usuario == rel.id_contacto,
            Contacto.id_contacto == user.id_empleado,
        )
    ).first()
    if rev:
        rev.registrado_formalmente = True

    db.commit()

    target = db.get(Empleado, rel.id_contacto)
    id_sede_target = _obtenerSedeUsuario(target, db) if target else None
    sede_obj = db.get(Sede, id_sede_target) if id_sede_target else None

    return {
        "detalle": "Contacto registrado formalmente con éxito.",
        "id_contacto_rel": rel.id,
        "nombre": target.nombre if target else "",
        "sede": sede_obj.nombre if sede_obj else "",
        "registrado_formalmente": True,
    }


@router.delete("/{id_contacto_rel}", status_code=status.HTTP_200_OK)
def _eliminarContacto(
    id_contacto_rel: int,
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    """Elimina un contacto de la lista del usuario."""
    rel = db.get(Contacto, id_contacto_rel)
    if rel is None or rel.id_usuario != user.id_empleado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contacto no encontrado.",
        )

    db.delete(rel)
    db.commit()
    return {"detalle": "Contacto eliminado correctamente."}
