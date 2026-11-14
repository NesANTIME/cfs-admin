from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int

class LoginRequest(BaseModel):
    username: str = Field(..., min_length = 3, max_length = 50)
    password: str = Field(..., min_length = 1, max_length = 128)

class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., max_length = 2048)

class SedeCreate(BaseModel):
    nombre: str = Field(..., min_length = 1, max_length = 100)
    ubicacion: str = Field(..., min_length = 1, max_length = 255)
    descripcion: str = Field(..., min_length = 1, max_length = 1000)

class AdminSedeInfo(BaseModel):
    model_config = ConfigDict(from_attributes = True)

    id_empleado: int
    nombre: str
    usuario: str
    activo: bool = True

class SedeResponse(BaseModel):
    model_config = ConfigDict(from_attributes = True)

    id_sede: int
    nombre: str
    ubicacion: str
    descripcion: str | None = None
    id_tecnico_jefe: int | None = None
    admin_s: AdminSedeInfo | None = None
    admins_s_disponibles: list[AdminSedeInfo] = []

class SedeTecnicoUpdate(BaseModel):
    id_empleado: int | None = None

class DispositivoResponse(BaseModel):
    model_config = ConfigDict(from_attributes = True)

    id_dispositivo: int
    nombre: str
    direccion_ip: str
    mac: str
    tipo: str
    estado: str

    @field_validator("direccion_ip", "mac", mode = "before")
    @classmethod
    def convertirAStr(cls, valor):
        return str(valor) if valor is not None else ""

class SedeDetalleResponse(BaseModel):
    model_config = ConfigDict(from_attributes = True)

    id_sede: int
    nombre: str
    ubicacion: str
    descripcion: str | None = None
    id_tecnico_jefe: int | None = None
    dispositivos: list[DispositivoResponse] = []


class ServicioUsuarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes = True)

    tipo_servicio: str
    habilitado: bool


class MeResponse(BaseModel):
    """Esquema de respuesta para GET /me."""
    model_config = ConfigDict(from_attributes=True)

    id: int               # id_empleado
    nombre: str
    usuario: str
    tipo: str
    rol: str | None = None
    direccion: str | None = None
    tipo_admin: str       # 'admin-g', 'admin-s', 'usuario'
    nivel_acceso: int | None = None
    id_sede: int | None = None
    es_admin: bool = False
    es_admin_g: bool = False
    es_admin_s: bool = False
    uid_publico: str | None = None
    sede_nombre: str | None = None
    servicios: list[ServicioUsuarioResponse] = []


class ChangePasswordRequest(BaseModel):
    contrasena_actual: str = Field(..., min_length = 1, max_length = 128)
    contrasena_nueva: str = Field(..., min_length = 8, max_length = 128)


class UsuarioSedeResponse(BaseModel):
    model_config = ConfigDict(from_attributes = True)

    id_empleado: int
    nombre: str
    usuario: str
    tipo: str
    activo: bool
    en_linea: bool = False
    uid_publico: str | None = None
    rol: str | None = None
    servicios: list[ServicioUsuarioResponse] = []


# --- CRUD de Usuarios ---

TIPOS_USUARIO_VALIDOS = ("usuario_sede", "tecnico")

class UsuarioCreate(BaseModel):
    nombre: str = Field(..., min_length = 1, max_length = 100)
    usuario: str = Field(..., min_length = 3, max_length = 50)
    contrasena: str = Field(..., min_length = 8, max_length = 128)
    tipo: str = Field(..., pattern = "^(usuario_sede|tecnico)$")
    direccion: str | None = Field(None, max_length = 255)
    es_admin_s: bool = False

class UsuarioUpdate(BaseModel):
    nombre: str | None = Field(None, min_length = 1, max_length = 100)
    contrasena: str | None = Field(None, min_length = 8, max_length = 128)
    activo: bool | None = None

class UsuarioEstadoUpdate(BaseModel):
    activo: bool

class UsuarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes = True)
    id_empleado: int
    nombre: str
    usuario: str
    tipo: str
    activo: bool
    uid_publico: str | None = None
    id_sede: int | None = None


# --- Contactos ---

