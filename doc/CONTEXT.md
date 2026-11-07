# Contexto del proyecto — CFS-Admin

> **Documento:** contexto técnico del repositorio
> **Última actualización:** 2026-10-22
> **Rama analizada:** `development` (commit `1c13758`)
> **Naturaleza:** prototipo educativo / proyecto de investigación, **no listo para producción**

Este documento describe qué es CFS-Admin, cómo está construido, cómo se ejecuta y
cuáles son sus limitaciones y trabajo pendiente. Está pensado como punto de partida
para cualquier persona (o agente) que retome el proyecto.

---

## Índice

1. [Resumen ejecutivo](#1-resumen-ejecutivo)
2. [Estado actual](#2-estado-actual)
3. [Arquitectura](#3-arquitectura)
4. [Estructura del repositorio](#4-estructura-del-repositorio)
5. [Backend](#5-backend)
6. [API REST](#6-api-rest)
7. [Autenticación y seguridad](#7-autenticación-y-seguridad)
8. [Modelo de datos](#8-modelo-de-datos)
9. [Frontend](#9-frontend)
10. [Despliegue y operación](#10-despliegue-y-operación)
11. [Hallazgos y deuda técnica](#11-hallazgos-y-deuda-técnica)
12. [Convenciones del código](#12-convenciones-del-código)
13. [Glosario](#13-glosario)

---

## 1. Resumen ejecutivo

**CFS-Admin** es una plataforma web en desarrollo para autenticación y
administración de usuarios, orientada al monitoreo de clientes/servicios de red.
Combina una API REST en **FastAPI**, persistencia en **PostgreSQL** y un frontend
estático servido por **Apache HTTP Server**, todo orquestado con **Docker Compose**.

Lo implementado hasta ahora:

- Pantalla de inicio de sesión y panel de monitoreo (con datos simulados).
- Autenticación con **Argon2** y tokens **JWT** de acceso y renovación.
- Persistencia y revocación de refresh tokens.
- Bloqueo temporal de cuentas por intentos fallidos y rate limiting.
- Endpoint `GET /me` para consultar la identidad autenticada.
- Modelos SQLAlchemy para empleados, técnicos, jefes, usuarios de sede, roles,
  sedes, servicios de red y dispositivos de red.

Lo que **no** existe todavía:

- Autorización efectiva por roles en los endpoints (existe el helper, no se usa).
- Pruebas automatizadas ni CI.
- Integración real del panel con la API.
- Endurecimiento de despliegue (TLS, gestión de secretos, proxy confiable).

---

## 2. Estado actual

| Área | Estado | Notas |
|---|---|---|
| Autenticación (login/refresh/logout/me) | Funcional | Probada manualmente; sin tests |
| Bloqueo por intentos fallidos | Funcional | 5 intentos → 15 minutos |
| Rate limiting | Funcional | Límite por IP; estado en memoria |
| Modelo de datos | Versionado | Migración inicial con Alembic |
| Panel de monitoreo | Protegido en cliente | Valida `/me`; datos aún simulados |
| Protección de rutas del frontend | Implementada | Redirección si la sesión no es válida |
| Creación de administrador | Manual | `python cfs-app.py create-admin` |
| Tests / CI | Ausente | No hay carpeta de pruebas ni workflows |
| Documentación | Parcial | README general; este documento complementa |

---

## 3. Arquitectura

### 3.1 Topología de contenedores

```
                         host :8080
                             │
                    ┌────────▼─────────┐
                    │  web (httpd:2.4) │
                    │  Apache + proxy  │
                    └────┬────────┬────┘
             estáticos   │        │  /api/*  →  http://api:8000/*
        (index, home)    │        │
                         │   ┌────▼──────────────┐
                         │   │ api (FastAPI)     │
                         │   │ python:3.13-slim  │
                         │   └────┬──────────────┘
                         │        │ psycopg2
                         │   ┌────▼──────────────┐
                         └──▶│ db (postgres:18)  │
                             │ volumen persist.  │
                             └───────────────────┘
```

- El puerto `8000` de la API **no se publica** en el host; solo se llega a ella
  mediante el proxy de Apache.
- Apache elimina el prefijo `/api/` al reenviar, por lo que `/api/login` llega a
  FastAPI como `/login`.
- La base de datos solo es accesible dentro de la red de Compose.

### 3.2 Flujo de una petición de login

```
Navegador            Apache (:8080)          FastAPI                  PostgreSQL
   │                      │                     │                        │
   │ POST /api/login      │                     │                        │
   ├─────────────────────▶│  POST /login        │                        │
   │                      ├────────────────────▶│  SELECT empleado       │
   │                      │                     ├───────────────────────▶│
   │                      │                     │◀───────────────────────┤
   │                      │                     │  verifica Argon2       │
   │                      │                     │  emite JWT access+refresh
   │                      │                     │  INSERT refresh_token  │
   │                      │                     ├───────────────────────▶│
   │  {access, refresh}   │                     │                        │
   │◀─────────────────────┤◀────────────────────┤                        │
   │ sessionStorage       │                     │                        │
```

---

## 4. Estructura del repositorio

```
cfs-admin-stable/
├── compose.yaml                 # Servicios db, api y web
├── .env                         # Configuración local (ignorado por git)
├── .gitignore                   # Ignora .env y doc/
├── README.md                    # Guía de uso general
├── LICENSE.md                   # Licencia del proyecto
├── examples/
│   └── .env.example             # Plantilla de variables de entorno
├── backend/
│   ├── cfs-app.py               # CLI: run-app | migrate-db | create-admin
│   ├── alembic.ini              # Configuración de Alembic
│   ├── migrations/
│   │   ├── env.py               # Entorno Alembic (lee config.config)
│   │   ├── script.py.mako
│   │   └── versions/            # Migraciones versionadas
│   ├── DockerFile               # Imagen python:3.13-slim
│   ├── requirements.txt
│   ├── api/
│   │   └── login.py             # Endpoints de autenticación
│   ├── config/
│   │   ├── config.py            # Configuración derivada y utilidades
│   │   ├── load.py              # Pydantic Settings + validadores
│   │   └── request.py           # Esquemas de entrada/salida
│   ├── core/
│   │   ├── app.py               # Instancia FastAPI, CORS, routers
│   │   ├── deps.py              # Dependencias de autenticación/autorización
│   │   ├── limiter.py           # slowapi Limiter
│   │   └── security.py          # Argon2 + JWT
│   └── db/
│       ├── controller.py        # Engine, sesión, migrateDb, createAdmin
│       └── template/
│           ├── base.py          # DeclarativeBase + convención de nombres
│           ├── __init__.py      # Registro de todos los modelos
│           ├── empleado.py      # Empleado, Tecnico, TecnicoJefe, UsuarioSede
│           ├── rol.py
│           ├── sede.py
│           ├── servicio_red.py  # ServicioRed + tabla puente
│           ├── dispositivo_red.py
│           └── refresh_token.py
└── frontend/
    ├── DockerFile               # httpd:2.4 + proxy /api/
    ├── index.html               # Login
    ├── index.css
    ├── js/
    │   └── index.js             # Lógica de login
    └── home/
        ├── dashboard.html       # Panel de monitoreo (sesión validada, datos mock)
        ├── dashboard.css
        └── js.js                # Datos simulados, filtros, tema
```

> `backend/venv/` y `backend/__pycache__/` existen localmente pero están ignorados
> por `backend/.gitignore`.

---

## 5. Backend

### 5.1 Punto de entrada (`backend/cfs-app.py`)

CLI con tres subcomandos:

| Comando | Acción |
|---|---|
| `python cfs-app.py run-app` | Inicia Uvicorn con `core.app:app`, `proxy_headers=True` y `forwarded_allow_ips=TRUSTED_PROXIES` |
| `python cfs-app.py migrate-db` | Aplica las migraciones de Alembic hasta `head` |
| `python cfs-app.py create-db` | Alias histórico de `migrate-db` |
| `python cfs-app.py create-admin` | Pide usuario, nombre y contraseña; crea un `TecnicoJefe` con rol `Administrador` |

En Docker, el `CMD` ejecuta `migrate-db` y luego `run-app`, por lo que el esquema
se actualiza automáticamente al arrancar.

### 5.2 Configuración (`config/load.py`)

`Configuration(BaseSettings)` lee variables de entorno (Pydantic Settings), sin
prefijo, y valida:

| Variable | Tipo / defecto | Validación |
|---|---|---|
| `APP_ENV` | `development` \| `production` = `development` | — |
| `HOST_APP` | `127.0.0.1` | — |
| `PORT_APP` | `8000` | — |
| `TRUSTED_PROXIES` | `127.0.0.1` | IP/CIDR del proxy de confianza; se pasa a Uvicorn |
| `JWT_SECRET_KEY` | obligatorio | ≥ 32 caracteres y no puede empezar por `tu_` |
| `JWT_ALGORITHM` | `HS256` \| `HS384` \| `HS512` = `HS256` | — |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | — |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | — |
| `CORS_ALLOW_ORIGINS` | `["http://localhost:8080"]` | Rechaza `*` |
| `CORS_ALLOW_METHODS` | `["GET","POST","OPTIONS"]` | — |
| `CORS_ALLOW_HEADERS` | `["Content-Type","Authorization"]` | — |
| `CORS_ALLOW_CREDENTIALS` | `false` | — |
| `POSTGRES_HOST` | `db` | — |
| `POSTGRES_PORT` | `5432` | — |
| `POSTGRES_USER` / `PASSWORD` / `DB` | obligatorios | — |
| `POSTGRES_SQL_ECHO` | `false` | — |

`config/config.py` expone además:

- `CONFIG`: instancia única de la configuración.
- `MountUrlDb()`: construye la URL `postgresql+psycopg2` con `URL.create`.
- `getLongHashPassword()`: longitud mínima de contraseña (**8**).
- `HashDummy()`: hash señuelo para igualar tiempos cuando el usuario no existe.
- `ConfigBloq()`: `(5, 15)` → máximo de intentos y minutos de bloqueo.

`config/request.py` define los esquemas Pydantic:

- `LoginRequest`: `username` (3–50), `password` (1–128).
- `RefreshRequest`: `refresh_token` (máx. 2048).
- `TokenResponse`: `access_token`, `refresh_token`, `token_type="bearer"`, `expires_in`.

### 5.3 Aplicación FastAPI (`core/app.py`)

- Título: `cfs-admin-api`.
- En `APP_ENV=production` se deshabilitan `/docs`, `/redoc` y `/openapi.json`.
- Registra `slowapi` (`app.state.limiter` y manejador de `RateLimitExceeded`).
- Añade `CORSMiddleware` con la configuración anterior.
- Importa `db.template` para registrar todos los modelos antes de crear tablas.
- Incluye el router de `api/login.py` **sin prefijo** (el `/api` lo aporta Apache).

### 5.4 Capa de datos (`db/controller.py`)

- `engine = create_engine(MountUrlDb(), pool_pre_ping=True)`.
- `SessionLocal = sessionmaker(autoflush=False, autocommit=False)`.
- `getDb()`: dependencia generadora que abre y cierra la sesión.
- `migrateDb()`: ejecuta `alembic upgrade head` usando `alembic.ini` y
  `migrations/`, con la misma configuración de base de datos que la API.
- `createAdmin()`: valida duplicados, crea el rol `Administrador` si falta y un
  `TecnicoJefe` con `nivel_acceso=5`. No se ejecuta automáticamente en Compose.

### 5.5 Migraciones (`backend/migrations/`)

- `env.py` construye la URL desde `MountUrlDb()` (variables `POSTGRES_*`), registra
  los modelos de `db.template` y activa `compare_type` y `compare_server_default`.
- La migración inicial `26d4103a93c8` crea todo el esquema, incluidas las
  restricciones, la tabla puente y la FK circular `sedes.id_tecnico_jefe`.
- `alembic check` no detecta diferencias entre los modelos y la base migrada.
- La migración se validó en ambos sentidos (`upgrade head`, `downgrade base`,
  `upgrade head`).
- Si una base antigua ya tiene las tablas de `create_all`, hay que baselinearla
  una vez con `alembic stamp head`; de lo contrario `upgrade` intentará crearlas
  de nuevo.

### 5.6 Dependencias (`core/deps.py`)

- `getCurrentUser`: extrae el Bearer token, exige `type == "access"`, decodifica,
  carga el `Empleado` por `sub`, y comprueba que exista y esté `activo`.
- `requireTipos(*tipos)`: factory de dependencia para exigir `user.tipo`; devuelve
  403 si no coincide. **Actualmente ningún endpoint la utiliza.**

---

## 6. API REST

Todas las rutas viven en la raíz del backend y se exponen al navegador bajo `/api/`
gracias al proxy inverso.

| Método | Ruta pública | Ruta backend | Auth | Límite | Descripción |
|---|---|---|---|---|---|
| POST | `/api/login` | `/login` | No | 10/min por IP | Valida credenciales y emite tokens |
| POST | `/api/refresh` | `/refresh` | Refresh token en body | 30/min por IP | Rota el refresh token |
| POST | `/api/logout` | `/logout` | Refresh token en body | — | Revoca el refresh token (204) |
| GET | `/api/me` | `/me` | Bearer access | — | Devuelve identidad y rol |
| GET | `/api/docs` | `/docs` | No | — | Swagger (solo fuera de producción) |

### 6.1 `POST /login`

Request:

```json
{ "username": "admin", "password": "secreto" }
```

Respuesta `200`:

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

Comportamiento:

- Busca el empleado por `usuario`.
- Si no existe, verifica contra `Dummy_hash` para mantener un tiempo similar.
- Rechaza con `401` si: no existe, está bloqueado, está inactivo o la contraseña
  es incorrecta. El mensaje es siempre el mismo (no filtra qué falló).
- Si la contraseña es incorrecta, incrementa `intentos_fallidos`; al alcanzar 5,
  fija `bloqueado_hasta = now + 15 min` y reinicia el contador.
- En éxito: reinicia contador y bloqueo, re-hashea si Argon2 lo requiere, y emite
  ambos tokens. El `jti` del refresh se persiste en `refresh_tokens`.

### 6.2 `POST /refresh`

- Decodifica el JWT y exige `type == "refresh"`.
- Busca el `jti` en `refresh_tokens`; si no existe → `401`.
- **Detección de reutilización:** si el token ya estaba revocado, revoca todos los
  refresh tokens del empleado y responde `401`.
- Verifica que el empleado siga existiendo y activo.
- Marca el token actual como revocado y emite un par nuevo (rotación).

### 6.3 `POST /logout`

- Decodifica el refresh token y marca su fila como `revocado = True`.
- Si el token es inválido, responde igualmente `204` (idempotente).

### 6.4 `GET /me`

Requiere Bearer access token. Devuelve:

```json
{
  "id": 1,
  "nombre": "Administrador",
  "usuario": "admin",
  "tipo": "tecnico_jefe",
  "rol": "Administrador",
  "direccion": null
}
```

`direccion` solo se rellena si el usuario es un `UsuarioSede`.

### 6.5 Errores

| Código | Cuándo |
|---|---|
| 401 | Credenciales inválidas, token ausente/expirado/de tipo incorrecto, usuario inactivo |
| 403 | `requireTipos` no coincide (aún sin uso) |
| 422 | Validación Pydantic del body |
| 429 | Límite de rate limiting excedido |

---

## 7. Autenticación y seguridad

### 7.1 Contraseñas

- Hash con **Argon2** (`argon2-cffi`, `PasswordHasher` por defecto).
- Mínimo 8 caracteres; máximo aceptado en login 128.
- `check_needs_rehash` permite actualizar el hash tras un login exitoso.
- La columna `contrasena_hash` tiene un `CHECK` que exige el prefijo `$argon2`.

### 7.2 Tokens JWT

- Algoritmo configurable (por defecto HS256), emisor `cfs-admin-api`.
- Claims: `sub`, `iat`, `exp`, `type` (`access`/`refresh`), `jti`, `iss`.
- La decodificación exige `exp`, `iat`, `sub`, `jti` e `iss`, y valida el emisor.
- Access token: 30 minutos en la configuración actual (`.env`); 15 por defecto.
- Refresh token: 7 días.
- El refresh token **no** se guarda completo en la base: solo su `jti`, empleado,
  expiración y estado de revocación.

### 7.3 Protección de cuentas

- 5 intentos fallidos consecutivos → bloqueo de 15 minutos.
- El bloqueo se aplica por usuario, no por IP.
- El mensaje de error no distingue usuario inexistente, contraseña incorrecta,
  cuenta inactiva o bloqueada.

### 7.4 Rate limiting

- `slowapi` con `get_remote_address` y almacenamiento en memoria del proceso.
- `login`: 10/min; `refresh`: 30/min.
- Apache reemplaza `X-Forwarded-For` con la IP real del cliente y Uvicorn solo
  confía en la IP fija del contenedor `web` (`TRUSTED_PROXIES=172.28.0.10`), por
  lo que el límite se aplica por cliente y no de forma global.
- **Limitación restante:** el estado es local al proceso (no sirve con múltiples
  workers/réplicas); para escalar haría falta un backend compartido (Redis).

### 7.5 CORS

- Orígenes explícitos (se rechaza `*`).
- Con el proxy inverso, el navegador habla con el mismo origen (`:8080`), por lo
  que CORS no interviene en el flujo normal.
- En `.env` los orígenes apuntan a `http://localhost:3000`, mientras el README
  documenta `http://localhost:8080`; no afecta al flujo con proxy.

---

## 8. Modelo de datos

### 8.1 Diagrama de entidades

```
┌──────────┐        ┌───────────────┐        ┌──────────────┐
│  roles   │1      *│   empleados   │        │ refresh_     │
│ id_rol   ├────────┤ id_empleado   │1      *│ tokens       │
│ nombre   │        │ usuario (uq)  │────────┤ jti (PK)     │
│ descrip. │        │ tipo (discr.) │        │ id_empleado  │
└──────────┘        │ id_rol        │        │ expira       │
                    └───────┬───────┘        │ revocado     │
                            │ herencia       └──────────────┘
          ┌─────────────────┼──────────────────┐
          │                 │                  │
   ┌──────▼─────┐    ┌──────▼──────┐    ┌──────▼───────┐
   │  tecnicos  │    │tecnico_jefe │    │ usuarios_    │
   │ id_sede    │    │ nivel_acceso│    │ sede         │
   └──────┬─────┘    └──────┬──────┘    │ direccion    │
          │                 │           └──────┬───────┘
          │                 │                  │
          │  ┌──────────────┴───────────┐      │
          │  │                          │      │
     ┌────▼──▼───┐   ┌──────────────┐   │      │
     │  sedes    │1 *│dispositivos_ │   │      │
     │ id_sede   ├───┤red           │   │      │
     │ id_jefe   │   │ ip, mac, ... │   │      │
     └─────┬─────┘   └──────┬───────┘   │      │
           │                │           │      │
           │         ┌──────▼───────┐   │      │
           │         │dispositivo_  │   │      │
           │         │servicio (M2M)│   │      │
           │         └──────┬───────┘   │      │
           │                │           │      │
           │         ┌──────▼───────────▼──────▼───┐
           └─────────┤ servicios_red                │
                     │ id_usuario_sede / id_tecnico │
                     │ id_tecnico_jefe / estado     │
                     └──────────────────────────────┘
```

### 8.2 Herencia de empleados

Se usa **herencia polimórfica de SQLAlchemy** con joined-table inheritance:

- `empleados` es la tabla base; la columna discriminadora es `tipo`.
- Valores permitidos: `empleado`, `tecnico`, `tecnico_jefe`, `usuario_sede`.
- `Tecnico` → tabla `tecnicos` (FK a `empleados`, `ON DELETE CASCADE`).
- `TecnicoJefe` → tabla `tecnico_jefe` (FK a `tecnicos`, `ON DELETE CASCADE`).
  Hereda de `Tecnico`, por lo que también puede tener `id_sede`.
- `UsuarioSede` → tabla `usuarios_sede` (FK a `empleados`).

### 8.3 Tablas y restricciones

| Tabla | Columnas principales | Restricciones destacadas |
|---|---|---|
| `roles` | `id_rol`, `nombre`, `descripcion` | `nombre` único y no vacío |
| `empleados` | `id_empleado`, `nombre`, `usuario`, `contrasena_hash`, `tipo`, `activo`, `intentos_fallidos`, `bloqueado_hasta`, `id_rol` | `usuario` único y ≥ 3; hash Argon2; `tipo` válido; FK rol `RESTRICT` |
| `tecnicos` | `id_empleado` (PK/FK), `id_sede` | FK sede `SET NULL` |
| `tecnico_jefe` | `id_empleado` (PK/FK), `nivel_acceso` | `nivel_acceso >= 1` |
| `usuarios_sede` | `id_empleado` (PK/FK), `direccion` | — |
| `sedes` | `id_sede`, `nombre`, `ubicacion`, `id_tecnico_jefe` | `nombre` único; FK jefe `SET NULL` con `use_alter` |
| `servicios_red` | `id_servicio`, `nombre`, `estado`, tres FKs de responsables | `estado ∈ {activo, inactivo}` |
| `dispositivos_red` | `id_dispositivo`, `nombre`, `direccion_ip` (INET), `mac` (MACADDR), `tipo`, `estado`, `id_sede` | `mac` única; IP única por sede; `estado ∈ {en_linea, fuera_de_linea, desconocido}` |
| `dispositivo_servicio` | `id_dispositivo`, `id_servicio` | PK compuesta; FKs `CASCADE` |
| `refresh_tokens` | `jti`, `id_empleado`, `expira`, `revocado` | `id_empleado` indexado; FK `CASCADE` |

Convención de nombres de constraints definida en `db/template/base.py`
(`pk_`, `fk_`, `uq_`, `ix_`, `ck_`).

### 8.4 Relaciones relevantes

- Un `Rol` tiene muchos `Empleado`.
- Un `Tecnico` pertenece opcionalmente a una `Sede`; un `TecnicoJefe` puede tener
  varias sedes a cargo (`Sede.id_tecnico_jefe`).
- Un `ServicioRed` puede tener como responsables a un `UsuarioSede`, un `Tecnico`
  y/o un `TecnicoJefe` (todos opcionales).
- `ServicioRed` ↔ `DispositivoRed` es muchos-a-muchos vía `dispositivo_servicio`.
- Una `Sede` tiene muchos `DispositivoRed` (borrado en cascada).

---

## 9. Frontend

### 9.1 Login (`frontend/index.html` + `frontend/js/index.js`)

- Formulario con validación local (usuario y contraseña no vacíos).
- Botón mostrar/ocultar contraseña.
- `fetch` a `${urlserver}/login` con `urlserver = "/api"`.
- Guarda `access_token` y `refresh_token` en `sessionStorage`.
- Muestra mensajes de error/éxito accesibles (`role="alert"`, `aria-live`).
- Tras un login correcto redirige con `window.location.assign("home/dashboard.html")`.
- Estilos con variables CSS, modo claro/oscuro automático y `prefers-reduced-motion`.

### 9.2 Panel (`frontend/home/dashboard.html` + `frontend/home/js.js`)

- **Protección de sesión:** al cargar valida el access token contra `GET /api/me`.
  Si expiró, intenta `POST /api/refresh`; si falla, limpia `sessionStorage` y
  redirige al login. El `<main>` permanece oculto hasta completar la validación.
- **Cierre de sesión:** "Salir" llama a `POST /api/logout` con el refresh token
  (`keepalive`), limpia `sessionStorage` y vuelve a `../index.html`.
- KPIs: clientes, en línea, con alertas, caídos.
- Tabla con cliente, servicio, estado, latencia, sparkline y disponibilidad.
- Búsqueda por texto y filtros por estado.
- Tema claro/oscuro persistido en `localStorage` (`cfs-theme`).
- Refresco automático cada 15 segundos.
- **Los datos de la tabla siguen siendo simulados**: `cargarDatos()` genera
  lecturas aleatorias; la única llamada real a la API es la validación de sesión.

### 9.3 Flujo actual

```
index.html → POST /api/login → sessionStorage → /home/dashboard.html
home/dashboard.html → GET /api/me (o /api/refresh) → datos mock
"Salir" → POST /api/logout → limpiar sessionStorage → ../index.html
```

---

## 10. Despliegue y operación

### 10.1 Servicios de Compose

| Servicio | Imagen / build | Puertos | Notas |
|---|---|---|---|
| `db` | `postgres:18` | interno 5432 | Volumen `postgres_data`; healthcheck `pg_isready` |
| `api` | `backend/DockerFile` | interno 8000 | Espera a `db` saludable; usuario no root `app` |
| `web` | `frontend/DockerFile` | `8080:80` | Apache con `ProxyPass /api/ http://api:8000/` |

- `api` usa `env_file: .env`, por lo que recibe también `JWT_*_EXPIRE`,
  `CORS_*` y el resto de variables, además de los overrides `APP_ENV=production`,
  `HOST_APP=0.0.0.0`, `POSTGRES_HOST=db` y `TRUSTED_PROXIES=172.28.0.10`.
- La red `cfs` fija la subred `172.28.0.0/24` y la IP `172.28.0.10` para `web`;
  Uvicorn solo acepta cabeceras de proxy desde esa IP.
- Apache reemplaza `X-Forwarded-For` con `REMOTE_ADDR` antes de proxyar.
- `web` copia todo `frontend/` a `/usr/local/apache2/htdocs/`.
- El frontend incluye `DockerFile` (con F mayúscula) y el contexto de build es la
  raíz del repositorio.

### 10.2 Variables de entorno

Se leen desde `.env` en la raíz. `.env` está ignorado por git; `examples/.env.example`
es la plantilla y `api` lo carga con `env_file`. En el `.env` local actual:

- `PORT_APP=8000`, access token 30 min, refresh 7 días.
- `CORS_ALLOW_ORIGINS=["http://localhost:3000"]`.
- `POSTGRES_HOST=localhost` (válido fuera de Compose; Compose lo sobrescribe a `db`).
- `JWT_SECRET_KEY` de 64 caracteres (distinto de la plantilla).
- `TRUSTED_PROXIES` es opcional en `.env`; Compose usa `172.28.0.10` por defecto.

### 10.3 Comandos útiles

```bash
# Levantar todo
docker compose up --build -d

# Estado y logs
docker compose ps
docker compose logs -f api

# Crear el administrador inicial (interactivo, dentro del contenedor)
docker compose exec api python cfs-app.py create-admin

# Aplicar migraciones pendientes
docker compose exec api python cfs-app.py migrate-db

# Generar una migración tras cambiar modelos (bind mount para conservarla)
docker compose run --rm -v "$PWD/backend:/app" api alembic revision --autogenerate -m "cambio"

# Acceso
# Frontend:  http://localhost:8080
# API:       http://localhost:8080/api/
# Swagger:   http://localhost:8080/api/docs  (solo si APP_ENV != production)
```

---

## 11. Hallazgos y deuda técnica

### 11.1 Correcciones aplicadas

| # | Área | Cambio |
|---|---|---|
| 1 | Login | `window.location.assign("home/dashboard.html")` reemplaza la llamada inválida a `href` y ya redirige tras autenticar |
| 2 | Panel | Valida la sesión con `GET /api/me`; si el access token expiró intenta `/api/refresh`; si falla, limpia y redirige al login |
| 3 | Logout | Llama a `POST /api/logout` con `keepalive`, limpia `sessionStorage` y navega a `../index.html` |
| 4 | Rate limit | Uvicorn recibe `forwarded_allow_ips=TRUSTED_PROXIES`; Apache reemplaza `X-Forwarded-For`; el límite se aplica por IP real |
| 5 | Configuración | `api` usa `env_file: .env`, por lo que `JWT_*_EXPIRE` y `CORS_*` llegan al contenedor (access token de 30 min verificado) |
| 6 | Esquema | Alembic con migración inicial; `migrate-db` se ejecuta al arrancar el contenedor |

Verificación realizada: `upgrade head` → `downgrade base` → `upgrade head`,
`alembic check` sin diferencias, login/`me`/logout contra el stack completo y
prueba de rate limiting desde dos IPs distintas (10 intentos + 429 por cada una).

### 11.2 Riesgos y limitaciones restantes

- **Rate limiting en memoria:** funciona por IP, pero no se comparte entre workers
  ni réplicas. Para escalar hace falta Redis u otro backend común.
- **Protección solo en cliente:** el HTML del panel es un archivo estático
  descargable; la validación evita mostrar datos, pero no sustituye la protección
  de los endpoints en el servidor.
- **Access token tras logout:** al ser JWT sin estado, sigue siendo válido hasta
  su expiración (comprobado: `/me` responde 200 tras cerrar sesión). El refresh
  token sí queda revocado.
- **Sin TLS**: el despliegue de Compose sirve HTTP en `:8080`.
- **Secretos en `.env`**: correcto para desarrollo, pero no hay gestor de secretos.
- **`createAdmin` no es automático** y no hay usuario sembrado; el primer acceso
  exige ejecutar el comando manualmente.
- **Sin autorización por roles**: `requireTipos` está disponible pero no se aplica.
- **Logout sin autenticación**: acepta cualquier refresh token en el body; es
  idempotente, pero conviene valorar si se exige el access token.
- **`doc/` está en `.gitignore`**: este documento no se versiona salvo que se
  ajuste el ignore o se añada con `git add -f`.

### 11.3 Calidad y documentación

- No hay tests unitarios, de integración ni E2E.
- No hay CI/CD.
- No hay linting/formateo configurado (Python o JS).
- El README termina abruptamente tras la sección de acceso y aún contiene
  discrepancias menores (Python 3.13 vs. venv local 3.14; CORS 8080 vs. 3000).

### 11.4 Mejoras sugeridas (priorizadas)

1. Integrar el panel con endpoints reales de servicios/dispositivos.
2. Implementar autorización por roles en los endpoints de administración.
3. Añadir tests (pytest + httpx/TestClient) y un pipeline de CI.
4. Usar un almacén compartido para el rate limiting si se escala a varios workers.
5. Añadir TLS y gestión de secretos para un despliegue real.
6. Completar el README y decidir si `doc/` debe versionarse.

---

## 12. Convenciones del código

- **Idioma:** identificadores, mensajes y comentarios en español; nombres de
  frameworks/APIs en inglés.
- **Python:** tipo hints en firmas, SQLAlchemy 2 con `Mapped`/`mapped_column`,
  dependencias de FastAPI con `Annotated`, imports ordenados por origen.
- **Estilo:** paréntesis en condiciones (`if (...)`), espaciado alrededor de `=`
  en argumentos con nombre, nombres en `camelCase` para funciones y `snake_case`
  para columnas.
- **Frontend:** JavaScript moderno con ES modules, `const`/`let`, funciones
  auxiliares pequeñas, sin dependencias externas.
- **Base de datos:** nombres de tabla en plural, columnas en `snake_case`,
  constraints con convención centralizada.
- **Configuración:** variables de entorno en mayúsculas, validadas al arrancar.

---

## 13. Glosario

| Término | Significado |
|---|---|
| **Access token** | JWT de corta duración que autoriza peticiones a la API |
| **Refresh token** | JWT de larga duración usado para obtener nuevos access tokens |
| **jti** | Identificador único del JWT; se persiste para poder revocarlo |
| **Rotación** | Emitir un refresh nuevo e invalidar el anterior en cada `/refresh` |
| **Detección de reutilización** | Si llega un refresh ya revocado, se revocan todos los del usuario |
| **Argon2** | Función de hash de contraseñas resistente a GPU |
| **Polimorfismo (SQLAlchemy)** | Herencia de modelos mapeada a varias tablas con discriminador |
| **Proxy inverso** | Apache recibe las peticiones y las reenvía a la API interna |
| **Rate limiting** | Límite de peticiones por ventana de tiempo |
| **Alembic** | Herramienta de migraciones versionadas para SQLAlchemy |
| **Migración** | Script que aplica un cambio de esquema de forma reproducible |
| **X-Forwarded-For** | Cabecera con la IP original del cliente a través de un proxy |

---

## Referencias

- `README.md` — guía de instalación y uso.
- `compose.yaml` — definición de servicios.
- `backend/alembic.ini` y `backend/migrations/` — migraciones de esquema.
- `examples/.env.example` — plantilla de configuración.
- `backend/core/security.py` — implementación de JWT y Argon2.
- `backend/api/login.py` — flujo completo de autenticación.
- `backend/db/template/` — modelo de datos.
