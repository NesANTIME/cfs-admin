"use strict";

const $ = (s) => document.querySelector(s);
const API = "/api";
const LOGIN = "../index.html";
const PATRON_UUID = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

const state = {
  usuario: null,
  tab: "recibidas",
  invitaciones: [],
  contactos: [],
  modo: "contacto",
  pollTimer: null,
  countdownTimer: null,
  cargando: false,
  modoDemo: false,
  pendientesRecibidas: 0,
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

function mostrarToast(mensaje, tipo = "") {
  const el = $("#toast");
  if (!el) return;
  el.textContent = mensaje;
  el.className = `toast ${tipo}`.trim();
  el.hidden = false;
  clearTimeout(mostrarToast._timer);
  mostrarToast._timer = setTimeout(() => { el.hidden = true; }, 4000);
}

function inicial(nombre) {
  const limpio = (nombre || "").trim();
  return limpio ? limpio.charAt(0).toUpperCase() : "?";
}

function escaparHtml(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));
}

function actualizarBadge() {
  const badge = $("#badge-recibidas");
  if (badge) badge.textContent = String(state.pendientesRecibidas);
  document.title = state.pendientesRecibidas > 0
    ? `(${state.pendientesRecibidas}) Videollamadas · CFS-Admin`
    : "CFS-Admin · Videollamadas";
}

function etiquetaEstado(estado) {
  return {
    pendiente: "Pendiente",
    aceptada: "Aceptada",
    rechazada: "Rechazada",
    cancelada: "Cancelada",
    expirada: "Expirada",
    finalizada: "Finalizada",
  }[estado] || estado;
}

function claseEstado(estado) {
  if (estado === "aceptada") return "ok";
  if (["rechazada", "cancelada", "expirada", "finalizada"].includes(estado)) return "off";
  return "";
}

function restanteTexto(expiraEn) {
  if (!expiraEn) return "";
  const ms = new Date(expiraEn).getTime() - Date.now();
  if (Number.isNaN(ms)) return "";
  if (ms <= 0) return "Expirada";
  const total = Math.floor(ms / 1000);
  const min = Math.floor(total / 60);
  const seg = String(total % 60).padStart(2, "0");
  return `Expira en ${min}:${seg}`;
}

function renderInvitaciones() {
  const contenedor = $("#lista-invitaciones");
  if (!contenedor) return;

  if (!state.invitaciones.length) {
    contenedor.innerHTML = state.tab === "recibidas"
      ? '<p class="empty">No tienes videollamadas pendientes.</p>'
      : '<p class="empty">No has enviado invitaciones recientes.</p>';
    return;
  }

  contenedor.innerHTML = state.invitaciones.map((inv) => {
    const recibida = state.tab === "recibidas";
    const nombre = recibida
      ? (inv.nombre_invitador || inv.usuario_invitador || "Usuario")
      : (inv.nombre_invitado || (inv.estado === "pendiente" ? "Usuario de otra sede" : "Usuario"));
    const meta = recibida
      ? [inv.usuario_invitador ? `@${inv.usuario_invitador}` : null, inv.sede_invitador || "Sede"]
          .filter(Boolean).join(" · ")
      : [
          inv.usuario_invitado ? `@${inv.usuario_invitado}` : null,
          inv.estado === "pendiente" && !inv.nombre_invitado ? "Datos ocultos hasta aceptar" : null,
        ].filter(Boolean).join(" · ");
    const uid = recibida ? inv.uid_invitador : inv.uid_invitado;
    const estadoClase = claseEstado(inv.estado);

    let acciones = "";
    if (recibida && inv.estado === "pendiente") {
      acciones = `
        <button class="btn btn-accept" type="button" data-action="aceptar" data-id="${inv.id}"
          ${inv.puede_aceptar ? "" : "disabled title=\"No puedes aceptar esta invitación ahora\""}>✅ Aceptar</button>
        <button class="ghost btn-reject" type="button" data-action="rechazar" data-id="${inv.id}">❌ Rechazar</button>`;
    } else if (!recibida && inv.estado === "pendiente") {
      acciones = `<button class="ghost btn-reject" type="button" data-action="cancelar" data-codigo="${inv.codigo_sala}">Cancelar invitación</button>`;
    } else if (!recibida && inv.estado === "aceptada") {
      acciones = `<button class="btn" type="button" data-action="entrar" data-codigo="${inv.codigo_sala}">Entrar a la llamada</button>`;
    }

    return `
      <article class="invitacion-card ${inv.estado}">
        <div class="inv-top">
          <div class="inv-avatar">${escaparHtml(inicial(nombre))}</div>
          <div class="inv-id">
            <p class="inv-nombre">${escaparHtml(nombre)}</p>
            <p class="inv-meta">${escaparHtml(meta || "Videollamada")}</p>
          </div>
        </div>
        <span class="inv-estado ${estadoClase}">${escaparHtml(etiquetaEstado(inv.estado))}</span>
        ${uid ? `<p class="inv-uid" title="UID">UID: ${escaparHtml(uid)}</p>` : ""}
        <p class="inv-tiempo" data-expira="${escaparHtml(inv.expira_en || "")}">${escaparHtml(restanteTexto(inv.expira_en))}</p>
        ${acciones ? `<div class="inv-acciones">${acciones}</div>` : ""}
      </article>`;
  }).join("");
}

