from .base import Base
from typing import TYPE_CHECKING
from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from .empleado import Empleado
    from .sede import Sede


TIPOS_SERVICIO_USUARIO = ("videoconferencia", "chat")


class ServicioUsuario(Base):
    __tablename__ = "servicios_usuario"

    id: Mapped[int] = mapped_column(primary_key=True)

    id_empleado: Mapped[int] = mapped_column(
        ForeignKey("empleados.id_empleado", ondelete="CASCADE")
    )
    tipo_servicio: Mapped[str] = mapped_column(String(50))
    habilitado: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    id_sede: Mapped[int | None] = mapped_column(
        ForeignKey("sedes.id_sede", ondelete="SET NULL"), nullable=True
    )

    # Relaciones
    empleado: Mapped["Empleado"] = relationship(back_populates="servicios_usuario")
    sede: Mapped["Sede | None"] = relationship(back_populates="servicios_usuario")

    __table_args__ = (
        CheckConstraint(
            "tipo_servicio IN ('videoconferencia', 'chat')",
            name="ck_servicios_usuario_tipo_servicio_valido",
        ),
        UniqueConstraint(
            "id_empleado",
            "tipo_servicio",
            name="uq_servicios_usuario_id_empleado_tipo_servicio",
        ),
    )

    def __repr__(self) -> str:
        return f"<ServicioUsuario empleado={self.id_empleado} tipo={self.tipo_servicio} habilitado={self.habilitado}>"
