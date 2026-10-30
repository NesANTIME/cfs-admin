from datetime import datetime, timezone
from .base import Base
from typing import TYPE_CHECKING
from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from .empleado import Empleado


class Contacto(Base):
    __tablename__ = "contactos"

    id: Mapped[int] = mapped_column(primary_key=True)
    id_usuario: Mapped[int] = mapped_column(
        ForeignKey("empleados.id_empleado", ondelete="CASCADE"), index=True
    )
    id_contacto: Mapped[int] = mapped_column(
        ForeignKey("empleados.id_empleado", ondelete="CASCADE"), index=True
    )
    alias: Mapped[str | None] = mapped_column(String(100), nullable=True)
    registrado_formalmente: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )

    # Relaciones
    usuario: Mapped["Empleado"] = relationship(foreign_keys=[id_usuario])
    contacto: Mapped["Empleado"] = relationship(foreign_keys=[id_contacto])

    __table_args__ = (
        UniqueConstraint("id_usuario", "id_contacto", name="uq_contactos_usuario_contacto"),
    )

    def __repr__(self) -> str:
        return f"<Contacto user={self.id_usuario} contacto={self.id_contacto} formal={self.registrado_formalmente}>"
