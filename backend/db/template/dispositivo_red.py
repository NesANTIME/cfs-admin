from .base import Base
from typing import TYPE_CHECKING
from .servicio_red import dispositivo_servicio
from sqlalchemy.dialects.postgresql import INET, MACADDR
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint

if (TYPE_CHECKING):
    from .sede import Sede
    from .servicio_red import ServicioRed


estadosDispositivo = ("en_linea", "fuera_de_linea", "desconocido")


class DispositivoRed(Base):
    __tablename__ = "dispositivos_red"

    id_dispositivo: Mapped[int] = mapped_column(primary_key = True)
    nombre: Mapped[str] = mapped_column(String(100))
    direccion_ip: Mapped[str] = mapped_column(INET)
    mac: Mapped[str] = mapped_column(MACADDR, unique = True)
    tipo: Mapped[str] = mapped_column(String(50))
    estado: Mapped[str] = mapped_column(String(20), default = "desconocido", server_default = "desconocido")


    id_sede: Mapped[int] = mapped_column(ForeignKey("sedes.id_sede", ondelete = "CASCADE"))
    sede: Mapped["Sede"] = relationship(back_populates = "dispositivos")


    servicios: Mapped[list["ServicioRed"]] = relationship(
        secondary = dispositivo_servicio, back_populates = "dispositivos"
    )


    __table_args__ = (
        UniqueConstraint("id_sede", "direccion_ip", name = "ip_unica_por_sede"),
        CheckConstraint("char_length(trim(nombre)) > 0", name = "nombre_no_vacio"),
        CheckConstraint(
            "estado IN ('" + "','".join(estadosDispositivo) + "')",
            name = "estado_valido",
        ),
    )


    def __repr__(self) -> str:
        return f"<DispositivoRed {self.nombre} {self.direccion_ip}>"
