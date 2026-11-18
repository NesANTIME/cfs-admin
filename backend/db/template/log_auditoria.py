from datetime import datetime, timezone
from typing import TYPE_CHECKING
from .base import Base
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from .empleado import Empleado


class LogAuditoria(Base):
    __tablename__ = "logs_auditoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    accion: Mapped[str] = mapped_column(String(100), index=True)
    entidad: Mapped[str] = mapped_column(String(50), index=True)  # empleado, servicio, sede, dispositivo, autenticacion
    id_entidad: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detalle: Mapped[str | None] = mapped_column(Text, nullable=True)
    id_actor: Mapped[int | None] = mapped_column(
        ForeignKey("empleados.id_empleado", ondelete="SET NULL"), nullable=True
    )
    actor_usuario: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    ip_origen: Mapped[str | None] = mapped_column(String(45), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        index=True,
    )

    actor: Mapped["Empleado | None"] = relationship(foreign_keys=[id_actor])

    __table_args__ = (
        Index("ix_logs_accion_creado_en", "accion", "creado_en"),
        Index("ix_logs_entidad_creado_en", "entidad", "creado_en"),
    )

    def __repr__(self) -> str:
        return f"<LogAuditoria id={self.id} accion={self.accion} actor={self.actor_usuario}>"
