from .base import Base
from typing import TYPE_CHECKING
from sqlalchemy import CheckConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

if (TYPE_CHECKING):
    from .empleado import Empleado



class Rol(Base):
    __tablename__ = "roles"

    id_rol: Mapped[int] = mapped_column(primary_key = True)
    nombre: Mapped[str] = mapped_column(String(50), unique = True)
    descripcion: Mapped[str | None] = mapped_column(Text)
    empleados: Mapped[list["Empleado"]] = relationship(back_populates = "rol")

    __table_args__ = (
        CheckConstraint("char_length(trim(nombre)) > 0", name = "nombre_no_vacio"),
    )

    def __repr__(self) -> str:
        return f"<Rol {self.nombre}>"
