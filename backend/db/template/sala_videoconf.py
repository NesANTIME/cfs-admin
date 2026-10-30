from datetime import datetime, timezone
import uuid
from .base import Base
from typing import TYPE_CHECKING
from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from .empleado import Empleado
    from .sede import Sede


class SalaVideoconf(Base):
    __tablename__ = "salas_videoconf"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo_sala: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, default=lambda: str(uuid.uuid4())
    )
    id_sede: Mapped[int] = mapped_column(
        ForeignKey("sedes.id_sede", ondelete="CASCADE"), index=True
    )
    id_iniciador: Mapped[int] = mapped_column(
        ForeignKey("empleados.id_empleado", ondelete="CASCADE"), index=True
    )
    id_invitado: Mapped[int | None] = mapped_column(
        ForeignKey("empleados.id_empleado", ondelete="SET NULL"), nullable=True, index=True
    )
    activa: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )

    # Relaciones
    iniciador: Mapped["Empleado"] = relationship(foreign_keys=[id_iniciador])
    invitado: Mapped["Empleado | None"] = relationship(foreign_keys=[id_invitado])
    sede: Mapped["Sede"] = relationship(foreign_keys=[id_sede])

    def __repr__(self) -> str:
        return f"<SalaVideoconf codigo={self.codigo_sala} sede={self.id_sede} activa={self.activa}>"
