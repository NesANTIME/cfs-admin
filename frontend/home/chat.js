"use strict";

const $ = (s) => document.querySelector(s);
const API = "/api";
const LOGIN = "../index.html";

const state = {
  usuario: null,
  contactos: [],
  contactoActivo: null,
  mensajes: [],
  firmaMensajes: null,
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
      } else {
        // El contacto fue eliminado o rechazado desde el otro extremo.
        state.contactoActivo = null;
        state.mensajes = [];
        state.firmaMensajes = null;
        if (state.pollingInterval) clearInterval(state.pollingInterval);
        $("#chat-conversation").hidden = true;
        $("#chat-placeholder").hidden = false;
        actualizarComposer();
      }
    }
  } catch (e) {
    console.error("Error al cargar contactos:", e);
  }
}

function renderContactos() {
  const list = $("#contacts-list");
  const t = (state.filtroContactos || "").toLowerCase();

  const filtrados = state.contactos.filter((c) =>
    ((c.nombre || "") + " " + (c.usuario || "") + " " + (c.uid_publico || "")).toLowerCase().includes(t)
  );

  if (filtrados.length === 0) {
    const mensaje = state.contactos.length > 0
      ? "Ningún contacto coincide con la búsqueda."
      : "No tienes contactos en tu sede todavía. Agrega uno con su Username o UID.";
    list.innerHTML = `<p class="empty">${esc(mensaje)}</p>`;
    return;
  }

  list.innerHTML = filtrados.map((c) => {
    const esActivo = state.contactoActivo && state.contactoActivo.id_empleado === c.id_empleado;
    const dotClass = c.en_linea ? "online" : "offline";
    const formalBadge = !c.registrado_formalmente
      ? `<span class="contact-badge-formal">Solicitud pendiente</span>`
      : "";
    const uidCorto = c.uid_publico ? `${c.uid_publico.substring(0, 8)}…` : "—";

    return `
      <div class="contact-item ${esActivo ? "active" : ""}" data-id="${c.id_empleado}" tabindex="0">
        <div class="contact-avatar">
          👤
          <span class="status-dot ${dotClass}" title="${c.en_linea ? "En línea" : "Desconectado"}"></span>
        </div>
        <div class="contact-info">
          <div class="contact-name">${esc(c.nombre)} ${formalBadge}</div>
          <div class="contact-sub">${esc(c.sede_nombre || "Sede")} · ${esc(uidCorto)}</div>
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
  state.mensajes = [];
  state.firmaMensajes = null;
  renderContactos();
  renderHeaderConversacion();

  $("#chat-placeholder").hidden = true;
  $("#chat-conversation").hidden = false;

  const contenedorMensajes = $("#chat-messages");
  if (contenedorMensajes) {
    contenedorMensajes.innerHTML = `<p class="empty" style="margin:auto">Cargando mensajes…</p>`;
  }

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
  $("#conv-uid-tag").textContent = `UID: ${c.uid_publico || "—"}`;

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
    const tieneVideo = Array.isArray(c.servicios) && c.servicios.includes("videoconferencia");
    const btnVideo = $("#btn-iniciar-videollamada");
    btnVideo.disabled = !tieneVideo;
    btnVideo.title = tieneVideo
      ? "Iniciar videollamada"
      : "Este contacto no tiene el servicio de videollamada habilitado";
  } else {
    statusPill.className = "pill warn";
    statusPill.textContent = "Solicitud pendiente";
    $("#formalizar-banner").hidden = false;
    $("#btn-iniciar-videollamada").disabled = true;
  }

  actualizarComposer();
}

function actualizarComposer() {
  const habilitado = Boolean(state.contactoActivo && state.contactoActivo.registrado_formalmente);
  const input = $("#input-mensaje");
  const btnEnviar = $("#btn-enviar-msg");
  const btnAdjuntar = $("#btn-adjuntar-img");

  if (input) {
    input.disabled = !habilitado;
    input.placeholder = habilitado
      ? "Escribe un mensaje seguro…"
      : "Acepta la solicitud para habilitar el chat…";
  }
  if (btnEnviar) btnEnviar.disabled = !habilitado;
  if (btnAdjuntar) btnAdjuntar.disabled = !habilitado;
}

async function aceptarSolicitudContacto() {
  if (!state.contactoActivo) return;
  const relId = state.contactoActivo.id_contacto_rel;
  const btn = $("#btn-aceptar-solicitud");
  if (btn) btn.disabled = true;

  try {
    const res = await apiFetch(`/contactos/${relId}/aceptar`, { method: "POST" });
    if (res && res.ok) {
      await cargarContactos();
      const c = state.contactos.find((x) => x.id_contacto_rel === relId);
      if (c) seleccionarContacto(c);
    } else {
      const err = await (res ? res.json().catch(() => ({})) : {});
      alert(err.detail || "No se pudo formalizar el contacto.");
    }
  } catch (e) {
    console.error("Error al formalizar:", e);
    alert("Error de conexión al formalizar el contacto.");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function rechazarSolicitudContacto() {
  if (!state.contactoActivo) return;
  if (!confirm(`¿Deseas rechazar o eliminar a ${state.contactoActivo.nombre} de tus contactos?`)) return;
  const relId = state.contactoActivo.id_contacto_rel;
  const btn = $("#btn-rechazar-solicitud");
  if (btn) btn.disabled = true;

  try {
    const res = await apiFetch(`/contactos/${relId}`, { method: "DELETE" });
    if (res && res.ok) {
      state.contactoActivo = null;
      state.mensajes = [];
      state.firmaMensajes = null;
      if (state.pollingInterval) clearInterval(state.pollingInterval);
      $("#chat-conversation").hidden = true;
      $("#chat-placeholder").hidden = false;
      actualizarComposer();
      await cargarContactos();
    } else {
      alert("No se pudo eliminar el contacto.");
    }
  } catch (e) {
    console.error("Error al rechazar contacto:", e);
  } finally {
    if (btn) btn.disabled = false;
  }
}

/* ---- Mensajes ---- */

async function cargarMensajes() {
  if (!state.contactoActivo) return;

  try {
    const res = await apiFetch(`/chat/mensajes?destinatario_id=${state.contactoActivo.id_empleado}`);
    if (!res || !res.ok) {
      // Mientras la solicitud siga pendiente no hay conversación que mostrar.
      if (
        state.contactoActivo &&
        !state.contactoActivo.registrado_formalmente &&
        state.firmaMensajes !== ""
      ) {
        state.mensajes = [];
        state.firmaMensajes = "";
        renderMensajes();
      }
      return;
    }
    const datos = await res.json();
    const firma = datos.map((m) => `${m.id}:${m.leido ? 1 : 0}`).join("|");
    if (state.firmaMensajes !== null && firma === state.firmaMensajes) return;

    const habiaNuevos = datos.length !== state.mensajes.length;
    state.mensajes = datos;
    state.firmaMensajes = firma;
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

  const estabaCercaDelFondo =
    container.scrollHeight - container.scrollTop - container.clientHeight < 90;

  container.innerHTML = state.mensajes.map((m) => {
    const clase = m.es_mio ? "mine" : "theirs";
    const fecha = new Date(m.creado_en);
    const hora = isNaN(fecha) ? "" : fecha.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

    const contenidoHtml = m.tipo === "imagen"
      ? `<img src="${m.contenido}" class="chat-img-thumb" alt="Imagen enviada" onclick="window.open('${m.contenido}', '_blank')" title="Clic para ampliar">`
      : `<div class="msg-text">${esc(m.contenido)}</div>`;

    return `
      <div class="msg-bubble ${clase}">
        ${contenidoHtml}
        <div class="msg-meta">
          <span>${hora}</span>
          ${m.es_mio ? (m.leido ? "<span>✓✓</span>" : "<span>✓</span>") : ""}
        </div>
      </div>
    `;
  }).join("");

  if (autoScroll || estabaCercaDelFondo) {
    container.scrollTop = container.scrollHeight;
  }
}

async function enviarMensaje(e) {
  e.preventDefault();
  if (!state.contactoActivo) return;
  if (!state.contactoActivo.registrado_formalmente) {
    alert("Acepta la solicitud de chat antes de enviar mensajes.");
    return;
  }

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
        tipo: "texto",
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
    actualizarComposer();
    input.focus();
  }
}

function configurarAdjuntosImagen() {
  const btnAdjuntar = $("#btn-adjuntar-img");
  const inputImg = $("#input-chat-img");
  if (!btnAdjuntar || !inputImg) return;

  btnAdjuntar.addEventListener("click", () => {
    if (!state.contactoActivo) {
      alert("Selecciona un contacto primero para enviar imágenes.");
      return;
    }
    if (!state.contactoActivo.registrado_formalmente) {
      alert("Acepta la solicitud de chat antes de enviar imágenes.");
      return;
    }
    inputImg.click();
  });

  inputImg.addEventListener("change", async (e) => {
    const file = e.target.files?.[0];
    if (!file || !state.contactoActivo) return;
    if (!state.contactoActivo.registrado_formalmente) {
      alert("Acepta la solicitud de chat antes de enviar imágenes.");
      inputImg.value = "";
      return;
    }

    if (file.size > 2.5 * 1024 * 1024) {
      alert("La imagen seleccionada supera el límite máximo permitido (2.5 MB).");
      inputImg.value = "";
      return;
    }

    btnAdjuntar.disabled = true;
    const lector = new FileReader();
    lector.onload = async () => {
      const base64Data = lector.result;
      try {
        const res = await apiFetch("/chat/mensajes", {
          method: "POST",
          body: JSON.stringify({
            destinatario_id: state.contactoActivo.id_empleado,
            contenido: base64Data,
            tipo: "imagen",
          }),
        });

        if (res && res.status === 201) {
          await cargarMensajes();
          const container = $("#chat-messages");
          if (container) container.scrollTop = container.scrollHeight;
        } else {
          const err = await (res ? res.json().catch(() => ({})) : {});
          alert(err.detail || "Error al enviar la imagen.");
        }
      } catch (err) {
        alert("Error de conexión al enviar la imagen.");
      } finally {
        actualizarComposer();
        inputImg.value = "";
      }
    };
    lector.readAsDataURL(file);
  });
}

/* Modal Agregar por Username o UID */

function abrirModalAgregarUid() {
  const modal = $("#modal-agregar-contacto");
  const msg = $("#msg-agregar-uid");
  const form = $("#form-agregar-uid");
  const dropdown = $("#autocomplete-dropdown");
  if (dropdown) dropdown.hidden = true;
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
  clearTimeout(queryDebounce);
  queryDebounce = null;
  const modal = $("#modal-agregar-contacto");
  const dropdown = $("#autocomplete-dropdown");
  if (dropdown) dropdown.hidden = true;
  const list = $("#autocomplete-list");
  if (list) list.innerHTML = "";
  if (!modal) return;
  modal.setAttribute("hidden", "");
  modal.style.display = "none";
}

let queryDebounce = null;
function configurarAutocomplete() {
  const input = $("#input-uid");
  const dropdown = $("#autocomplete-dropdown");
  const list = $("#autocomplete-list");
  if (!input || !dropdown || !list) return;

  input.addEventListener("input", (e) => {
    clearTimeout(queryDebounce);
    const val = e.target.value.trim();

    const esUUID = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(val);
    const pareceUIDParcial = !esUUID && /^[0-9a-fA-F]{8}-[0-9a-fA-F-]*$/.test(val);

    // Un UID solo se procesa cuando está completo; los prefijos no muestran sugerencias.
    if (!val || val.length < 2 || esUUID || pareceUIDParcial) {
      dropdown.hidden = true;
      list.innerHTML = "";
      return;
    }

    queryDebounce = setTimeout(async () => {
      try {
        const res = await apiFetch(`/contactos/buscar?q=${encodeURIComponent(val)}`);
        if (!res || !res.ok) {
          dropdown.hidden = true;
          return;
        }
        const usuarios = await res.json();
        if (!usuarios || usuarios.length === 0) {
          dropdown.hidden = true;
          list.innerHTML = "";
          return;
        }

        list.innerHTML = usuarios.map((u) => {
          const tag = u.ya_es_contacto
            ? `<span class="ac-tag is-contact">Ya es contacto</span>`
            : (u.solicitud_pendiente ? `<span class="ac-tag pending">Pendiente</span>` : `<span class="ac-tag">Disponible</span>`);
          return `
            <div class="autocomplete-item" data-username="${esc(u.usuario)}" data-uid="${esc(u.uid_publico)}">
              <div class="ac-user-info">
                <span class="ac-name">${esc(u.nombre)}</span>
                <span class="ac-user">@${esc(u.usuario)} · ${esc(u.uid_publico.substring(0, 8))}…</span>
              </div>
              ${tag}
            </div>
          `;
        }).join("");

        list.querySelectorAll(".autocomplete-item").forEach((item) => {
          item.addEventListener("mousedown", (ev) => {
            ev.preventDefault();
            input.value = item.dataset.username;
            dropdown.hidden = true;
          });
        });

        dropdown.hidden = false;
      } catch (e) {
        dropdown.hidden = true;
      }
    }, 220);
  });

  input.addEventListener("blur", () => {
    setTimeout(() => { dropdown.hidden = true; }, 200);
  });
}

async function guardarContactoUid(e) {
  e.preventDefault();
  const input = $("#input-uid");
  const identificador = input.value.trim();
  const alias = $("#input-alias").value.trim();
  const msg = $("#msg-agregar-uid");
  const btn = $("#btn-submit-uid");
  const dropdown = $("#autocomplete-dropdown");
  if (dropdown) dropdown.hidden = true;

  if (!identificador) {
    msg.className = "form-msg error";
    msg.textContent = "Por favor ingresa un nombre de usuario o UID único.";
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
      body: JSON.stringify({ identificador, alias: alias || null }),
    });

    if (res && (res.status === 201 || res.status === 200)) {
      const nuevo = await res.json();
      msg.className = "form-msg success";
      msg.textContent = "¡Contacto añadido exitosamente!";
      msg.hidden = false;
      msg.style.display = "block";
      await cargarContactos();
      const c = state.contactos.find((x) => x.id_empleado === nuevo.id_empleado);
      if (c) seleccionarContacto(c);
      setTimeout(() => { cerrarModalAgregarUid(); }, 600);
    } else {
      const err = await (res ? res.json().catch(() => ({})) : {});
      let errorMsg = "No se pudo agregar el contacto. Asegúrate de que pertenezca a tu sede.";
      if (err && err.detail) {
        if (typeof err.detail === "string") {
          errorMsg = err.detail;
        } else if (Array.isArray(err.detail) && err.detail[0]?.msg) {
          errorMsg = err.detail[0].msg;
        }
      }
      msg.className = "form-msg error";
      msg.textContent = errorMsg;
      msg.hidden = false;
      msg.style.display = "block";
    }
  } catch (err) {
    console.error("Error al añadir contacto:", err);
    msg.className = "form-msg error";
    msg.textContent = "Error al procesar la solicitud.";
    msg.hidden = false;
    msg.style.display = "block";
  } finally {
    btn.disabled = false;
    btn.textContent = "Añadir contacto";
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
const btnAceptarSolicitud = $("#btn-aceptar-solicitud");
if (btnAceptarSolicitud) btnAceptarSolicitud.addEventListener("click", aceptarSolicitudContacto);
const btnRechazarSolicitud = $("#btn-rechazar-solicitud");
if (btnRechazarSolicitud) btnRechazarSolicitud.addEventListener("click", rechazarSolicitudContacto);

$("#btn-iniciar-videollamada").addEventListener("click", async () => {
  const contacto = state.contactoActivo;
  if (!contacto) return;

  if (!contacto.registrado_formalmente) {
    alert("Debes formalizar el contacto antes de iniciar una videollamada.");
    return;
  }
  if (!Array.isArray(contacto.servicios) || !contacto.servicios.includes("videoconferencia")) {
    alert("Este contacto no tiene el servicio de videollamada habilitado.");
    return;
  }

  const boton = $("#btn-iniciar-videollamada");
  boton.disabled = true;
  try {
    const res = await apiFetch("/videoconferencia/salas", {
      method: "POST",
      body: JSON.stringify({ id_contacto: contacto.id_empleado }),
    });
    const datos = res ? await res.json().catch(() => ({})) : {};
    if (!res || !res.ok) {
      alert(datos.detail || "No se pudo iniciar la videollamada.");
      return;
    }
    window.location.assign(`videocall.html?codigo_sala=${encodeURIComponent(datos.codigo_sala)}`);
  } catch (e) {
    alert("Error de conexión al iniciar la videollamada.");
  } finally {
    boton.disabled = false;
  }
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
  if (u.tipo_admin === "usuario" && Array.isArray(u.servicios)) {
    const chatSvc = u.servicios.find((s) => s.tipo_servicio === "chat");
    if (chatSvc && !chatSvc.habilitado) {
      alert("Tu servicio de chat se encuentra deshabilitado por el administrador.");
      window.location.replace("usuario.html");
      return;
    }
  }
  $("#user-name").textContent = u.nombre || u.usuario;
  $("#user-role").textContent = u.tipo_admin === "admin-g" ? "ADMIN-G" : (u.tipo_admin === "admin-s" ? "ADMIN-S" : "CLIENTE");
  $("#user-badge").hidden = false;
  $("#chat-app").hidden = false;

  configurarAutocomplete();
  configurarAdjuntosImagen();

  await cargarContactos();
  setInterval(cargarContactos, 5000);

  enviarHeartbeat();
  setInterval(enviarHeartbeat, 30000);
}

iniciar();