function actualizarCuentaRegresiva() {
  let expirada = false;
  document.querySelectorAll("[data-expira]").forEach((el) => {
    const valor = el.getAttribute("data-expira");
    if (!valor) return;
    const texto = restanteTexto(valor);
    el.textContent = texto;
    if (texto === "Expirada") expirada = true;
  });
  if (expirada && state.tab === "recibidas" && !state.cargando) {
    cargarInvitaciones(true);
  }
}

async function actualizarContadorRecibidas() {
  try {
    const res = await apiFetch("/videoconferencia/invitaciones?tipo=recibidas&estado=pendiente");
    if (!res || !res.ok) return;
    const pendientes = await res.json();
    state.pendientesRecibidas = Array.isArray(pendientes) ? pendientes.length : 0;
    actualizarBadge();
  } catch (e) { /* no-op */ }
}

async function cargarInvitaciones(silencioso = false) {
  if (state.cargando) return;
  state.cargando = true;
  try {
    const estado = state.tab === "recibidas" ? "pendiente" : "todas";
    const res = await apiFetch(`/videoconferencia/invitaciones?tipo=${state.tab}&estado=${estado}`);
    if (!res || !res.ok) {
      if (!silencioso) mostrarToast("No se pudieron cargar las invitaciones.", "error");
      return;
    }
    state.invitaciones = await res.json();
    renderInvitaciones();
    if (state.tab === "recibidas") {
      state.pendientesRecibidas = state.invitaciones.filter((i) => i.estado === "pendiente").length;
      actualizarBadge();
    } else {
      await actualizarContadorRecibidas();
    }
  } catch (e) {
    if (!silencioso) mostrarToast("Error de conexión al cargar invitaciones.", "error");
  } finally {
    state.cargando = false;
  }
}

async function cargarContactos() {
  const select = $("#select-contacto");
  if (!select) return;
  try {
    const res = await apiFetch("/contactos");
    if (!res || !res.ok) throw new Error("contactos");
    const todos = await res.json();
    state.contactos = todos.filter(
      (c) => c.registrado_formalmente && Array.isArray(c.servicios) && c.servicios.includes("videoconferencia")
    );
    if (!state.contactos.length) {
      select.innerHTML = '<option value="">No hay contactos con videollamada habilitada</option>';
      return;
    }
    select.innerHTML = '<option value="">Selecciona un contacto…</option>' + state.contactos
      .map((c) => `<option value="${c.id_empleado}">${c.nombre} (@${c.usuario}) · ${c.sede_nombre || "Sede"}</option>`)
      .join("");
  } catch (e) {
    select.innerHTML = '<option value="">No se pudieron cargar los contactos</option>';
  }
}

