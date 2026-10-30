"use strict";

const $ = (s) => document.querySelector(s);
const API = "/api";
const LOGIN = "../index.html";
const state = {
  usuario: null,
  sedes: [],
  filtroTexto: "",
};

/* ---- Sesión ---- */
function leerToken(clave) {
  try { return sessionStorage.getItem(clave); } catch (e) { return null; }
}

function guardarTokens(access, refresh) {
  try {
    sessionStorage.setItem("access_token", access);
    sessionStorage.setItem("refresh_token", refresh);
  } catch (e) { /* no-op */ }
}

function limpiarSesion() {
  try {
    sessionStorage.removeItem("access_token");
    sessionStorage.removeItem("refresh_token");
    sessionStorage.removeItem("sede_actual");
  } catch (e) { /* no-op */ }
}

function irALogin() {
  window.location.replace(LOGIN);
}

async function renovarSesion() {
  const refresh = leerToken("refresh_token");
  if (!refresh) return false;

  try {
    const respuesta = await fetch(`${API}/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
      cache: "no-store",
    });

    if (!respuesta.ok) return false;

    const datos = await respuesta.json();
    if (!datos.access_token || !datos.refresh_token) return false;

    guardarTokens(datos.access_token, datos.refresh_token);
    return true;
  } catch (e) {
    return false;
  }
}

async function validarSesion() {
  const access = leerToken("access_token");
  if (!access) return false;

  try {
    let respuesta = await fetch(`${API}/me`, {
      headers: { "Authorization": `Bearer ${access}`, "Accept": "application/json" },
      cache: "no-store",
    });

    if (respuesta.status === 401 && (await renovarSesion())) {
      const nuevoAccess = leerToken("access_token");
      respuesta = await fetch(`${API}/me`, {
        headers: { "Authorization": `Bearer ${nuevoAccess}`, "Accept": "application/json" },
        cache: "no-store",
      });
    }

    if (!respuesta.ok) return false;
    state.usuario = await respuesta.json();
    return true;
  } catch (e) {
    return false;
  }
}

function cerrarSesion() {
  const refresh = leerToken("refresh_token");
  if (refresh) {
    fetch(`${API}/logout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
      keepalive: true,
    }).catch(() => {});
  }
  limpiarSesion();
  irALogin();
}

