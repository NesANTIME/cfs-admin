# Documentación del Frontend: CFS-Admin

> **Módulo:** Interfaz de Usuario y Autenticación del Cliente  
> **Tecnologías:** HTML5, CSS3, JavaScript (ES Modules)  

---

## 1. Descripción General

El frontend de **CFS-Admin** proporciona la interfaz web del sistema, actualmente centrada en la pantalla de inicio de sesión y la integración con la API REST del backend.

---

## 2. Estructura de Archivos

- **[`index.html`](file:///home/nesantime/Universidad/cfs-admin/frontend/index.html):** Estructura del formulario de autenticación con campos para usuario, contraseña, botón para mostrar/ocultar contraseña y mensajes de estado dinámicos.
- **[`index.css`](file:///home/nesantime/Universidad/cfs-admin/frontend/index.css):** Estilos visuales del formulario, soporte para modo oscuro/claro y estados de error/éxito.
- **[`js/cons.js`](file:///home/nesantime/Universidad/cfs-admin/frontend/js/cons.js):** Configuración de la URL base del servidor backend (`urlserver`).
- **[`js/index.js`](file:///home/nesantime/Universidad/cfs-admin/frontend/js/index.js):**
  - Validación de campos en tiempo real.
  - Petición HTTP asíncrona (`fetch`) al endpoint `POST ${urlserver}/login`.
  - Almacenamiento seguro del token en `sessionStorage`.
  - Redirección al panel de administración tras una autenticación exitosa.

---

## 3. Despliegue y Ejecución Local

Para servir el frontend localmente, puedes usar cualquier servidor web estático:

```bash
# Con Python
python3 -m http.server 3000 --directory frontend

# O con herramientas como Live Server / Nginx
```
