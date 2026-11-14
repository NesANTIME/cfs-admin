from typing import Annotated
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from core.deps import getCurrentUser
from db.controller import GetDatabase
from fastapi import APIRouter, Depends
from db.template.empleado import Empleado
from datetime import datetime, timedelta, timezone


router = APIRouter(tags=["Presencia"])


@router.post("/heartbeat", status_code=204)
def _heartbeat(
    user: Annotated[Empleado, Depends(getCurrentUser)],
    db: Annotated[Session, Depends(GetDatabase)],
):
    user.en_linea = True
    user.ultima_vez_en_linea = datetime.now(timezone.utc)
    db.commit()


def limpiarPresencia(db: Session) -> None:
    umbral = datetime.now(timezone.utc) - timedelta(seconds=90)
    db.execute(
        update(Empleado)
        .where(
            Empleado.en_linea == True,
            (Empleado.ultima_vez_en_linea == None) | (Empleado.ultima_vez_en_linea < umbral)
        )
        .values(en_linea=False)
    )
    db.commit()
