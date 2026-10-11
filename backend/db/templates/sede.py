from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from db.connect import Base


class sede(Base):
    __tablename__ = "sede"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )

    nombre: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False
    )

    ubicacion: Mapped[str] = mapped_column(
        String(150),
        unique=True,
        nullable=False
    )