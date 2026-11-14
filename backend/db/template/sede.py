from .base import Base
from typing import TYPE_CHECKING
from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

if (TYPE_CHECKING):
    from .dispositivo_red import DispositivoRed
    from .empleado import Tecnico, TecnicoJefe
    from .servicio_usuario import ServicioUsuario



class Sede(Base):
    __tablename__ = "sedes"

    id_sede: Mapped[int] = mapped_column(primary_key = True)
    nombre: Mapped[str] = mapped_column(String(100), unique = True)
    ubicacion: Mapped[str] = mapped_column(String(255))
    descripcion: Mapped[str | None] = mapped_column(Text, nullable = True)
    id_tecnico_jefe: Mapped[int | None] = mapped_column(
        ForeignKey(
            "tecnico_jefe.id_empleado",
            ondelete = "SET NULL",
            use_alter = True,
            name = "fk_sedes_id_tecnico_jefe_tecnico_jefe",
        )
    )

    jefe: Mapped["TecnicoJefe | None"] = relationship(back_populates = "sedes_a_cargo", foreign_keys = [id_tecnico_jefe])
    tecnicos: Mapped[list["Tecnico"]] = relationship(back_populates = "sede", foreign_keys = "Tecnico.id_sede")
    dispositivos: Mapped[list["DispositivoRed"]] = relationship(back_populates = "sede", cascade = "all, delete-orphan")
    servicios_usuario: Mapped[list["ServicioUsuario"]] = relationship(back_populates = "sede")

    __table_args__ = (CheckConstraint("char_length(trim(nombre)) > 0", name = "nombre_no_vacio"),)


    def __repr__(self) -> str:
        return f"<Sede {self.nombre}>"
