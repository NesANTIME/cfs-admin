# Guía de Implementación — CFS-Admin

> **Fecha:** 2026-10-30  
> **Rama base:** `development`  
> **Propósito:** Hoja de ruta detallada para completar la plataforma CFS-Admin según los requerimientos funcionales definidos.

---

## Estado de lo implementado (resumen rápido)

| Módulo | Estado |
|---|---|
| Login (admin-g) | ✅ Funcional |
| Tokens JWT (access + refresh + logout) | ✅ Funcional |
| Bloqueo por intentos fallidos | ✅ Funcional |
| Rate limiting por IP | ✅ Funcional |
| Heartbeat / presencia (`en_linea`) | ✅ Modelo + endpoint. Falta integración frontend |
| `GET /me` con `tipo_admin` | ✅ Funcional |
| Lista de sedes (panel admin) | ✅ Funcional (frontend + backend) |
| Crear sede (solo admin-g) | ✅ Funcional |
| Acceder a una sede (`dashboard.html?id_sede=`) | ✅ Funcional |
| Lista de usuarios con toggle de servicios | ✅ Backend completo. Frontend parcial (tabla sin acciones reales) |
| Cambiar contraseña (panel) | ❌ No existe |
| Crear usuarios/empleados desde la sede | ❌ No existe |
| Crear admin-s y asignarle sede | ❌ No existe |
| Servicio de Chat (intra-sede) | ❌ No implementado |
| Servicio de Videoconferencia | ❌ No implementado |
| Sistema de Contactos (lista + UID) | ❌ No implementado |
| Frontend: tabla de usuarios con acciones reales | ❌ Parcial (sin toggle funcional, sin crear usuario) |

---

## OBJETIVOS DE IMPLEMENTACIÓN

### OBJ-1 · Cambio seguro de contraseña en el panel

**Descripción:** El admin-g (y cualquier usuario con sesión activa) debe poder cambiar su propia contraseña desde el panel, en cualquier momento, sin necesidad de comandos manuales.

**Qué falta:**
- Backend: endpoint `POST /me/password` que reciba `contrasena_actual` y `contrasena_nueva`, verifique con Argon2, rehashee y guarde.
- Backend: schema Pydantic `ChangePasswordRequest`.
- Frontend: modal/sección "Cambiar contraseña" accesible desde el header del panel (`index.html` o `dashboard.html`).
- Frontend: lógica JS que llame al endpoint y muestre feedback.

**Archivos involucrados:**
- `backend/api/login.py` (añadir nuevo endpoint o crear `api/perfil.py`)
- `backend/config/request.py` (schema `ChangePasswordRequest`)
- `frontend/home/panel.js` (modal + llamada API)
- `frontend/home/index.html` (botón en header)

---

### OBJ-2 · Crear usuarios/empleados y admin-s desde la sede

**Descripción:** Un admin-g o admin-s debe poder crear usuarios (`usuario_sede`) y admins de sede (`tecnico` con `nivel_acceso < 5`) directamente desde la vista de una sede. El admin-g puede además crear otros admin-s y asignarlos a cualquier sede.

**Qué falta:**
- Backend: endpoint `POST /sedes/{id_sede}/usuarios` que cree `UsuarioSede` o `Tecnico` y los asigne a la sede.  
  - El admin-g puede crear tipo `tecnico` (admin-s) y asignarlo.  
  - El admin-s solo puede crear `usuario_sede` dentro de su sede.
- Backend: schema `UsuarioCreate` ya existe en `request.py`; falta la lógica de hashing y FK de sede.
- Backend: endpoint `DELETE /sedes/{id_sede}/usuarios/{id}` para desactivar/eliminar.
- Frontend (`dashboard.html`): botón "Crear usuario" en la sección "👥 Usuarios y Servicios", modal con formulario (nombre, usuario, contraseña, tipo).
- Frontend (`js.js`): funciones `abrirModalCrearUsuario()`, `guardarUsuario()`, `recargarUsuarios()`.