function abrirModal() {
  const modal = $("#modal-nueva");
  if (!modal) return;
  $("#modal-msg").hidden = true;
  $("#form-nueva-videollamada").reset();
  seleccionarModo("contacto");
  modal.hidden = false;
  cargarContactos();
}

function cerrarModal() {
  const modal = $("#modal-nueva");
  if (modal) modal.hidden = true;
}

function seleccionarModo(modo) {
  state.modo = modo;
  const esContacto = modo === "contacto";
  $("#modo-contacto").classList.toggle("on", esContacto);
  $("#modo-uid").classList.toggle("on", !esContacto);
  $("#modo-contacto").setAttribute("aria-selected", String(esContacto));
  $("#modo-uid").setAttribute("aria-selected", String(!esContacto));
  $("#panel-contacto").hidden = !esContacto;
  $("#panel-uid").hidden = esContacto;
}

async function crearInvitacion(evento) {
  evento.preventDefault();
  const msg = $("#modal-msg");
  const boton = $("#btn-crear-invitacion");
  msg.hidden = true;

  let cuerpo;
  if (state.modo === "contacto") {
    const id = parseInt($("#select-contacto").value, 10);
    if (!id) {
      msg.textContent = "Selecciona un contacto.";
      msg.className = "form-msg error";
      msg.hidden = false;
      return;
    }
    cuerpo = { id_contacto: id };
  } else {
    const uid = $("#input-uid").value.trim();
    if (!PATRON_UUID.test(uid)) {
      msg.textContent = "El UID debe tener 36 caracteres y el formato completo.";
      msg.className = "form-msg error";
      msg.hidden = false;
      return;
    }
    cuerpo = { identificador: uid };
  }

  boton.disabled = true;
  boton.textContent = "Enviando…";
  try {
    const res = await apiFetch("/videoconferencia/salas", {
      method: "POST",
      body: JSON.stringify(cuerpo),
    });
    const datos = res ? await res.json().catch(() => ({})) : {};
    if (!res || !res.ok) {
      msg.textContent = datos.detail || "No se pudo enviar la invitación.";
      msg.className = "form-msg error";
      msg.hidden = false;
      return;
    }
    window.location.assign(`videocall.html?codigo_sala=${encodeURIComponent(datos.codigo_sala)}`);
  } catch (e) {
    msg.textContent = "Error de conexión al enviar la invitación.";
    msg.className = "form-msg error";
    msg.hidden = false;
  } finally {
    boton.disabled = false;
    boton.textContent = "Enviar invitación";
  }
}

async function aceptarInvitacion(id) {
  const res = await apiFetch(`/videoconferencia/invitaciones/${id}/aceptar`, { method: "POST" });
  const datos = res ? await res.json().catch(() => ({})) : {};
  if (!res || !res.ok) {
    mostrarToast(datos.detail || "No se pudo aceptar la invitación.", "error");
    cargarInvitaciones(true);
    return;
  }
  window.location.assign(`videocall.html?codigo_sala=${encodeURIComponent(datos.codigo_sala)}`);
}

async function rechazarInvitacion(id) {
  const res = await apiFetch(`/videoconferencia/invitaciones/${id}/rechazar`, { method: "POST" });
  if (!res || !res.ok) {
    const datos = res ? await res.json().catch(() => ({})) : {};
    mostrarToast(datos.detail || "No se pudo rechazar la invitación.", "error");
    return;
  }
  mostrarToast("Invitación rechazada.", "ok");
  cargarInvitaciones(true);
}

async function cancelarInvitacion(codigo) {
  const res = await apiFetch(`/videoconferencia/salas/${encodeURIComponent(codigo)}/cancelar`, { method: "POST" });
  if (!res || !res.ok) {
    const datos = res ? await res.json().catch(() => ({})) : {};
    mostrarToast(datos.detail || "No se pudo cancelar la invitación.", "error");
    return;
  }
  mostrarToast("Invitación cancelada.", "ok");
  cargarInvitaciones(true);
}

