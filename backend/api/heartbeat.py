from datetime import datetime, timedelta, timezone
from typing import Annotated
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select
from db.controller import getDb
from core.deps import getCurrentUser
from db.template.empleado import Empleado

router = APIRouter(tags=["Presencia"])


@router.post("/heartbeat", status_code=204)
def _heartbeat(
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(getDb)],
):
    """Marca al usuario como en línea. El cliente debe llamar cada 30 segundos."""
    user.en_linea = True
    user.ultima_vez_en_linea = datetime.now(timezone.utc)
    db.commit()


def limpiarPresencia(db: Session) -> None:
    """Marca como fuera de línea a todo empleado sin heartbeat en los últimos 90 segundos."""
    umbral = datetime.now(timezone.utc) - timedelta(seconds=90)
    empleados = db.execute(
        select(Empleado).where(
            Empleado.en_linea == True  # noqa: E712
        )
    ).scalars().all()

    for emp in empleados:
        if emp.ultima_vez_en_linea is None or emp.ultima_vez_en_linea < umbral:
            emp.en_linea = False

    db.commit()
