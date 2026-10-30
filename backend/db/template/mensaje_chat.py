from datetime import datetime, timezone
from .base import Base
from typing import TYPE_CHECKING
from sqlalchemy import Boolean, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from .empleado import Empleado
    from .sede import Sede


class MensajeChat(Base):
    __tablename__ = "mensajes_chat"

    id: Mapped[int] = mapped_column(primary_key=True)
    id_remitente: Mapped[int] = mapped_column(
        ForeignKey("empleados.id_empleado", ondelete="CASCADE"), index=True
    )
    id_destinatario: Mapped[int] = mapped_column(
        ForeignKey("empleados.id_empleado", ondelete="CASCADE"), index=True
    )
    id_sede: Mapped[int] = mapped_column(
        ForeignKey("sedes.id_sede", ondelete="CASCADE"), index=True
    )
    contenido: Mapped[str] = mapped_column(Text)
    leido: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", index=True
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), index=True
    )

    # Relaciones
    remitente: Mapped["Empleado"] = relationship(foreign_keys=[id_remitente])
    destinatario: Mapped["Empleado"] = relationship(foreign_keys=[id_destinatario])
    sede: Mapped["Sede"] = relationship(foreign_keys=[id_sede])

    def __repr__(self) -> str:
        return f"<MensajeChat de={self.id_remitente} para={self.id_destinatario} sede={self.id_sede}>"
