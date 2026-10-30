"use strict";

const $ = (s) => document.querySelector(s);
const API = "/api";
const LOGIN = "../index.html";

const state = {
  usuario: null,
  servicios: {
    chat: false,
    videoconferencia: false,
  },
};

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

async function validarSesion() {
  const res = await apiFetch("/me");
  if (!res || !res.ok) return false;
  state.usuario = await res.json();
  return true;
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

async function enviarHeartbeat() {
  try {
    await apiFetch("/heartbeat", { method: "POST" });
  } catch (e) { /* no-op */ }
}

async function comprobarServicios() {
  // Consultar usuarios de la sede para identificar mis servicios habilitados
  const idSede = state.usuario.id_sede;
  if (!idSede) {
    // Si no tiene sede fija pero es admin o asignado
    actualizarVistaServicios(true, true);
    return;
  }

  try {
    const res = await apiFetch(`/sedes/${idSede}/usuarios`);
    if (res && res.ok) {
      const lista = await res.json();
      const me = lista.find((u) => u.id_empleado === state.usuario.id);
      if (me && me.servicios) {
        const chat = me.servicios.find((s) => s.tipo_servicio === "chat");
        const video = me.servicios.find((s) => s.tipo_servicio === "videoconferencia");
        actualizarVistaServicios(chat ? chat.habilitado : false, video ? video.habilitado : false);
        return;
      }
    }
  } catch (e) {
    console.error("Error al consultar servicios del usuario:", e);
  }

  // Fallback si es administrador
  const esAdmin = state.usuario.tipo_admin === "admin-g";
  actualizarVistaServicios(esAdmin, esAdmin);
}

function actualizarVistaServicios(chatHab, videoHab) {
  state.servicios.chat = chatHab;
  state.servicios.videoconferencia = videoHab;

  const cardChat = $("#card-chat");
  const badgeChat = $("#badge-chat");
  const btnChat = $("#btn-entrar-chat");

  const cardVideo = $("#card-video");
  const badgeVideo = $("#badge-video");
  const btnVideo = $("#btn-entrar-video");

  if (chatHab) {
    cardChat.classList.remove("disabled");
    badgeChat.className = "pill up";
    badgeChat.textContent = "Habilitado";
    btnChat.disabled = false;
  } else {
    cardChat.classList.add("disabled");
    badgeChat.className = "pill down";
    badgeChat.textContent = "Deshabilitado por admin";
    btnChat.disabled = true;
  }

  if (videoHab) {
    cardVideo.classList.remove("disabled");
    badgeVideo.className = "pill up";
    badgeVideo.textContent = "Habilitado";
    btnVideo.disabled = false;
  } else {
    cardVideo.classList.add("disabled");
    badgeVideo.className = "pill down";
    badgeVideo.textContent = "Deshabilitado por admin";
    btnVideo.disabled = true;
  }
}

/* Modal Cambiar Contraseña */
function abrirModalCambiarPass() {
  const modal = $("#modal-cambiar-pass");
  const msg = $("#msg-cambiar-pass");
  const form = $("#form-cambiar-pass");
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
    const input = $("#pass-actual");
    if (input) input.focus();
  }, 50);
}

function cerrarModalCambiarPass() {
  const modal = $("#modal-cambiar-pass");
  if (!modal) return;
  modal.setAttribute("hidden", "");
  modal.style.display = "none";
}

