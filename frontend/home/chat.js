"use strict";

const $ = (s) => document.querySelector(s);
const API = "/api";
const LOGIN = "../index.html";

const state = {
  usuario: null,
  contactos: [],
  contactoActivo: null,
  mensajes: [],
  filtroContactos: "",
  pollingInterval: null,
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

function esc(t) {
  const d = document.createElement("div");
  d.textContent = t;
  return d.innerHTML;
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

/* ---- Contactos ---- */

async function cargarContactos() {
  try {
    const res = await apiFetch("/contactos");
    if (!res || !res.ok) return;
    state.contactos = await res.json();
    renderContactos();

    // Actualizar datos del contacto activo si está seleccionado
    if (state.contactoActivo) {
      const actualizado = state.contactos.find((c) => c.id_empleado === state.contactoActivo.id_empleado);
      if (actualizado) {
        state.contactoActivo = actualizado;
        renderHeaderConversacion();
      }
    }
  } catch (e) {
    console.error("Error al cargar contactos:", e);
  }
}

function renderContactos() {
  const list = $("#contacts-list");
  const empty = $("#empty-contacts");
  const t = (state.filtroContactos || "").toLowerCase();

  const filtrados = state.contactos.filter((c) =>
    (c.nombre + " " + (c.usuario || "") + " " + c.uid_publico).toLowerCase().includes(t)
  );

  if (filtrados.length === 0) {
    list.innerHTML = "";
    empty.hidden = false;
    empty.textContent = state.contactos.length > 0
      ? "Ningún contacto coincide con la búsqueda."
      : "No tienes contactos en tu sede todavía. Agrega uno con su UID único.";
    return;
  }

  empty.hidden = true;
  list.innerHTML = filtrados.map((c) => {
    const esActivo = state.contactoActivo && state.contactoActivo.id_empleado === c.id_empleado;
    const dotClass = c.en_linea ? "online" : "offline";
    const formalBadge = !c.registrado_formalmente
      ? `<span class="contact-badge-formal">No formalizado</span>`
      : "";

    return `
      <div class="contact-item ${esActivo ? "active" : ""}" data-id="${c.id_empleado}" tabindex="0">
        <div class="contact-avatar">
          👤
          <span class="status-dot ${dotClass}" title="${c.en_linea ? "En línea" : "Desconectado"}"></span>
        </div>
        <div class="contact-info">
          <div class="contact-name">${esc(c.nombre)} ${formalBadge}</div>
          <div class="contact-sub">${esc(c.sede_nombre || "Sede")} · ${esc(c.uid_publico.substring(0, 8))}…</div>
        </div>
      </div>
    `;
  }).join("");

  list.querySelectorAll(".contact-item").forEach((item) => {
    item.addEventListener("click", () => {
      const idEmp = parseInt(item.dataset.id, 10);
      const contacto = state.contactos.find((c) => c.id_empleado === idEmp);
      if (contacto) seleccionarContacto(contacto);
    });
  });
}

function seleccionarContacto(contacto) {
  state.contactoActivo = contacto;
  renderContactos();
  renderHeaderConversacion();

  $("#chat-placeholder").hidden = true;
  $("#chat-conversation").hidden = false;

  cargarMensajes();
  if (state.pollingInterval) clearInterval(state.pollingInterval);
  state.pollingInterval = setInterval(cargarMensajes, 2000);

  setTimeout(() => {
    const input = $("#input-mensaje");
    if (input) input.focus();
  }, 50);
}

function renderHeaderConversacion() {
  const c = state.contactoActivo;
  if (!c) return;

  $("#conv-name").textContent = c.nombre;
  $("#conv-sede-tag").textContent = c.sede_nombre || "Sede";
  $("#conv-uid-tag").textContent = `UID: ${c.uid_publico}`;

  const statusPill = $("#conv-status-pill");
  if (c.registrado_formalmente) {
    if (c.en_linea) {
      statusPill.className = "pill up";
      statusPill.textContent = "En línea";
    } else {
      statusPill.className = "pill down";
      statusPill.textContent = "Desconectado";
    }
    $("#formalizar-banner").hidden = true;
    $("#btn-iniciar-videollamada").disabled = false;
  } else {
    statusPill.className = "pill warn";
    statusPill.textContent = "Pendiente formalizar";
    $("#formalizar-banner").hidden = false;
    $("#btn-iniciar-videollamada").disabled = true;
  }
}

async function formalizarContactoActivo() {
  if (!state.contactoActivo) return;
  const relId = state.contactoActivo.id_contacto_rel;
  const btn = $("#btn-formalizar-contacto");
  btn.disabled = true;

  try {
    const res = await apiFetch(`/contactos/${relId}/registrar`, { method: "POST" });
    if (res && res.ok) {
      await cargarContactos();
    } else {
      alert("No se pudo registrar formalmente el contacto.");
    }
  } catch (e) {
    console.error("Error al formalizar:", e);
  } finally {
    btn.disabled = false;
  }
}

/* ---- Mensajes ---- */

async function cargarMensajes() {
  if (!state.contactoActivo) return;

  try {
    const res = await apiFetch(`/chat/mensajes?destinatario_id=${state.contactoActivo.id_empleado}`);
    if (!res || !res.ok) return;
    const datos = await res.json();
    const habiaNuevos = datos.length !== state.mensajes.length;
    state.mensajes = datos;
    renderMensajes(habiaNuevos);
  } catch (e) {
    console.error("Error al cargar mensajes:", e);
  }
}

function renderMensajes(autoScroll = false) {
  const container = $("#chat-messages");
  if (!container) return;

  if (state.mensajes.length === 0) {
    container.innerHTML = `<p class="empty" style="margin:auto">No hay mensajes previos en esta conversación. Envía el primer mensaje seguro.</p>`;
    return;
  }

  container.innerHTML = state.mensajes.map((m) => {
    const clase = m.es_mio ? "mine" : "theirs";
    const fecha = new Date(m.creado_en);
    const hora = fecha.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

    return `
      <div class="msg-bubble ${clase}">
        <div class="msg-text">${esc(m.contenido)}</div>
        <div class="msg-meta">
          <span>${hora}</span>
          ${m.es_mio ? (m.leido ? "<span>✓✓</span>" : "<span>✓</span>") : ""}
        </div>
      </div>
    `;
  }).join("");

  if (autoScroll) {
    container.scrollTop = container.scrollHeight;
  }
}

async function enviarMensaje(e) {
  e.preventDefault();
  if (!state.contactoActivo) return;

  const input = $("#input-mensaje");
  const texto = input.value.trim();
  if (!texto) return;

  input.value = "";
  const btnEnviar = $("#btn-enviar-msg");
  btnEnviar.disabled = true;

  try {
    const res = await apiFetch("/chat/mensajes", {
      method: "POST",
      body: JSON.stringify({
        destinatario_id: state.contactoActivo.id_empleado,
        contenido: texto,
      }),
    });

    if (res && res.status === 201) {
      await cargarMensajes();
      const container = $("#chat-messages");
      if (container) container.scrollTop = container.scrollHeight;
    } else {
      const err = await (res ? res.json().catch(() => ({})) : {});
      alert(err.detail || "Error al enviar mensaje. Verifica que ambos tengan el servicio habilitado.");
    }
  } catch (err) {
    alert("Error de conexión al enviar mensaje.");
  } finally {
    btnEnviar.disabled = false;
    input.focus();
  }
}

/* Modal Agregar por UID */

function abrirModalAgregarUid() {
  const modal = $("#modal-agregar-contacto");
  const msg = $("#msg-agregar-uid");
  const form = $("#form-agregar-uid");
  if (form) form.reset();
  if (msg) {
    msg.hidden = true;
    msg.style.display = "none";
  }
  if (modal) {
    modal.removeAttribute("hidden");
    modal.style.display = "grid";
  }
  setTimeout(() => {
    const input = $("#input-uid");
    if (input) input.focus();
  }, 50);
}

function cerrarModalAgregarUid() {
  const modal = $("#modal-agregar-contacto");
  if (!modal) return;
  modal.setAttribute("hidden", "");
  modal.style.display = "none";
}

async function guardarContactoUid(e) {
  e.preventDefault();
  const uid = $("#input-uid").value.trim();
  const alias = $("#input-alias").value.trim();
  const msg = $("#msg-agregar-uid");
  const btn = $("#btn-submit-uid");

  if (!uid) {
    msg.className = "form-msg error";
    msg.textContent = "Por favor ingresa el UID único del usuario.";
    msg.hidden = false;
    msg.style.display = "block";
    return;
  }

  btn.disabled = true;
  btn.textContent = "Buscando…";
  msg.hidden = true;
  msg.style.display = "none";

  try {
    const res = await apiFetch("/contactos", {
      method: "POST",
      body: JSON.stringify({ uid_publico: uid, alias: alias || null }),
    });

    if (res && res.status === 201) {
      const nuevo = await res.json();
      msg.className = "form-msg success";
      msg.textContent = "¡Contacto agregado exitosamente!";
      msg.hidden = false;
      msg.style.display = "block";
      await cargarContactos();
      const c = state.contactos.find((x) => x.id_empleado === nuevo.id_empleado);
      if (c) seleccionarContacto(c);
      setTimeout(() => { cerrarModalAgregarUid(); }, 600);
    } else {
      const err = await (res ? res.json().catch(() => ({})) : {});
      msg.className = "form-msg error";
      msg.textContent = err.detail || "No se pudo agregar el contacto. Asegúrate de que pertenezca a tu sede.";
      msg.hidden = false;
      msg.style.display = "block";
    }
  } catch (err) {
    msg.className = "form-msg error";
    msg.textContent = "Error al conectar con el servidor.";
    msg.hidden = false;
    msg.style.display = "block";
  } finally {
    btn.disabled = false;
    btn.textContent = "Agregar contacto";
  }
}

/* Eventos */
$("#logout").addEventListener("click", cerrarSesion);
$("#btn-volver").addEventListener("click", () => {
  if (state.usuario && state.usuario.tipo_admin === "usuario") {
    window.location.assign("usuario.html");
  } else {
    window.location.assign("index.html");
  }
});

$("#form-chat").addEventListener("submit", enviarMensaje);
$("#q-contactos").addEventListener("input", (e) => {
  state.filtroContactos = e.target.value;
  renderContactos();
});

$("#btn-modal-agregar-uid").addEventListener("click", abrirModalAgregarUid);
$("#btn-cerrar-modal-uid").addEventListener("click", cerrarModalAgregarUid);
$("#btn-cancelar-uid").addEventListener("click", cerrarModalAgregarUid);
$("#form-agregar-uid").addEventListener("submit", guardarContactoUid);
$("#btn-formalizar-contacto").addEventListener("click", formalizarContactoActivo);

$("#btn-iniciar-videollamada").addEventListener("click", () => {
  if (!state.contactoActivo) return;
  window.location.assign(`videocall.html?contacto_id=${state.contactoActivo.id_empleado}`);
});

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") cerrarModalAgregarUid();
});
const modalUid = $("#modal-agregar-contacto");
if (modalUid) {
  modalUid.addEventListener("click", (e) => {
    if (e.target === modalUid) cerrarModalAgregarUid();
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
  $("#user-role").textContent = u.tipo_admin === "admin-g" ? "ADMIN-G" : (u.tipo_admin === "admin-s" ? "ADMIN-S" : "CLIENTE");
  $("#user-badge").hidden = false;
  $("#chat-app").hidden = false;

  await cargarContactos();
  setInterval(cargarContactos, 10000);

  enviarHeartbeat();
  setInterval(enviarHeartbeat, 30000);
}

iniciar();
