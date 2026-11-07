from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .empleado import Empleado
    from .sala_videoconf import SalaVideoconf


class InvitacionVideoconf(Base):
    __tablename__ = "invitaciones_videoconf"

    id: Mapped[int] = mapped_column(primary_key=True)

    id_sala: Mapped[int] = mapped_column(
        ForeignKey("salas_videoconf.id", ondelete="CASCADE"), index=True
    )
    id_invitador: Mapped[int] = mapped_column(
        ForeignKey("empleados.id_empleado", ondelete="CASCADE"), index=True
    )
    id_invitado: Mapped[int] = mapped_column(
        ForeignKey("empleados.id_empleado", ondelete="CASCADE"), index=True
    )

    estado: Mapped[str] = mapped_column(
        String(20), default="pendiente", server_default="pendiente"
    )
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    respondida_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    sala: Mapped["SalaVideoconf"] = relationship(back_populates="invitaciones")
    invitador: Mapped["Empleado"] = relationship(foreign_keys=[id_invitador])
    invitado: Mapped["Empleado"] = relationship(foreign_keys=[id_invitado])

    __table_args__ = (
        CheckConstraint("id_invitador <> id_invitado", name="invitacion_no_auto"),
        CheckConstraint(
            "estado IN ('pendiente','aceptada','rechazada','cancelada','expirada','finalizada')",
            name="invitacion_estado_valido",
        ),
        UniqueConstraint(
            "id_sala", "id_invitado", name="uq_invitaciones_sala_invitado"
        ),
        Index("ix_invitaciones_invitado_estado", "id_invitado", "estado"),
        Index("ix_invitaciones_invitador_estado", "id_invitador", "estado"),
        Index(
            "uq_invitaciones_pendientes_par",
            "id_invitador",
            "id_invitado",
            unique=True,
            postgresql_where=text("estado = 'pendiente'"),
        ),
    )
