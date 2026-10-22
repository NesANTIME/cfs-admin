from .base import Base
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column



class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    jti: Mapped[str] = mapped_column(String(32), primary_key = True)
    id_empleado: Mapped[int] = mapped_column(
        ForeignKey("empleados.id_empleado", ondelete = "CASCADE"), index = True
    )
    expira: Mapped[datetime] = mapped_column(DateTime(timezone = True))
    revocado: Mapped[bool] = mapped_column(default = False, server_default = "false")
