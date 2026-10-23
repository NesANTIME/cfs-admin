
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

    window.location.assign("home/dashboard.html");

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