**Archivos involucrados:**
- `backend/api/` → nuevo archivo `usuarios.py` o extender `servicios_usuario.py`
- `backend/config/request.py` (ajustar/ampliar `UsuarioCreate`)
- `frontend/home/dashboard.html` (modal + botón)
- `frontend/home/js.js` (lógica)

> [!IMPORTANT]
> El admin-s **no** puede crear admin-g ni modificar sedes. La creación de admin-s es exclusiva del admin-g.

---

### OBJ-3 · Toggle funcional de servicios (videoconferencia / chat) en el frontend

**Descripción:** La tabla de usuarios en `dashboard.html` ya muestra columnas de Videoconf. y Chat, pero los toggles no tienen acción real. Deben llamar a los endpoints `/habilitar` y `/deshabilitar` ya existentes en el backend.

**Qué falta:**
- Frontend (`js.js`): función `toggleServicio(idEmpleado, idSede, tipoServicio, habilitar)` que llame `POST /sedes/{id}/usuarios/{id}/servicios/{tipo}/habilitar` o `/deshabilitar`.
- Frontend (`js.js`): renderizar los toggles como `<button>` o `<input type="checkbox">` con el estado correcto tomado del campo `habilitado` devuelto por `GET /sedes/{id}/usuarios`.
- Frontend (`js.js`): mostrar el estado `en_linea` real (del campo `en_linea` del empleado).

**Archivos involucrados:**
- `frontend/home/js.js` (sección renderUsuarios)
- `frontend/home/dashboard.html` (ajuste de tabla)
- `frontend/home/dashboard.css` (estilos toggle)

---

### OBJ-4 · Sistema de presencia real (online/offline)

**Descripción:** El sistema ya tiene `en_linea` y `ultima_vez_en_linea` en el modelo `Empleado` y el endpoint `POST /heartbeat`. Falta integrar el heartbeat en el frontend de los usuarios y mostrar el estado real en el panel de admin.

**Qué falta:**
- Frontend (usuario): llamar a `POST /api/heartbeat` cada 30 segundos mientras la sesión esté activa (para usuarios `usuario_sede`).
- Frontend (admin, `js.js`): leer el campo `en_linea` de la respuesta `GET /sedes/{id}/usuarios` y mostrarlo con el color correcto en la tabla.
- Backend (`app.py`): registrar el router de heartbeat (`from api.heartbeat import router as router_heartbeat`).
- Backend: añadir un scheduler o endpoint de limpieza para `limpiarPresencia()` (sugerido: llamarlo en lifespan o en un thread periódico ligero).

**Archivos involucrados:**
- `backend/core/app.py` (incluir router heartbeat)
- `frontend/home/js.js` (intervalo heartbeat en vistas de usuario)
- `frontend/home/dashboard.html` / `js.js` (indicador visual)

---

### OBJ-5 · Servicio de Chat intra-sede

**Descripción:** Los usuarios con el servicio "chat" habilitado pueden enviarse mensajes de texto solo con otros usuarios de la **misma sede**. El sistema debe permitir gestionar contactos y enviar/recibir mensajes en tiempo real o pseudo-real (polling).

**Sub-objetivos:**

#### 5a — Modelo de datos (Chat)
- Nueva tabla `mensajes_chat`: `id`, `id_remitente` (FK empleados), `id_destinatario` (FK empleados), `id_sede` (FK sedes), `contenido` (Text), `leido` (bool), `creado_en` (timestamp).
- Restricción: `id_remitente != id_destinatario`.
- Nueva migración Alembic.