class ContactoBuscarRequest(BaseModel):
    uid_publico: str = Field(..., min_length = 10, max_length = 50)

class ContactoBuscarResponse(BaseModel):
    model_config = ConfigDict(from_attributes = True)
    id_empleado: int
    nombre: str
    usuario: str
    uid_publico: str
    ya_es_contacto: bool = False
    solicitud_pendiente: bool = False

class ContactoAgregarRequest(BaseModel):
    identificador: str = Field(..., min_length = 2, max_length = 50)
    alias: str | None = Field(None, max_length = 100)

class ContactoResponse(BaseModel):
    model_config = ConfigDict(from_attributes = True)
    id_contacto_rel: int
    id_empleado: int
    nombre: str | None = None
    usuario: str | None = None
    uid_publico: str
    id_sede: int | None = None
    sede_nombre: str | None = None
    en_linea: bool = False
    registrado_formalmente: bool = False
    alias: str | None = None
    servicios: list[str] = []


# --- Chat ---

class MensajeChatCreate(BaseModel):
    destinatario_id: int
    contenido: str = Field(..., min_length = 1, max_length = 3500000)
    tipo: str = Field(default = "texto", pattern = "^(texto|imagen)$")

    @model_validator(mode="after")
    def validar_tamano(self):
        if self.tipo == "texto" and len(self.contenido) > 5000:
            raise ValueError("Los mensajes de texto no pueden exceder los 5000 caracteres.")
        return self

class MensajeChatResponse(BaseModel):
    model_config = ConfigDict(from_attributes = True)
    id: int
    id_remitente: int
    id_destinatario: int
    id_sede: int
    contenido: str
    tipo: str = "texto"
    leido: bool
    creado_en: str
    es_mio: bool = False
    remitente_nombre: str | None = None


# --- Videoconferencia ---

class SalaVideoconfCreate(BaseModel):
    id_contacto: int | None = Field(None, description="ID de empleado del contacto (no el ID de la relación).")
    identificador: str | None = Field(None, min_length=2, max_length=50, description="Username o UID exacto de 36 caracteres.")

    @model_validator(mode="after")
    def validar_identificador(self):
        if (self.id_contacto is None) == (self.identificador is None):
            raise ValueError("Debes indicar id_contacto o identificador, pero no ambos.")
        return self

class SalaVideoconfResponse(BaseModel):
    codigo_sala: str
    id_sala: int
    id_sede: int
    id_iniciador: int
    id_invitado: int | None = None
    nombre_iniciador: str | None = None
    nombre_invitado: str | None = None
    usuario_invitado: str | None = None
    uid_invitado: str | None = None
    sede_invitado: str | None = None
    sede_iniciador: str | None = None
    estado_invitacion: str | None = None
    invitacion_id: int | None = None
    expira_en: datetime | None = None
    activa: bool
    es_iniciador: bool = False
    puede_entrar: bool = False

class InvitacionVideoconfResponse(BaseModel):
    id: int
    id_sala: int
    codigo_sala: str
    id_invitador: int
    nombre_invitador: str | None = None
    usuario_invitador: str | None = None
    uid_invitador: str | None = None
    sede_invitador: str | None = None
    id_invitado: int | None = None
    nombre_invitado: str | None = None
    usuario_invitado: str | None = None
    uid_invitado: str | None = None
    estado: str
    creada_en: datetime
    expira_en: datetime
    respondida_en: datetime | None = None
    puede_aceptar: bool = False
    es_recibida: bool = True

class IceServerConfig(BaseModel):
    urls: list[str]
    username: str | None = None
    credential: str | None = None

class IceConfigResponse(BaseModel):
    iceServers: list[IceServerConfig]

class SenalVideoconfCreate(BaseModel):
    tipo: str = Field(..., pattern="^(offer|answer|candidate)$")
    para_id: int
    sdp: dict | None = None
    candidate: dict | None = None

    @model_validator(mode="after")
    def validar_carga(self):
        if self.tipo in ("offer", "answer") and not self.sdp:
            raise ValueError("Las señales offer/answer requieren sdp.")
        if self.tipo == "candidate" and not self.candidate:
            raise ValueError("Las señales candidate requieren candidate.")
        return self