async function apiFetch(endpoint, opciones = {}) {
  let access = leerToken("access_token");
  if (!access) return null;

  const headers = {
    "Authorization": `Bearer ${access}`,
    "Accept": "application/json",
    ...(opciones.headers || {}),
  };
  if (opciones.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  let respuesta = await fetch(`${API}${endpoint}`, {
    ...opciones,
    headers,
    cache: "no-store",
  });

  if (respuesta.status === 401 && (await renovarSesion())) {
    access = leerToken("access_token");
    headers["Authorization"] = `Bearer ${access}`;
    respuesta = await fetch(`${API}${endpoint}`, {
      ...opciones,
      headers,
      cache: "no-store",
    });
  }

  return respuesta;
}

function esc(t) {
  const d = document.createElement("div");
  d.textContent = t;
  return d.innerHTML;
}

/* ---- Gestión de Sedes ---- */
async function cargarSedes() {
  const btn = $("#refresh-sedes");
  if (btn) btn.disabled = true;

  try {
    const respuesta = await apiFetch("/sedes");
    if (!respuesta || !respuesta.ok) {
      return;
    }
    state.sedes = await respuesta.json();
    renderSedes();
  } catch (e) {
    console.error("Error al cargar sedes:", e);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function renderSedes() {
  const grid = $("#grid-sedes");
  const emptyBox = $("#empty-sedes-box");
  const emptyMsg = $("#empty-sedes-msg");
  const btnEmptyCrear = $("#btn-empty-crear-sede");
  const badgeCount = $("#badge-sedes-count");
  const esAdminG = state.usuario && state.usuario.tipo_admin === "admin-g";

  const t = (state.filtroTexto || "").toLowerCase();
  const filtradas = state.sedes.filter((s) =>
    (s.nombre + " " + s.ubicacion + " " + (s.descripcion || "")).toLowerCase().includes(t)
  );

  badgeCount.textContent = `${state.sedes.length} ${state.sedes.length === 1 ? "sede disponible" : "sedes disponibles"}`;

  // Si no hay sedes registradas en total:
  if (state.sedes.length === 0) {
    grid.innerHTML = "";
    grid.hidden = true;
    emptyBox.hidden = false;

    if (esAdminG) {
      emptyMsg.textContent = "Como Administrador General, debes registrar al menos una sede para comenzar a gestionar y monitorear sus dispositivos.";
      btnEmptyCrear.hidden = false;
    } else {
      emptyMsg.textContent = "No tienes ninguna sede asignada en este momento. Contacta a un Administrador General.";
      btnEmptyCrear.hidden = true;
    }
    return;
  }

  // Si hay sedes pero el filtro no encuentra nada:
  if (filtradas.length === 0 && t) {
    grid.innerHTML = "";
    grid.hidden = true;
    emptyBox.hidden = false;
    emptyMsg.textContent = "Ninguna sede coincide con el criterio de búsqueda.";
    btnEmptyCrear.hidden = true;
    return;
  }

  emptyBox.hidden = true;
  grid.hidden = false;

  grid.innerHTML = filtradas.map((s) => `
    <article class="sede-card card" data-id="${s.id_sede}" tabindex="0" role="button" aria-label="Abrir panel de ${esc(s.nombre)}">
      <div class="sede-card-header">
        <span class="sede-id-tag">ID #${s.id_sede}</span>
        <span class="pill up">Operativa</span>
      </div>
      <h2 class="sede-card-title">${esc(s.nombre)}</h2>
      <p class="sede-card-loc">📍 ${esc(s.ubicacion)}</p>
      <p class="sede-card-desc">${esc(s.descripcion || "Sede operativa registrada en CFS-Admin.")}</p>
      <div class="sede-card-footer">
        <span class="sede-footer-hint">Equipos & Monitoreo</span>
        <span class="btn-entrar">Ingresar al panel →</span>
      </div>
    </article>
  `).join("");

  // Evento de click para navegar al dashboard específico de la sede
  grid.querySelectorAll(".sede-card").forEach((card) => {
    const idSede = card.dataset.id;
    const abrir = () => {
      window.location.assign(`dashboard.html?id_sede=${encodeURIComponent(idSede)}`);
    };
    card.addEventListener("click", abrir);
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        abrir();
      }
    });
  });
}

/* Modal crear sede */
function abrirModalCrearSede() {
  const modal = $("#modal-crear-sede");
  const msg = $("#msg-crear-sede");
  const form = $("#form-sede");
  if (form) form.reset();
  if (msg) {
    msg.hidden = true;
    msg.style.display = "none";
    msg.className = "form-msg";
    msg.textContent = "";
  }
  if (modal) {
    modal.removeAttribute("hidden");
    modal.style.display = "grid";
  }
  setTimeout(() => {
    const input = $("#sede-nombre");
    if (input) input.focus();
  }, 50);
}

function cerrarModalCrearSede() {
  const modal = $("#modal-crear-sede");
  if (!modal) return;
  modal.setAttribute("hidden", "");
  modal.style.display = "none";
}