function manejarAcciones(evento) {
  const boton = evento.target.closest("[data-action]");
  if (!boton) return;
  const accion = boton.dataset.action;
  if (accion === "aceptar") aceptarInvitacion(parseInt(boton.dataset.id, 10));
  else if (accion === "rechazar") rechazarInvitacion(parseInt(boton.dataset.id, 10));
  else if (accion === "cancelar") cancelarInvitacion(boton.dataset.codigo);
  else if (accion === "entrar") {
    window.location.assign(`videocall.html?codigo_sala=${encodeURIComponent(boton.dataset.codigo)}`);
  }
}

function iniciarPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = setInterval(() => {
    if (!document.hidden) cargarInvitaciones(true);
  }, 5000);
}

function iniciarCuentaRegresiva() {
  if (state.countdownTimer) clearInterval(state.countdownTimer);
  state.countdownTimer = setInterval(actualizarCuentaRegresiva, 1000);
}

function configurarEventos() {
  $("#btn-volver").addEventListener("click", () => {
    window.location.assign(state.usuario?.tipo_admin === "usuario" ? "usuario.html" : "index.html");
  });
  $("#btn-nueva-videollamada").addEventListener("click", abrirModal);
  $("#btn-cerrar-modal").addEventListener("click", cerrarModal);
  $("#btn-cancelar-nueva").addEventListener("click", cerrarModal);
  $("#modo-contacto").addEventListener("click", () => seleccionarModo("contacto"));
  $("#modo-uid").addEventListener("click", () => seleccionarModo("uid"));
  $("#form-nueva-videollamada").addEventListener("submit", crearInvitacion);
  $("#lista-invitaciones").addEventListener("click", manejarAcciones);

  $("#tab-recibidas").addEventListener("click", () => cambiarTab("recibidas"));
  $("#tab-enviadas").addEventListener("click", () => cambiarTab("enviadas"));

  $("#modal-nueva").addEventListener("click", (e) => {
    if (e.target === $("#modal-nueva")) cerrarModal();
  });
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") cerrarModal();
  });

  $("#logout").addEventListener("click", async () => {
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
  });

  const root = document.documentElement;
  try { const g = localStorage.getItem("cfs-theme"); if (g) root.dataset.theme = g; } catch (e) {}
  $("#theme").addEventListener("click", () => {
    const oscuro = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = oscuro ? "light" : "dark";
    try { localStorage.setItem("cfs-theme", root.dataset.theme); } catch (e) {}
  });

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) cargarInvitaciones(true);
  });
}

function cambiarTab(tab) {
  state.tab = tab;
  $("#tab-recibidas").classList.toggle("on", tab === "recibidas");
  $("#tab-enviadas").classList.toggle("on", tab === "enviadas");
  $("#tab-recibidas").setAttribute("aria-selected", String(tab === "recibidas"));
  $("#tab-enviadas").setAttribute("aria-selected", String(tab === "enviadas"));
  $("#lista-invitaciones").innerHTML = '<p class="empty">Cargando invitaciones…</p>';
  cargarInvitaciones();
}

function actualizarServicioVideo() {
  const u = state.usuario;
  const servicios = Array.isArray(u?.servicios) ? u.servicios : [];
  const video = servicios.find((s) => s.tipo_servicio === "videoconferencia");
  const habilitado = video ? video.habilitado : u?.tipo_admin === "admin-g";
  if (!habilitado) {
    $("#aviso-servicio").hidden = false;
    $("#btn-nueva-videollamada").disabled = true;
  }
}

async function iniciar() {
  if (!(await validarSesion())) {
    limpiarSesion();
    irALogin();
    return;
  }

  const u = state.usuario;
  $("#inbox-app").hidden = false;
  $("#user-badge").hidden = false;
  $("#user-name").textContent = u.nombre || u.usuario;
  $("#user-role").textContent = u.tipo_admin === "admin-g" ? "ADMIN-G" : (u.tipo_admin === "admin-s" ? "ADMIN-S" : "CLIENTE");

  actualizarServicioVideo();
  configurarEventos();
  await cargarInvitaciones();
  iniciarPolling();
  iniciarCuentaRegresiva();
}

iniciar();