async function cambiarPassword(e) {
  e.preventDefault();
  const actual = $("#pass-actual").value;
  const nueva = $("#pass-nueva").value;
  const confirmar = $("#pass-confirmar").value;
  const msg = $("#msg-cambiar-pass");
  const submitBtn = $("#btn-submit-pass");

  if (!actual || !nueva || !confirmar) {
    msg.className = "form-msg error";
    msg.textContent = "Todos los campos de contraseña son requeridos.";
    msg.hidden = false;
    msg.style.display = "block";
    return;
  }

  if (nueva.length < 8) {
    msg.className = "form-msg error";
    msg.textContent = "La nueva contraseña debe tener al menos 8 caracteres.";
    msg.hidden = false;
    msg.style.display = "block";
    return;
  }

  if (nueva !== confirmar) {
    msg.className = "form-msg error";
    msg.textContent = "La confirmación de la contraseña no coincide.";
    msg.hidden = false;
    msg.style.display = "block";
    return;
  }

  submitBtn.disabled = true;
  submitBtn.textContent = "Actualizando…";
  msg.hidden = true;
  msg.style.display = "none";

  try {
    const respuesta = await apiFetch("/me/password", {
      method: "POST",
      body: JSON.stringify({ contrasena_actual: actual, contrasena_nueva: nueva }),
    });

    if (respuesta && respuesta.ok) {
      msg.className = "form-msg success";
      msg.textContent = "¡Contraseña actualizada exitosamente!";
      msg.hidden = false;
      msg.style.display = "block";
      setTimeout(() => {
        cerrarModalCambiarPass();
      }, 1200);
    } else {
      const err = await (respuesta ? respuesta.json().catch(() => ({})) : {});
      msg.className = "form-msg error";
      msg.textContent = err.detail || "Error al cambiar contraseña.";
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
    submitBtn.textContent = "Actualizar contraseña";
  }
}

/* Eventos */
$("#logout").addEventListener("click", cerrarSesion);
$("#btn-copiar-uid").addEventListener("click", () => {
  const uid = $("#user-uid").textContent;
  if (navigator.clipboard) {
    navigator.clipboard.writeText(uid).then(() => {
      $("#btn-copiar-uid").textContent = "✅ ¡Copiado!";
      setTimeout(() => { $("#btn-copiar-uid").textContent = "📋 Copiar"; }, 2000);
    });
  }
});

$("#btn-entrar-chat").addEventListener("click", () => {
  window.location.assign("chat.html");
});

$("#btn-entrar-video").addEventListener("click", () => {
  window.location.assign("videocall.html");
});

const btnCambiarPass = $("#btn-cambiar-pass");
if (btnCambiarPass) btnCambiarPass.addEventListener("click", abrirModalCambiarPass);
const btnCerrarPass = $("#btn-cerrar-modal-pass");
if (btnCerrarPass) btnCerrarPass.addEventListener("click", cerrarModalCambiarPass);
const btnCancPass = $("#btn-cancelar-pass");
if (btnCancPass) btnCancPass.addEventListener("click", cerrarModalCambiarPass);
const formPass = $("#form-cambiar-pass");
if (formPass) formPass.addEventListener("submit", cambiarPassword);

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") cerrarModalCambiarPass();
});
const modalPass = $("#modal-cambiar-pass");
if (modalPass) {
  modalPass.addEventListener("click", (e) => {
    if (e.target === modalPass) cerrarModalCambiarPass();
  });
}

/* Tema */
const root = document.documentElement;
try { const g = localStorage.getItem("cfs-theme"); if (g) root.dataset.theme = g; } catch (e) {}
$("#theme").addEventListener("click", () => {
  const oscuro = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = oscuro ? "light" : "dark";
  try { localStorage.setItem("cfs-theme", root.dataset.theme); } catch (e) {}
});

/* ---- Arranque ---- */
async function iniciar() {
  if (!(await validarSesion())) {
    limpiarSesion();
    irALogin();
    return;
  }

  const u = state.usuario;
  $("#user-name").textContent = u.nombre || u.usuario;
  $("#user-saludo").textContent = `Hola, ${u.nombre || u.usuario}`;
  $("#user-role").textContent = u.rol || "CLIENTE";
  $("#user-uid").textContent = u.uid_publico || "Sin UID";

  if (u.sede_nombre) {
    $("#user-sede-tag").textContent = u.sede_nombre;
    $("#user-sede-lead").textContent = `Servicios de red conectados en ${u.sede_nombre}`;
  } else {
    $("#user-sede-tag").textContent = "Sede Principal";
  }

  $("#user-badge").hidden = false;
  $("#panel").hidden = false;

  await comprobarServicios();
  setInterval(comprobarServicios, 2000);

  enviarHeartbeat();
  setInterval(enviarHeartbeat, 30000);
}

iniciar();
