from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from db.connect import Base


class dispositivo(Base):
    __tablename__ = "dispositivo"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )

    nombre: Mapped[str] = mapped_column(
        String(150),
        unique=True,
        nullable=False
    )

    direccionIP: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False
    )

    mac: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False
    )
  
    tipo: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    estado: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )