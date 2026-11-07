import re
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select, or_, func
from sqlalchemy.orm import Session
from db.controller import getDb
from core.deps import getCurrentUser, obtenerTipoAdmin
from db.template.empleado import Empleado, Tecnico, UsuarioSede
from db.template.contacto import Contacto
from db.template.sede import Sede
from db.template.servicio_usuario import ServicioUsuario
from config.request import ContactoAgregarRequest, ContactoResponse, ContactoBuscarResponse

router = APIRouter(prefix="/contactos", tags=["Contactos"])


def _obtenerSedeUsuario(emp: Empleado, db: Session) -> int | None:
    """Determina la sede de un empleado."""
    id_s = getattr(emp, "id_sede", None)
    if id_s is not None:
        return id_s
    # Buscar en ServicioUsuario
    serv = db.scalars(select(ServicioUsuario).where(ServicioUsuario.id_empleado == emp.id_empleado)).first()
    return serv.id_sede if serv else None


def _obtenerIdsEmpleadosDeSede(id_sede: int, db: Session) -> set[int]:
    """Retorna los IDs de los empleados cuya sede principal es la indicada.

    No se usan los registros de servicios para inferir la sede: un usuario
    pertenece a una única sede y esa asignación es la que rige el aislamiento.
    """
    ids: set[int] = set()
    ids.update(db.scalars(select(Tecnico.id_empleado).where(Tecnico.id_sede == id_sede)).all())
    ids.update(db.scalars(select(UsuarioSede.id_empleado).where(UsuarioSede.id_sede == id_sede)).all())
    return ids


