from pydantic import BaseModel, ConfigDict, Field, field_validator

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

class ContactoAgregarRequest(BaseModel):
    uid_publico: str = Field(..., min_length = 10, max_length = 50)
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
    contenido: str = Field(..., min_length = 1, max_length = 5000)

class MensajeChatResponse(BaseModel):
    model_config = ConfigDict(from_attributes = True)
    id: int
    id_remitente: int
    id_destinatario: int
    id_sede: int
    contenido: str
    leido: bool
    creado_en: str
    es_mio: bool = False
    remitente_nombre: str | None = None


# --- Videoconferencia ---

class SalaVideoconfCreate(BaseModel):
    id_contacto: int | None = None

class SalaVideoconfResponse(BaseModel):
    model_config = ConfigDict(from_attributes = True)
    codigo_sala: str
    id_sede: int
    id_iniciador: int
    id_invitado: int | None = None
    activa: bool


