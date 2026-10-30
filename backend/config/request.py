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

class SedeResponse(BaseModel):
    model_config = ConfigDict(from_attributes = True)

    id_sede: int
    nombre: str
    ubicacion: str
    descripcion: str | None = None
    id_tecnico_jefe: int | None = None

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


class UsuarioSedeResponse(BaseModel):
    model_config = ConfigDict(from_attributes = True)

    id_empleado: int
    nombre: str
    usuario: str
    tipo: str
    activo: bool
    en_linea: bool = False
    servicios: list[ServicioUsuarioResponse] = []


# --- CRUD de Usuarios ---

TIPOS_USUARIO_VALIDOS = ("usuario_sede", "tecnico")

class UsuarioCreate(BaseModel):
    nombre: str = Field(..., min_length = 1, max_length = 100)
    usuario: str = Field(..., min_length = 3, max_length = 50)
    contrasena: str = Field(..., min_length = 8, max_length = 128)
    tipo: str = Field(..., pattern = "^(usuario_sede|tecnico)$")
    direccion: str | None = Field(None, max_length = 255)

class UsuarioUpdate(BaseModel):
    nombre: str | None = Field(None, min_length = 1, max_length = 100)
    contrasena: str | None = Field(None, min_length = 8, max_length = 128)

class UsuarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes = True)
    id_empleado: int
    nombre: str
    usuario: str
    tipo: str
    activo: bool

