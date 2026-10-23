# CFS-Admin

Plataforma web en desarrollo para la autenticación y administración de usuarios, con una API REST en **FastAPI**, persistencia en **PostgreSQL** y una interfaz web estática servida por **Apache HTTP Server**. El entorno de desarrollo se ejecuta con Docker Compose.

> **Estado del proyecto:** prototipo en desarrollo. Actualmente incluye la pantalla de inicio de sesión, endpoints de autenticación, emisión y renovación de tokens JWT, cierre de sesión, consulta del usuario autenticado y modelos de datos para empleados, roles, técnicos, sedes y servicios de red. No debe considerarse listo para producción sin completar y revisar la autorización por roles, las pruebas y el despliegue seguro.

## Propósito y uso del proyecto

CFS-Admin es un **proyecto de investigación y ejemplo educativo** creado con fines de exploración, práctica y aprendizaje sobre el desarrollo de aplicaciones web, APIs, autenticación, bases de datos y despliegue mediante contenedores.

Su código y documentación se ofrecen para **uso libre con fines de estudio, práctica y aprendizaje**. Puedes utilizarlo como referencia para experimentar, comprender su arquitectura y desarrollar tus propias versiones. Antes de redistribuirlo o incorporarlo a otros proyectos, revisa y conserva los avisos de licencia que correspondan; si el repositorio no incluye una licencia explícita, consulta con el autor las condiciones de redistribución.


## Características

- Inicio de sesión mediante usuario y contraseña.
- Hash de contraseñas con Argon2.
- Tokens de acceso y renovación JWT.
- Registro de tokens de renovación en PostgreSQL y posibilidad de revocarlos al cerrar sesión.
- Protección contra intentos repetidos de inicio de sesión: límite de solicitudes y bloqueo temporal tras varios intentos fallidos.
- Consulta de la identidad del usuario autenticado mediante `GET /me`.
- Modelos SQLAlchemy para roles, empleados, técnicos, técnicos jefe, usuarios de sede, sedes y servicios/dispositivos de red.
- Configuración por variables de entorno.
- Servicios en contenedores independientes y volumen persistente para PostgreSQL.
- Proxy inverso del frontend: el navegador consulta la API mediante `/api/`.

## Tecnologías

| Componente | Tecnología |
|---|---|
| Backend | Python 3.13, FastAPI, Uvicorn |
| ORM | SQLAlchemy |
| Migraciones | Alembic |
| Base de datos | PostgreSQL 18 |
| Validación de configuración | Pydantic Settings |
| Autenticación | JWT (`PyJWT`) y Argon2 |
| Frontend | HTML, CSS y JavaScript |
| Servidor web / proxy | Apache HTTP Server |
| Entorno | Docker y Docker Compose |


## Requisitos

Instala o ten disponible:

- Docker Engine.
- Docker Compose v2 (`docker compose`).
- Un navegador web moderno.
- Terminal para ejecutar los comandos.

Comprueba la instalación:

```bash
docker --version
docker compose version
```

## Configuración

Docker Compose lee el archivo `.env` desde la carpeta donde se encuentra `compose.yaml`.

### 1. Crear `.env`

En la raíz del proyecto:

```bash
cp examples/.env.example .env
```

Edita `.env` y configura, como mínimo, estos valores:

```dotenv
PORT_APP=8000
TRUSTED_PROXIES=172.28.0.10

# Genera una clave con: python3 -c 'import secrets; print(secrets.token_hex(32))'
JWT_SECRET_KEY=REEMPLAZA_POR_UNA_CLAVE_ALEATORIA_DE_64_CARACTERES_HEXADECIMALES
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

CORS_ALLOW_ORIGINS=["http://localhost:8080"]
CORS_ALLOW_METHODS=["GET", "POST", "PUT", "DELETE"]
CORS_ALLOW_HEADERS=["Content-Type", "Authorization"]
CORS_ALLOW_CREDENTIALS=true

POSTGRES_USER=cfs_user
POSTGRES_PASSWORD=CAMBIA_ESTA_CONTRASENA
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=cfs-admin
```

