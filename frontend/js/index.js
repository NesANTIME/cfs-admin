
"use strict";

const urlserver = "/api";

const $ = (id) => document.getElementById(id);

const form = $("form");
const user = $("user");
const pass = $("pass");
const btn = $("btn");
const status = $("status");
const toggleBtn = $("toggle");

if (!form || !user || !pass || !btn || !status || !toggleBtn) {
  throw new Error(
    "No se encontraron todos los elementos del formulario."
  );
}

toggleBtn.addEventListener("click", function () {
  const show = pass.type === "password";

  pass.type = show ? "text" : "password";
  this.textContent = show ? "Ocultar" : "Mostrar";
  this.setAttribute("aria-pressed", String(show));
});

const check = (fid, mid, hasError, errorMessage) => {
  const field = $(fid);
  const message = $(mid);

  field.classList.toggle("err", hasError);
  message.textContent = hasError ? errorMessage : "";

  return !hasError;
};

/**
 * Redirige al panel correspondiente según el perfil del usuario.
 */
function redirigirSegunRol(perfil) {
  if (perfil && perfil.tipo_admin === "usuario") {
    window.location.replace("home/usuario.html");
  } else {
    window.location.replace("home/index.html");
  }
}

/**
 * Comprueba si ya existe una sesión autenticada activa y redirige automáticamente al dashboard.
 */
async function verificarSesionExistente() {
  const access = sessionStorage.getItem("access_token") || localStorage.getItem("access_token");
  const refresh = sessionStorage.getItem("refresh_token") || localStorage.getItem("refresh_token");

  if (!access && !refresh) return;

  status.className = "msg";
  status.textContent = "Comprobando sesión activa…";
  btn.disabled = true;
  btn.textContent = "Comprobando…";

  try {
    let token = access;
    let respMe = null;

    if (token) {
      respMe = await fetch(`${urlserver}/me`, {
        headers: {
          "Authorization": `Bearer ${token}`,
          "Accept": "application/json",
        },
        cache: "no-store",
      });
    }

    // Si access_token expiró pero hay refresh_token, intentar renovarlo
    if ((!respMe || respMe.status === 401) && refresh) {
      const respRefresh = await fetch(`${urlserver}/refresh`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
        },
        body: JSON.stringify({ refresh_token: refresh }),
        cache: "no-store",
      });

      if (respRefresh.ok) {
        const datos = await respRefresh.json();
        if (datos.access_token && datos.refresh_token) {
          sessionStorage.setItem("access_token", datos.access_token);
          sessionStorage.setItem("refresh_token", datos.refresh_token);
          token = datos.access_token;
          respMe = await fetch(`${urlserver}/me`, {
            headers: {
              "Authorization": `Bearer ${token}`,
              "Accept": "application/json",
            },
            cache: "no-store",
          });
        }
      }
    }

    if (respMe && respMe.ok) {
      const perfil = await respMe.json();
      status.className = "msg ok";
      status.textContent = "Sesión activa detectada. Redirigiendo…";
      btn.textContent = "Redirigiendo…";
      redirigirSegunRol(perfil);
      return;
    }
  } catch (err) {
    console.warn("No se pudo validar sesión existente:", err);
  }

  // Token inválido o expirado sin posibilidad de renovar: limpiar almacenamiento
  sessionStorage.removeItem("access_token");
  sessionStorage.removeItem("refresh_token");
  sessionStorage.removeItem("sede_actual");
  try {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
  } catch (e) {}

  status.className = "msg";
  status.textContent = "";
  btn.disabled = false;
  btn.textContent = "Ingresar";
}

// Ejecutar comprobación automática inmediatamente al cargar el script
verificarSesionExistente();

async function iniciarSesion(username, password) {
  const respuesta = await fetch(`${urlserver}/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json",
    },
    body: JSON.stringify({ username, password }),
  });

  const texto = await respuesta.text();
  let resultado = {};

  try {
    resultado = texto ? JSON.parse(texto) : {};
  } catch {
    resultado = {
      detail: texto || "Respuesta no válida del servidor.",
    };
  }

  if (!respuesta.ok) {
    throw new Error(
      resultado.detail ||
      resultado.mensaje ||
      "Error al iniciar sesión."
    );
  }

  return resultado;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();

  status.className = "msg";
  status.textContent = "";

  const isUserValid = check(
    "f-user",
    "m-user",
    !user.value.trim(),
    "Escribe tu usuario."
  );

  const isPassValid = check(
    "f-pass",
    "m-pass",
    !pass.value,
    "Escribe tu contraseña."
  );

  if (!isUserValid) {
    user.focus();
    return;
  }

  if (!isPassValid) {
    pass.focus();
    return;
  }

  btn.disabled = true;
  btn.textContent = "Ingresando…";

  try {
    const resultado = await iniciarSesion(
      user.value.trim(),
      pass.value
    );

    if (!resultado.access_token || !resultado.refresh_token) {
      throw new Error(
        "El servidor no devolvió los tokens esperados."
      );
    }

    sessionStorage.setItem(
      "access_token",
      resultado.access_token
    );

    sessionStorage.setItem(
      "refresh_token",
      resultado.refresh_token
    );

    status.className = "msg ok";
    status.textContent = "Sesión iniciada correctamente.";

    // Consultar tipo de usuario para redirigir al panel correspondiente
    try {
      const respMe = await fetch(`${urlserver}/me`, {
        headers: {
          "Authorization": `Bearer ${resultado.access_token}`,
          "Accept": "application/json",
        },
        cache: "no-store",
      });
      if (respMe.ok) {
        const perfil = await respMe.json();
        redirigirSegunRol(perfil);
        return;
      }
    } catch (e) {
      // Si falla la consulta a /me, proceder por defecto
    }

    window.location.replace("home/index.html");


  } catch (error) {
    console.error("Error en el inicio de sesión:", error);

    status.className = "msg error";
    status.textContent =
      error instanceof TypeError
        ? "No se pudo conectar con el servidor."
        : error.message || "No se pudo iniciar sesión.";

  } finally {
    btn.disabled = false;
    btn.textContent = "Ingresar";
  }
});