async function guardarSede(e) {
  e.preventDefault();
  const nombre = $("#sede-nombre").value.trim();
  const ubicacion = $("#sede-ubicacion").value.trim();
  const descripcion = $("#sede-descripcion").value.trim();
  const msg = $("#msg-crear-sede");
  const submitBtn = $("#btn-submit-sede");

  if (!nombre || !ubicacion || !descripcion) {
    msg.className = "form-msg error";
    msg.textContent = "Por favor ingresa el nombre, ubicación y una descripción.";
    msg.hidden = false;
    msg.style.display = "block";
    return;
  }

  submitBtn.disabled = true;
  submitBtn.textContent = "Guardando sede…";
  msg.hidden = true;
  msg.style.display = "none";

  try {
    const respuesta = await apiFetch("/sedes", {
      method: "POST",
      body: JSON.stringify({ nombre, ubicacion, descripcion }),
    });

    if (!respuesta) {
      throw new Error("No hubo respuesta del servidor.");
    }

    if (respuesta.status === 201) {
      msg.className = "form-msg success";
      msg.textContent = "¡Sede registrada exitosamente!";
      msg.hidden = false;
      msg.style.display = "block";
      await cargarSedes();
      setTimeout(() => {
        cerrarModalCrearSede();
      }, 500);
    } else {
      const errorData = await respuesta.json().catch(() => ({}));
      msg.className = "form-msg error";
      msg.textContent = errorData.detail || "No se pudo registrar la sede.";
      msg.hidden = false;
      msg.style.display = "block";
    }
  } catch (err) {
    msg.className = "form-msg error";
    msg.textContent = "Error al conectar con el servidor.";
    msg.hidden = false;
    msg.style.display = "block";
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Guardar sede";
  }
}

/* Tema claro / oscuro */
const root = document.documentElement;
try { const g = localStorage.getItem("cfs-theme"); if (g) root.dataset.theme = g; } catch (e) {}
$("#theme").addEventListener("click", () => {
  const oscuro = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = oscuro ? "light" : "dark";
  try { localStorage.setItem("cfs-theme", root.dataset.theme); } catch (e) {}
});

/* Eventos */
$("#logout").addEventListener("click", cerrarSesion);
$("#refresh-sedes").addEventListener("click", cargarSedes);
$("#btn-nueva-sede").addEventListener("click", abrirModalCrearSede);
$("#btn-empty-crear-sede").addEventListener("click", abrirModalCrearSede);
$("#btn-cerrar-modal").addEventListener("click", cerrarModalCrearSede);
$("#btn-cancelar-sede").addEventListener("click", cerrarModalCrearSede);
$("#form-sede").addEventListener("submit", guardarSede);
$("#q-sedes").addEventListener("input", (e) => {
  state.filtroTexto = e.target.value;
  renderSedes();
});

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    cerrarModalCrearSede();
  }
});
$("#modal-crear-sede").addEventListener("click", (e) => {
  if (e.target === $("#modal-crear-sede")) {
    cerrarModalCrearSede();
  }
});

/* ---- Arranque ---- */
async function iniciar() {
  if (!(await validarSesion())) {
    limpiarSesion();
    irALogin();
    return;
  }

  const u = state.usuario;
  const userBadge = $("#user-badge");
  const userName = $("#user-name");
  const userRole = $("#user-role");

  userName.textContent = u.nombre || u.usuario;

  if (u.tipo_admin === "admin-g") {
    userRole.textContent = "ADMIN-G";
    userRole.className = "user-tag admin-g-tag";
    $("#btn-nueva-sede").hidden = false;
    $("#panel-sub").textContent = "Administrador General · Control y supervisión de todas las sedes";
  } else if (u.tipo_admin === "admin-s") {
    userRole.textContent = "ADMIN-S";
    userRole.className = "user-tag admin-s-tag";
    $("#btn-nueva-sede").hidden = true;
    $("#panel-sub").textContent = "Administrador de Sede · Acceso exclusivo a tu sede asignada";
  } else {
    userRole.textContent = u.rol || "USUARIO";
    userRole.className = "user-tag";
    $("#btn-nueva-sede").hidden = true;
    $("#panel-sub").textContent = "Sedes autorizadas para consulta";
  }

  userBadge.hidden = false;
  $("#panel").hidden = false;

  await cargarSedes();
}

iniciar();