Genera una clave JWT segura:

```bash
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

Copia el resultado completo en `JWT_SECRET_KEY`. No reutilices la clave de ejemplo ni publiques el archivo `.env`.

**Importante sobre el host de PostgreSQL:** cuando la API corre en Docker Compose, debe conectarse al nombre del servicio de base de datos (`db`), no a `localhost`. Dentro de un contenedor, `localhost` apunta a ese mismo contenedor.

**Sobre `TRUSTED_PROXIES`:** debe coincidir con la IP fija del contenedor `web` definida en `compose.yaml` (`172.28.0.10`). Uvicorn solo acepta `X-Forwarded-For` desde esa IP; si cambias la subred o la IP en Compose, actualiza también esta variable.

El archivo `examples/.env.example` es una plantilla; no es cargado automáticamente por Compose. Debes crear el `.env` en la raíz.

## Ejecución con Docker Compose

Ejecuta los comandos desde la raíz del repositorio, donde está `compose.yaml`.

### Construir e iniciar los servicios

```bash
docker compose up --build -d
```

El archivo Compose define estos servicios:

- `db`: PostgreSQL 18.
- `api`: backend FastAPI.
- `web`: frontend estático con Apache y proxy hacia la API.

El backend aplica las migraciones de Alembic al iniciar el contenedor
(`python cfs-app.py migrate-db`) y luego inicia la API. Las tablas se crean y
actualizan mediante las migraciones versionadas en `backend/migrations/versions/`.

### Migraciones de base de datos

```bash
# Aplicar migraciones pendientes
docker compose exec api python cfs-app.py migrate-db

# Crear una migración nueva después de cambiar los modelos.
# El bind mount es necesario para que el archivo generado quede en backend/migrations.
docker compose run --rm -v "$PWD/backend:/app" api alembic revision --autogenerate -m "descripción del cambio"

# Aplicar y comprobar que no hay diferencias pendientes
docker compose exec api alembic upgrade head
docker compose exec api alembic check
```

El comando histórico `python cfs-app.py create-db` se conserva como alias de
`migrate-db`; ya no usa `create_all`.

> Si ya existía una base creada con `create_all` y su esquema coincide con la
> migración inicial, ejecuta una sola vez `docker compose exec api alembic stamp head`
> para marcarla como migrada antes de arrancar la nueva versión.

### Verificar el estado

```bash
docker compose ps
```

### Ver los registros

```bash
docker compose logs -f api
```

También puedes consultar todos los servicios:

```bash
docker compose logs --tail=100 db api web
```

## Acceso a la aplicación

Con la configuración predeterminada, abre:

- **Frontend:** <http://localhost:8080>
- **API a través del proxy:** `http://localhost:8080/api/`
- **Documentación Swagger durante desarrollo:** `http://localhost:8080/api/docs` solo si `APP_ENV` no está configurado como `production` en el contenedor.

En la configuración Compose actual, la API usa el entorno de producción implícitamente si `APP_ENV` se configura como tal. En producción, Swagger y OpenAPI se deshabilitan.

El puerto `8000` de la API no se publica directamente en el host en el Compose actual; el navegador llega a ella a través de Apache en el servicio `web`.

### Crear un usuario desde la terminal

El script `examples/crear_usuario.py` pide las credenciales de PostgreSQL y los datos del nuevo usuario, genera el hash Argon2 e inserta el empleado en la base de datos. Ejecútalo desde la raíz:

```bash
./examples/crear_usuario.py
```

Si no tienes el entorno virtual `backend/venv`, puedes ejecutarlo dentro del contenedor `api`:

```bash
docker compose run --rm -v "$PWD/examples:/examples:ro" api python /examples/crear_usuario.py
```

Por defecto crea un usuario de tipo `empleado` con rol `Usuario`. Para crear un administrador (`tecnico_jefe`) usa `docker compose exec api python cfs-app.py create-admin`.
