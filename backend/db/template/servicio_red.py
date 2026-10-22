from .base import Base
from typing import TYPE_CHECKING
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import CheckConstraint, Column, ForeignKey, String, Table

if (TYPE_CHECKING):
    from .dispositivo_red import DispositivoRed
    from .empleado import Tecnico, TecnicoJefe, UsuarioSede



dispositivo_servicio = Table("dispositivo_servicio",
    Base.metadata, Column(
        "id_dispositivo",
        ForeignKey("dispositivos_red.id_dispositivo", ondelete = "CASCADE"),
        primary_key = True,
    ),

    Column(
        "id_servicio",
        ForeignKey("servicios_red.id_servicio", ondelete = "CASCADE"),
        primary_key = True,
    ),
)


ESTADOS_SERVICIO = ("activo", "inactivo")


class ServicioRed(Base):
    __tablename__ = "servicios_red"

    id_servicio: Mapped[int] = mapped_column(primary_key = True)
    nombre: Mapped[str] = mapped_column(String(100))
    estado: Mapped[str] = mapped_column(
        String(15), default = "inactivo", server_default = "inactivo"
    )

    id_usuario_sede: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios_sede.id_empleado", ondelete = "SET NULL")
    )
    id_tecnico: Mapped[int | None] = mapped_column(
        ForeignKey("tecnicos.id_empleado", ondelete = "SET NULL")
    )
    id_tecnico_jefe: Mapped[int | None] = mapped_column(
        ForeignKey("tecnico_jefe.id_empleado", ondelete = "SET NULL")
    )


    usuario_sede: Mapped["UsuarioSede | None"] = relationship(
        back_populates = "servicios", foreign_keys = [id_usuario_sede]
    )
    tecnico: Mapped["Tecnico | None"] = relationship(
        back_populates = "servicios", foreign_keys = [id_tecnico]
    )
    tecnico_jefe: Mapped["TecnicoJefe | None"] = relationship(
        back_populates = "servicios_jefe", foreign_keys = [id_tecnico_jefe]
    )
    dispositivos: Mapped[list["DispositivoRed"]] = relationship(
        secondary = dispositivo_servicio, back_populates = "servicios"
    )

    __table_args__ = (
        CheckConstraint("char_length(trim(nombre)) > 0", name = "nombre_no_vacio"),
        CheckConstraint(
            "estado IN ('" + "','".join(ESTADOS_SERVICIO) + "')", name = "estado_valido"
        ),
    )

    def __repr__(self) -> str:
        return f"<ServicioRed {self.nombre} ({self.estado})>"
