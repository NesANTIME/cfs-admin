from datetime import datetime
from .base import Base
from typing import TYPE_CHECKING
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

if (TYPE_CHECKING):
    from .rol import Rol
    from .sede import Sede
    from .servicio_red import ServicioRed
    from .servicio_usuario import ServicioUsuario




class Empleado(Base):
    __tablename__ = "empleados"

    id_empleado: Mapped[int] = mapped_column(primary_key = True)
    nombre: Mapped[str] = mapped_column(String(100))
    usuario: Mapped[str] = mapped_column(String(50), unique = True)
    contrasena_hash: Mapped[str] = mapped_column(String(255))
    tipo: Mapped[str] = mapped_column(String(20))
    activo: Mapped[bool] = mapped_column(default = True, server_default = "true")
    intentos_fallidos: Mapped[int] = mapped_column(default = 0, server_default = "0")
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone = True))
    en_linea: Mapped[bool] = mapped_column(Boolean(), default=False, server_default="false")
    ultima_vez_en_linea: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


    id_rol: Mapped[int] = mapped_column(ForeignKey("roles.id_rol", ondelete = "RESTRICT"))
    rol: Mapped["Rol"] = relationship(back_populates = "empleados")

    servicios_usuario: Mapped[list["ServicioUsuario"]] = relationship(
        back_populates="empleado", cascade="all, delete-orphan"
    )

    __mapper_args__ = {"polymorphic_on": "tipo", "polymorphic_identity": "empleado"}
    __table_args__ = (
        CheckConstraint("char_length(trim(nombre)) > 0", name = "nombre_no_vacio"),
        CheckConstraint("char_length(trim(usuario)) >= 3", name = "usuario_min_3"),
        CheckConstraint("contrasena_hash LIKE '$argon2%'", name = "contrasena_es_hash"),
        CheckConstraint(
            "tipo IN ('empleado','tecnico','tecnico_jefe','usuario_sede')",
            name = "tipo_valido",
        ),
    )

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.usuario}>"




class Tecnico(Empleado):
    __tablename__ = "tecnicos"

    id_empleado: Mapped[int] = mapped_column(
        ForeignKey("empleados.id_empleado", ondelete = "CASCADE"), primary_key = True
    )
    id_sede: Mapped[int | None] = mapped_column(ForeignKey("sedes.id_sede", ondelete = "SET NULL"))
    sede: Mapped["Sede | None"] = relationship(back_populates = "tecnicos", foreign_keys = [id_sede])
    servicios: Mapped[list["ServicioRed"]] = relationship(
        back_populates = "tecnico", foreign_keys = "ServicioRed.id_tecnico"
    )

    __mapper_args__ = {"polymorphic_identity": "tecnico"}




class TecnicoJefe(Tecnico):
    __tablename__ = "tecnico_jefe"

    id_empleado: Mapped[int] = mapped_column(
        ForeignKey("tecnicos.id_empleado", ondelete = "CASCADE"), primary_key = True
    )
    nivel_acceso: Mapped[int] = mapped_column(default = 1, server_default = "1")
    sedes_a_cargo: Mapped[list["Sede"]] = relationship(back_populates = "jefe", foreign_keys = "Sede.id_tecnico_jefe")
    servicios_jefe: Mapped[list["ServicioRed"]] = relationship(
        back_populates = "tecnico_jefe", foreign_keys = "ServicioRed.id_tecnico_jefe"
    )

    __mapper_args__ = {"polymorphic_identity": "tecnico_jefe"}
    __table_args__ = (
        CheckConstraint("nivel_acceso >= 1", name = "nivel_acceso_positivo"),
    )


class UsuarioSede(Empleado):
    __tablename__ = "usuarios_sede"

    id_empleado: Mapped[int] = mapped_column(
        ForeignKey("empleados.id_empleado", ondelete = "CASCADE"), primary_key = True
    )
    direccion: Mapped[str | None] = mapped_column(String(255))
    servicios: Mapped[list["ServicioRed"]] = relationship(
        back_populates = "usuario_sede", foreign_keys = "ServicioRed.id_usuario_sede"
    )

    __mapper_args__ = {"polymorphic_identity": "usuario_sede"}