@router.get("/buscar", response_model=list[ContactoBuscarResponse])
def _buscarUsuarios(
    q: Annotated[str, Query(min_length=2, max_length=50, description="Username o UID")],
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    """Busca usuarios disponibles para agregar respetando el aislamiento estricto de sede.

    - Si el término es un UID (36 caracteres formato UUID), busca exactamente por UID.
    - Si es un username o término parcial, busca coincidencias parciales por username.
    - No muestra resultados parciales si se ingresa un UID incompleto.
    - Únicamente muestra usuarios pertenecientes a la MISMA sede que el usuario que consulta (excepto admin-g).
    - Excluye al propio usuario que realiza la búsqueda y usuarios inactivos.
    """
    termino = q.strip()
    if not termino:
        return []

    tipo_admin = obtenerTipoAdmin(user)
    id_sede_user = _obtenerSedeUsuario(user, db)

    # Si no es admin-g y no tiene sede asignada, no puede contactar a nadie
    if tipo_admin != "admin-g" and id_sede_user is None:
        return []

    # Detectar si el usuario ingresó un UUID completo
    patron_uuid = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
    es_uuid = bool(patron_uuid.match(termino))

    # Si parece un UID parcial (prefijo hexadecimal con guion, ej. "77fcf360-1f99"),
    # no devolver nada: los UID solo se resuelven cuando están completos.
    parece_uid_parcial = (
        not es_uuid
        and re.match(r"^[0-9a-fA-F]{8}-[0-9a-fA-F-]*$", termino) is not None
    )
    if parece_uid_parcial:
        return []

    query = select(Empleado).where(
        Empleado.id_empleado != user.id_empleado,
        Empleado.activo == True,  # noqa: E712
    )

    if es_uuid:
        query = query.where(Empleado.uid_publico == termino)
    else:
        # Búsqueda por coincidencia en username
        query = query.where(
            or_(
                func.lower(Empleado.usuario).like(f"%{termino.lower()}%"),
                func.lower(Empleado.nombre).like(f"%{termino.lower()}%"),
            )
        )

    # Filtrar estrictamente intra-sede para usuarios no admin-g
    if tipo_admin != "admin-g" and id_sede_user is not None:
        ids_sede = _obtenerIdsEmpleadosDeSede(id_sede_user, db)
        if not ids_sede:
            return []
        query = query.where(Empleado.id_empleado.in_(ids_sede))

    empleados = db.scalars(query.limit(8)).all()

    # Obtener estado de contactos actuales del usuario
    mis_contactos = {
        c.id_contacto: c
        for c in db.scalars(select(Contacto).where(Contacto.id_usuario == user.id_empleado)).all()
    }

    resultado = []
    for emp in empleados:
        rel = mis_contactos.get(emp.id_empleado)
        ya_es_contacto = rel is not None and bool(rel.registrado_formalmente)
        solicitud_pendiente = rel is not None and not bool(rel.registrado_formalmente)

        resultado.append({
            "id_empleado": emp.id_empleado,
            "nombre": emp.nombre,
            "usuario": emp.usuario,
            "uid_publico": emp.uid_publico,
            "ya_es_contacto": ya_es_contacto,
            "solicitud_pendiente": solicitud_pendiente,
        })

    return resultado


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

    tipo_admin = obtenerTipoAdmin(user)
    id_sede_user = _obtenerSedeUsuario(user, db)

    rels = db.scalars(
        select(Contacto).where(Contacto.id_usuario == user.id_empleado).order_by(Contacto.id.desc())
    ).all()

    resultado = []
    for rel in rels:
        target = db.get(Empleado, rel.id_contacto)
        if target is None or not target.activo:
            continue

        id_sede_target = _obtenerSedeUsuario(target, db)

        # Aislamiento estricto: si el contacto cambió de sede o el usuario no
        # tiene sede, no debe seguir apareciendo en la lista.
        if tipo_admin != "admin-g" and (
            id_sede_user is None or id_sede_target != id_sede_user
        ):
            continue

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
            # Contacto sin registrar formalmente: nombre referencial con username/UID
            resultado.append({
                "id_contacto_rel": rel.id,
                "id_empleado": target.id_empleado,
                "nombre": rel.alias or f"@{target.usuario} [{target.uid_publico[:8]}…]",
                "usuario": target.usuario,
                "uid_publico": target.uid_publico,
                "id_sede": None,
                "sede_nombre": "Pendiente de formalizar",
                "en_linea": False,
                "registrado_formalmente": False,
                "alias": rel.alias,
                "servicios": [],
            })

    return resultado


@router.post("", response_model=ContactoResponse, status_code=status.HTTP_201_CREATED)
def _agregarContacto(
    data: ContactoAgregarRequest,
    response: Response,
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    """Agrega un contacto usando su Username o UID único.
    
    Regla: Solo se pueden agregar contactos de la MISMA sede (los usuarios admin-g pueden gestionar todas).
    Inicialmente se agrega sin registro formal hasta que el receptor lo confirme formalmente.
    """
    identificador = data.identificador.strip()
    if not identificador:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Por favor ingresa un nombre de usuario o un UID válido.",
        )

    patron_uuid = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
    if patron_uuid.match(identificador):
        target = db.scalars(
            select(Empleado).where(
                Empleado.uid_publico == identificador,
                Empleado.activo == True,  # noqa: E712
            )
        ).first()
        if target is None:
            target = db.scalars(
                select(Empleado).where(
                    func.lower(Empleado.usuario) == identificador.lower(),
                    Empleado.activo == True,  # noqa: E712
                )
            ).first()
    else:
        target = db.scalars(
            select(Empleado).where(
                func.lower(Empleado.usuario) == identificador.lower(),
                Empleado.activo == True,  # noqa: E712
            )
        ).first()
        if target is None:
            target = db.scalars(
                select(Empleado).where(
                    Empleado.uid_publico == identificador,
                    Empleado.activo == True,  # noqa: E712
                )
            ).first()

    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró ningún usuario activo con el identificador '{identificador}'.",
        )

    if target.id_empleado == user.id_empleado:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes agregarte a ti mismo como contacto.",
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
        response.status_code = status.HTTP_201_CREATED
    else:
        response.status_code = status.HTTP_200_OK
        if data.alias:
            rel.alias = data.alias.strip()

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

    # Servicios habilitados del contacto
    servicios_hab = [
        s.tipo_servicio
        for s in target.servicios_usuario
        if s.habilitado and (id_sede_target is None or s.id_sede == id_sede_target)
    ]

    return {
        "id_contacto_rel": rel.id,
        "id_empleado": target.id_empleado,
        "nombre": target.nombre if rel.registrado_formalmente else (rel.alias or f"@{target.usuario} [{target.uid_publico[:8]}…]"),
        "usuario": target.usuario,
        "uid_publico": target.uid_publico,
        "id_sede": id_sede_target if rel.registrado_formalmente else None,
        "sede_nombre": (sede_obj.nombre if sede_obj else "Sede") if rel.registrado_formalmente else "Pendiente de formalizar",
        "en_linea": bool(target.en_linea) if rel.registrado_formalmente else False,
        "registrado_formalmente": rel.registrado_formalmente,
        "alias": rel.alias,
        "servicios": servicios_hab if rel.registrado_formalmente else [],
    }


@router.post("/{id_contacto_rel}/aceptar", status_code=status.HTTP_200_OK)
@router.post("/{id_contacto_rel}/registrar", status_code=status.HTTP_200_OK)
def _aceptarContactoFormalmente(
    id_contacto_rel: int,
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    """Acepta y registra formalmente al contacto.
    
    A partir de este momento, se revela la información completa (nombre, sede y conexión)
    en ambas direcciones y se habilitan formalmente todas las funciones como videoconferencia.
    """
    rel = db.get(Contacto, id_contacto_rel)
    if rel is None or rel.id_usuario != user.id_empleado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Relación de contacto no encontrada.",
        )

    rel.registrado_formalmente = True

    # Actualizar también la relación recíproca para que ambos queden formalizados
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
        "detalle": "Contacto aceptado y registrado formalmente con éxito.",
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
    """Elimina o rechaza un contacto de la lista del usuario."""
    rel = db.get(Contacto, id_contacto_rel)
    if rel is None or rel.id_usuario != user.id_empleado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contacto no encontrado.",
        )

    # Eliminar también la relación recíproca para que el rechazo/eliminación
    # desaparezca de la lista de ambos usuarios.
    rev = db.scalars(
        select(Contacto).where(
            Contacto.id_usuario == rel.id_contacto,
            Contacto.id_contacto == rel.id_usuario,
        )
    ).first()
    if rev is not None:
        db.delete(rev)

    db.delete(rel)
    db.commit()
    return {"detalle": "Contacto eliminado correctamente."}