#### 5b — Backend: endpoints de chat
| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/chat/mensajes?destinatario_id=X` | Obtiene conversación con un usuario |
| `POST` | `/chat/mensajes` | Envía un mensaje |
| `GET` | `/chat/mensajes/nuevos` | Mensajes no leídos (para polling) |
| `PATCH` | `/chat/mensajes/{id}/leer` | Marca mensaje como leído |

- Validar que remitente y destinatario estén en la misma sede.
- Validar que ambos tengan el servicio `chat` habilitado.

#### 5c — Backend: lista de contactos
- Nueva tabla `contactos`: `id`, `id_usuario` (FK empleados), `id_contacto` (FK empleados), `alias` (opcional), `registrado_formalmente` (bool).
- Endpoint `GET /contactos` → lista de contactos del usuario.
- Endpoint `POST /contactos` → añadir contacto por UID (usuario).
- Endpoint `PATCH /contactos/{id}/registrar` → el receptor formaliza el contacto (puede ver nombre, sede, estado).

#### 5d — Frontend: vista de chat (para usuarios)
- Nueva página `frontend/home/chat.html` (o modal flotante en dashboard de usuario).
- Panel izquierdo: lista de contactos con estado online.
- Panel derecho: conversación con historial de mensajes.
- Polling cada 5 segundos a `/chat/mensajes/nuevos`.
- Indicador de "sin leer".

**Archivos nuevos:**
- `backend/db/template/mensaje_chat.py`
- `backend/db/template/contacto.py`
- `backend/api/chat.py`
- `frontend/home/chat.html`
- `frontend/home/chat.css`
- `frontend/home/chat.js`
- Nueva migración en `backend/migrations/versions/`

> [!NOTE]
> El chat es **intra-sede**: un usuario no puede ver ni chatear con alguien de otra sede. Esta restricción debe validarse tanto en backend como en frontend.

---

### OBJ-6 · Servicio de Videoconferencia

**Descripción:** Los usuarios con el servicio "videoconferencia" habilitado pueden iniciar o unirse a videollamadas dentro de la misma sede. La implementación se basa en WebRTC (peer-to-peer) con señalización por WebSocket o polling.

**Sub-objetivos:**

#### 6a — Señalización WebRTC (Backend)
- Añadir soporte WebSocket a FastAPI: `pip install websockets` y usar `WebSocket` de FastAPI.
- Nuevo endpoint WebSocket `WS /ws/videoconferencia/{id_sede}`.
- El servidor actúa como relay de señalización: intercambia `offer`, `answer` y `ICE candidates` entre pares.
- Validar que ambos usuarios estén en la misma sede y tengan videoconferencia habilitada.

#### 6b — Modelo: salas de videoconferencia (opcional)
- Tabla `salas_videoconf`: `id`, `id_sede`, `id_iniciador`, `activa` (bool), `creada_en`.
- Endpoint `POST /videoconferencia/iniciar` → crea sala y devuelve `sala_id`.
- Endpoint `GET /videoconferencia/sala/{sala_id}` → estado y participantes.
- Endpoint `POST /videoconferencia/sala/{sala_id}/unirse`.
- Endpoint `POST /videoconferencia/sala/{sala_id}/salir`.

#### 6c — Frontend: vista de videoconferencia
- Nueva página `frontend/home/videocall.html`.
- Elemento `<video>` para stream local y remoto.
- Lógica WebRTC: `RTCPeerConnection`, `getUserMedia`, intercambio de SDP + ICE por WebSocket.
- Botones: silenciar micrófono, apagar cámara, colgar.
- La llamada puede iniciarse desde la lista de contactos del chat.

#### 6d — Integración con lista de contactos
- En la vista de contactos (OBJ-5d), añadir botón "📹 Videollamada" que redirija a `videocall.html?sala_id=X&contacto=Y`.

**Archivos nuevos:**
- `backend/api/videoconferencia.py`
- `backend/db/template/sala_videoconf.py` (opcional)
- `frontend/home/videocall.html`
- `frontend/home/videocall.css`
- `frontend/home/videocall.js`

> [!IMPORTANT]
> WebRTC requiere HTTPS en producción para acceder a `getUserMedia`. En el entorno de Compose actual (HTTP en `:8080`), funciona solo en `localhost`. Para deploy real, agregar TLS (objetivo de deuda técnica).

---

### OBJ-7 · Sistema de Contactos con UID único

**Descripción:** Cada usuario tiene un UID único que puede compartir para que otros le agreguen como contacto sin necesidad de registro formal. El receptor puede "formalizar" el contacto para revelar su nombre, sede y estado.

**Qué falta:**
- Backend: añadir columna `uid_publico` (UUID v4, único) a la tabla `empleados`.
  - Generado automáticamente al crear el usuario.
  - Visible en el perfil del usuario.
- Backend: endpoint `GET /usuarios/buscar?uid=XXXX` → devuelve solo `uid`, `estado_online` (si ya es contacto formalizado, devuelve además nombre y sede).
- Backend: lógica de formalización: cuando el receptor formaliza, el emisor puede ver nombre, sede y estado.
- Frontend: campo "Agregar contacto por UID" en la vista de contactos.
- Frontend: notificación al receptor cuando alguien intenta agregarlo.
- Frontend: botón "Aceptar / Formalizar contacto" en la lista de solicitudes pendientes.

**Archivos involucrados:**
- `backend/db/template/empleado.py` (nueva columna `uid_publico`)
- `backend/db/template/contacto.py` (tabla de contactos con campo `registrado_formalmente`)
- `backend/api/contactos.py` (nuevo)
- `frontend/home/chat.js` (lógica de búsqueda por UID)
- Nueva migración Alembic

---

### OBJ-8 · Vista de usuario (cliente): acceso a sus servicios

**Descripción:** Los usuarios de tipo `usuario_sede` deben poder iniciar sesión y acceder a sus propios servicios habilitados (chat y/o videoconferencia), sin acceso al panel de administración de sedes.

**Qué falta:**
- Frontend: lógica de redirección post-login basada en `tipo_admin` devuelto por `/me`:
  - `admin-g` o `admin-s` → `home/index.html` (panel de sedes).
  - `usuario` → `home/usuario.html` (vista de servicios del usuario).
- Nueva página `frontend/home/usuario.html`: muestra los servicios habilitados (acceso a chat, acceso a videollamada).
- Heartbeat automático activado desde esta vista.

**Archivos involucrados:**
- `frontend/js/index.js` (lógica de redirección post-login)
- `frontend/home/usuario.html` (nueva página)
- `frontend/home/usuario.css` (nueva hoja de estilos)
- `frontend/home/usuario.js` (nueva lógica JS)

---

## ORDEN DE IMPLEMENTACIÓN SUGERIDO

```
[OBJ-1] Cambio de contraseña          → Independiente, rápido, alta prioridad.
[OBJ-2] Crear usuarios desde la sede  → Desbloquea OBJ-3, OBJ-4, OBJ-5.
[OBJ-3] Toggle servicios en frontend  → Usa backend ya listo; solo frontend.
[OBJ-4] Presencia real (heartbeat)    → Mejora visual; fácil de integrar.
[OBJ-8] Vista de usuario (cliente)    → Define la UX base de los usuarios finales.
[OBJ-7] Sistema de contactos (UID)    → Cimientos para el chat.
[OBJ-5] Chat intra-sede               → Depende de OBJ-7 y OBJ-8.
[OBJ-6] Videoconferencia (WebRTC)     → Mayor complejidad; va al final.
```

---

## RESUMEN DE ARCHIVOS NUEVOS A CREAR

| Archivo | Propósito |
|---|---|
| `backend/api/perfil.py` | Cambio de contraseña (`/me/password`) |
| `backend/api/usuarios.py` | CRUD de usuarios por sede |
| `backend/api/chat.py` | Mensajes + contactos |
| `backend/api/videoconferencia.py` | Señalización WebRTC + salas |
| `backend/api/contactos.py` | Búsqueda por UID, formalización |
| `backend/db/template/mensaje_chat.py` | Modelo de mensajes |
| `backend/db/template/contacto.py` | Modelo de contactos |
| `backend/db/template/sala_videoconf.py` | Modelo de salas (opcional) |
| `backend/migrations/versions/<hash>_chat_contactos.py` | Migración: mensajes + contactos |
| `backend/migrations/versions/<hash>_uid_publico.py` | Migración: uid_publico en empleados |
| `frontend/home/usuario.html` | Vista del usuario final |
| `frontend/home/usuario.css` | Estilos vista usuario |
| `frontend/home/usuario.js` | Lógica vista usuario |
| `frontend/home/chat.html` | Vista de chat |
| `frontend/home/chat.css` | Estilos chat |
| `frontend/home/chat.js` | Lógica chat + polling |
| `frontend/home/videocall.html` | Vista de videollamada |
| `frontend/home/videocall.css` | Estilos videollamada |
| `frontend/home/videocall.js` | Lógica WebRTC |

---

## RESUMEN DE ARCHIVOS A MODIFICAR

| Archivo | Cambio |
|---|---|
| `backend/core/app.py` | Incluir routers: heartbeat, perfil, usuarios, chat, videoconferencia |
| `backend/config/request.py` | Añadir `ChangePasswordRequest`, ampliar `UsuarioCreate` |
| `backend/db/template/empleado.py` | Añadir columna `uid_publico` (UUID) |
| `backend/db/template/__init__.py` | Importar nuevos modelos |
| `frontend/js/index.js` | Redirección post-login según tipo de usuario |
| `frontend/home/js.js` | Toggle servicios real, heartbeat, mostrar `en_linea` |
| `frontend/home/dashboard.html` | Botón crear usuario, modal, mejoras tabla |
| `frontend/home/dashboard.css` | Estilos toggle, modal usuario |
| `frontend/home/panel.js` | Botón cambiar contraseña en header |
| `frontend/home/index.html` | Botón cambiar contraseña en header |

---

## DEUDA TÉCNICA PENDIENTE (no bloqueante)

| Ítem | Impacto |
|---|---|
| TLS / HTTPS | Necesario para WebRTC en producción y para seguridad real |
| Rate limiting compartido (Redis) | Necesario si se escala a múltiples workers |
| Revocar access token en logout | JWT sin estado; válido hasta expiración tras cerrar sesión |
| Tests (pytest + httpx) | No hay cobertura de tests automatizados |
| CI/CD | No hay pipeline de integración |
| Gestión de secretos | `.env` correcto en dev; necesita vault/secrets manager en prod |
| Linting / formateo | Sin configuración de ruff/black/eslint |
| README actualizado | Discrepancias menores de versiones y CORS |

---

## NOTAS DE ARQUITECTURA

### Sobre el Chat (polling vs WebSocket)
Para simplicidad educativa, el chat puede implementarse con **polling** (`setInterval` cada 5 s), que no requiere cambios en el stack. Si se quiere tiempo real, agregar un endpoint WebSocket en FastAPI es directo con `from fastapi import WebSocket`. El WebSocket también sirve como canal de señalización para WebRTC.

### Sobre el UID único
Se recomienda usar `uuid.uuid4()` en Python al momento de crear el empleado, y almacenarlo como `String(36)` o tipo `UUID` de PostgreSQL. Este UID es público (puede compartirse) pero no es la contraseña ni el token.

### Sobre la herencia polimórfica y los admin-s
El admin-s en el modelo actual es un `Tecnico` con `id_sede` asignado y `nivel_acceso < 5`. Al crear un admin-s, se debe:
1. Crear el `Empleado` base.
2. Crear el `Tecnico` con `id_sede` de la sede destino.
3. Asignar un rol con nombre `"administrador de sede"` o `"admin-s"` (o confiar solo en `nivel_acceso`).

La función `obtenerTipoAdmin()` en `deps.py` ya maneja ambas condiciones.
