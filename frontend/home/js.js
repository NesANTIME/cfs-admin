"use strict";

const $ = (s) => document.querySelector(s);
const API = "/api";
const LOGIN = "../index.html";
const PANEL_SEDES = "index.html";

const state = {
  usuario: null,
  idSede: null,
  sedeActual: null,
  dispositivos: [],
  filtroDisp: "",
  servicios: [],
  filtroServicios: "all",
  textoServicios: "",
  usuarios: [],
  filtroUsuarios: "",
};

const ETIQUETA_DISP = {
  en_linea: "En línea",
  fuera_de_linea: "Fuera de línea",
  desconocido: "Desconocido",
};

const ETIQUETA_SERV = {
  up: "En línea",
  warn: "Alerta",
  down: "Caído",
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

/* ---- Carga de datos de la sede específica ---- */
async function cargarSedeEspecifica() {
  const btn = $("#refresh-sede");
  if (btn) btn.disabled = true;

  try {
    const respuesta = await apiFetch(`/sedes/${encodeURIComponent(state.idSede)}`);
    if (!respuesta || !respuesta.ok) {
      if (respuesta && respuesta.status === 403) {
        alert("No tienes permisos para acceder a esta sede.");
      } else {
        alert("La sede solicitada no existe o no fue encontrada.");
      }
      window.location.replace(PANEL_SEDES);
      return;
    }

    const sede = await respuesta.json();
    state.sedeActual = sede;
    state.dispositivos = sede.dispositivos || [];

    // Actualizar encabezado del banner de la sede
    document.title = `CFS-Admin · ${sede.nombre}`;
    $("#sede-id-tag").textContent = `Sede #${sede.id_sede}`;
    $("#sede-nombre-titulo").textContent = sede.nombre;
    $("#sede-ubicacion-lead").textContent = `📍 ${sede.ubicacion}`;
    $("#sede-descripcion-texto").textContent = sede.descripcion || "Sin descripción registrada.";

    renderDispositivos();
  } catch (e) {
    console.error("Error al cargar detalle de sede:", e);
  } finally {
    if (btn) btn.disabled = false;
  }
}

/* ---- Render de Dispositivos de la Sede ---- */
function renderDispositivos() {
  const tbody = $("#rows-dispositivos");
  const empty = $("#empty-dispositivos");
  const badgeCount = $("#badge-disp-count");

  const t = (state.filtroDisp || "").toLowerCase();
  const filtrados = state.dispositivos.filter((d) =>
    (d.nombre + " " + d.direccion_ip + " " + d.mac + " " + d.tipo).toLowerCase().includes(t)
  );

  const nTotal = state.dispositivos.length;
  const nUp = state.dispositivos.filter((d) => d.estado === "en_linea").length;
  const nWarn = state.dispositivos.filter((d) => d.estado === "desconocido").length;
  const nDown = state.dispositivos.filter((d) => d.estado === "fuera_de_linea").length;

  $("#k-disp-total").textContent = nTotal;
  $("#k-disp-up").textContent = nUp;
  $("#k-disp-warn").textContent = nWarn;
  $("#k-disp-down").textContent = nDown;

  badgeCount.textContent = `${nTotal} ${nTotal === 1 ? "dispositivo" : "dispositivos"}`;

  if (filtrados.length === 0) {
    tbody.innerHTML = "";
    empty.hidden = false;
    if (nTotal > 0 && t) {
      empty.textContent = "Ningún dispositivo coincide con el término de búsqueda.";
    } else {
      empty.textContent = "No hay dispositivos de red registrados en esta sede todavía.";
    }
    return;
  }

  empty.hidden = true;
  tbody.innerHTML = filtrados.map((d) => {
    const pillClass = d.estado === "en_linea" ? "up" : d.estado === "desconocido" ? "warn" : "down";
    const etiqueta = ETIQUETA_DISP[d.estado] || d.estado;
    return `
      <tr>
        <td class="num">#${d.id_dispositivo}</td>
        <td class="cli">${esc(d.nombre)}</td>
        <td><span class="chip" style="cursor:default;height:26px;font-size:.78rem">${esc(d.tipo)}</span></td>
        <td class="mono">${esc(d.direccion_ip)}</td>
        <td class="mono">${esc(d.mac)}</td>
        <td><span class="pill ${pillClass}">${etiqueta}</span></td>
      </tr>
    `;
  }).join("");
}



/* ---- Usuarios de la Sede y control de servicios ---- */

async function cargarUsuariosSede() {
  if (!state.idSede) return;
  try {
    const respuesta = await apiFetch(`/sedes/${encodeURIComponent(state.idSede)}/usuarios`);
    if (!respuesta || !respuesta.ok) return;
    state.usuarios = await respuesta.json();
    renderUsuarios();
  } catch (e) {
    console.error("Error al cargar usuarios de la sede:", e);
  }
}

function _obtenerServicio(usuario, tipoServicio) {
  if (!usuario.servicios) return null;
  return usuario.servicios.find((s) => s.tipo_servicio === tipoServicio) || null;
}

function _esBtnDeshabilitado(usuario) {
  // Si el usuario actual es admin-s, no puede gestionar tecnico_jefe
  const tipoAdmin = state.usuario ? state.usuario.tipo_admin : null;
  if (tipoAdmin === "admin-s" && usuario.tipo === "tecnico_jefe") return true;
  return false;
}

function renderUsuarios() {
  const tbody = $("#rows-usuarios");
  const empty = $("#empty-usuarios");
  const badge = $("#badge-usuarios-count");

  const t = (state.filtroUsuarios || "").toLowerCase();
  const filtrados = state.usuarios.filter((u) =>
    (u.nombre + " " + u.usuario + " " + (u.uid_publico || "")).toLowerCase().includes(t)
  );

  const nTotal = state.usuarios.length;
  badge.textContent = `${nTotal} ${nTotal === 1 ? "usuario" : "usuarios"}`;

  if (filtrados.length === 0) {
    tbody.innerHTML = "";
    empty.hidden = false;
    empty.textContent = nTotal > 0 && t
      ? "Ningún usuario coincide con el término de búsqueda."
      : "No hay usuarios registrados en esta sede.";
    return;
  }

  empty.hidden = true;
  tbody.innerHTML = filtrados.map((u) => {
    const pillEstado = u.en_linea
      ? `<span class="pill up">En línea</span>`
      : `<span class="pill down">Desconectado</span>`;

    const btnDeshabilitado = _esBtnDeshabilitado(u);
    const disabledAttr = btnDeshabilitado ? " disabled" : "";

    const svcVideo = _obtenerServicio(u, "videoconferencia");
    const videoHabilitado = svcVideo ? svcVideo.habilitado : false;
    const videoClase = videoHabilitado ? "on" : "off";
    const videoTexto = videoHabilitado ? "Habilitado" : "Deshabilitado";

    const svcChat = _obtenerServicio(u, "chat");
    const chatHabilitado = svcChat ? svcChat.habilitado : false;
    const chatClase = chatHabilitado ? "on" : "off";
    const chatTexto = chatHabilitado ? "Habilitado" : "Deshabilitado";

    const uidCorto = u.uid_publico ? `${u.uid_publico.substring(0, 13)}…` : "—";

    // Etiqueta de rol con clase CSS correcta según tipo
    let rolTexto, rolClase;
    if (u.tipo === "tecnico" || u.tipo === "tecnico_jefe") {
      rolTexto = u.rol || "Admin de Sede";
      rolClase = "user-tag-admin-s";
    } else {
      rolTexto = u.rol || "Usuario Sede";
      rolClase = "user-tag-user";
    }

    return `
      <tr>
        <td class="num">#${u.id_empleado}</td>
        <td class="cli">${esc(u.nombre)}</td>
        <td class="mono">${esc(u.usuario)}</td>
        <td><span class="${rolClase}">${esc(rolTexto)}</span></td>
        <td><span class="mono" style="font-size:0.78rem; opacity:0.85" title="${esc(u.uid_publico || '')}">${esc(uidCorto)}</span></td>
        <td>${pillEstado}</td>
        <td>
          <button
            class="btn-toggle ${videoClase}"
            data-id="${u.id_empleado}"
            data-tipo="videoconferencia"
            data-habilitado="${videoHabilitado}"
            ${disabledAttr}
            type="button"
          >${videoTexto}</button>
        </td>
        <td>
          <button
            class="btn-toggle ${chatClase}"
            data-id="${u.id_empleado}"
            data-tipo="chat"
            data-habilitado="${chatHabilitado}"
            ${disabledAttr}
            type="button"
          >${chatTexto}</button>
        </td>
        <td style="text-align:right">
          <button
            class="btn-desactivar btn-eliminar-user"
            data-id="${u.id_empleado}"
            data-user="${esc(u.usuario)}"
            type="button"
            title="Desactivar usuario"
          >❌ Desactivar</button>
        </td>
      </tr>
    `;
  }).join("");

  // Eventos toggle
  tbody.querySelectorAll(".btn-toggle:not([disabled])").forEach((btn) => {
    btn.addEventListener("click", () => {
      const idEmpleado = parseInt(btn.dataset.id, 10);
      const tipoServicio = btn.dataset.tipo;
      const habilitado = btn.dataset.habilitado === "true";
      toggleServicio(idEmpleado, tipoServicio, habilitado);
    });
  });

  // Eventos desactivar usuario
  tbody.querySelectorAll(".btn-eliminar-user").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const idEmp = btn.dataset.id;
      const nomUser = btn.dataset.user;
      if (!confirm(`¿Estás seguro de que deseas desactivar al usuario '${nomUser}' de esta sede?`)) {
        return;
      }
      try {
        const resp = await apiFetch(`/sedes/${encodeURIComponent(state.idSede)}/usuarios/${idEmp}`, {
          method: "DELETE",
        });
        if (resp && resp.ok) {
          await cargarUsuariosSede();
        } else {
          const err = await (resp ? resp.json().catch(() => ({})) : {});
          alert(err.detail || "No se pudo desactivar el usuario.");
        }
      } catch (e) {
        alert("Error al conectar con el servidor.");
      }
    });
  });
}

async function toggleServicio(idEmpleado, tipoServicio, estaHabilitado) {
  const accion = estaHabilitado ? "deshabilitar" : "habilitar";
  try {
    const respuesta = await apiFetch(
      `/sedes/${encodeURIComponent(state.idSede)}/usuarios/${idEmpleado}/servicios/${tipoServicio}/${accion}`,
      { method: "POST" }
    );
    if (!respuesta) return;
    if (respuesta.status === 403) {
      alert("Permiso denegado: no tienes autorización para modificar este servicio.");
      return;
    }
    if (!respuesta.ok) {
      const err = await respuesta.json().catch(() => ({}));
      alert(`Error al ${accion} el servicio: ${err.detail || respuesta.status}`);
      return;
    }
    await cargarUsuariosSede();
  } catch (e) {
    console.error(`Error al ${accion} servicio '${tipoServicio}' para empleado ${idEmpleado}:`, e);
  }
}

/* Modal Crear Usuario */
function abrirModalCrearUsuario() {
  const modal = $("#modal-crear-usuario");
  const msg = $("#msg-crear-usuario");
  const form = $("#form-usuario");
  if (form) form.reset();
  if (msg) {
    msg.hidden = true;
    msg.style.display = "none";
    msg.className = "form-msg";
    msg.textContent = "";
  }

  // Actualizar banner informativo de sede
  const sedeLabel = $("#modal-sede-label");
  if (sedeLabel && state.sedeActual) {
    sedeLabel.textContent = `Sede #${state.sedeActual.id_sede} — ${state.sedeActual.nombre}`;
  }

  // Resetear visibilidad de campos
  const groupDir = $("#group-direccion");
  const avisoAdminS = $("#aviso-admin-s");
  if (groupDir) { groupDir.hidden = false; }
  if (avisoAdminS) { avisoAdminS.hidden = true; }

  // Si el usuario autenticado es admin-s, no puede crear admin-s
  const optAdminS = $("#opt-admin-s");
  if (optAdminS) {
    const esAdminG = state.usuario && state.usuario.tipo_admin === "admin-g";
    optAdminS.hidden = !esAdminG;
    optAdminS.disabled = !esAdminG;
  }

  if (modal) {
    modal.removeAttribute("hidden");
    modal.style.display = "grid";
  }
  setTimeout(() => {
    const input = $("#new-user-nombre");
    if (input) input.focus();
  }, 50);
}

function cerrarModalCrearUsuario() {
  const modal = $("#modal-crear-usuario");
  if (!modal) return;
  modal.setAttribute("hidden", "");
  modal.style.display = "none";
}

async function guardarUsuario(e) {
  e.preventDefault();
  const nombre = $("#new-user-nombre").value.trim();
  const usuario = $("#new-user-usuario").value.trim();
  const contrasena = $("#new-user-pass").value;
  const tipoSeleccionado = $("#new-user-tipo").value;
  const direccion = $("#new-user-direccion").value.trim();
  const msg = $("#msg-crear-usuario");
  const submitBtn = $("#btn-submit-usuario");

  // es_admin_s sólo es true cuando el select es "tecnico" (opción admin-s)
  const esAdminS = tipoSeleccionado === "tecnico";
  // El tipo enviado al backend siempre es "usuario_sede" a menos que sea admin-s
  const tipo = esAdminS ? "tecnico" : "usuario_sede";

  if (!nombre || !usuario || !contrasena) {
    msg.className = "form-msg error";
    msg.textContent = "Nombre, usuario y contraseña son requeridos.";
    msg.hidden = false;
    msg.style.display = "block";
    return;
  }

  if (contrasena.length < 8) {
    msg.className = "form-msg error";
    msg.textContent = "La contraseña debe tener al menos 8 caracteres.";
    msg.hidden = false;
    msg.style.display = "block";
    return;
  }

  submitBtn.disabled = true;
  submitBtn.textContent = "Creando usuario…";
  msg.hidden = true;
  msg.style.display = "none";

  try {
    const respuesta = await apiFetch(`/sedes/${encodeURIComponent(state.idSede)}/usuarios`, {
      method: "POST",
      body: JSON.stringify({
        nombre,
        usuario,
        contrasena,
        tipo,
        direccion: (!esAdminS && direccion) ? direccion : null,
        es_admin_s: esAdminS,
      }),
    });

    if (respuesta && respuesta.status === 201) {
      msg.className = "form-msg success";
      msg.textContent = "¡Usuario registrado exitosamente!";
      msg.hidden = false;
      msg.style.display = "block";
      await cargarUsuariosSede();
      setTimeout(() => {
        cerrarModalCrearUsuario();
      }, 700);
    } else {
      const err = await (respuesta ? respuesta.json().catch(() => ({})) : {});
      msg.className = "form-msg error";
      msg.textContent = err.detail || "No se pudo registrar el usuario.";
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
    submitBtn.textContent = "Crear usuario";
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
    msg.textContent = "Todos los campos de contraseña son obligatorios.";
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
    msg.textContent = "La confirmación de la nueva contraseña no coincide.";
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
      msg.textContent = err.detail || "Error al actualizar contraseña.";
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

async function enviarHeartbeat() {
  try {
    await apiFetch("/heartbeat", { method: "POST" });
  } catch (e) { /* no-op */ }
}


/* Eventos */
$('#logout').addEventListener('click', cerrarSesion);
$('#refresh-sede').addEventListener('click', () => {
  cargarSedeEspecifica();
  cargarUsuariosSede();
});

const btnCrearUser = $('#btn-crear-usuario');
if (btnCrearUser) btnCrearUser.addEventListener('click', abrirModalCrearUsuario);
const btnCerrarUser = $('#btn-cerrar-modal-usuario');
if (btnCerrarUser) btnCerrarUser.addEventListener('click', cerrarModalCrearUsuario);
const btnCancUser = $('#btn-cancelar-usuario');
if (btnCancUser) btnCancUser.addEventListener('click', cerrarModalCrearUsuario);
const formUser = $('#form-usuario');
if (formUser) formUser.addEventListener('submit', guardarUsuario);

// Listener para cambiar visibilidad de campos según tipo de usuario
const selectTipo = $('#new-user-tipo');
if (selectTipo) {
  selectTipo.addEventListener('change', () => {
    const esAdminS = selectTipo.value === 'tecnico';
    const groupDir = $('#group-direccion');
    const avisoAdminS = $('#aviso-admin-s');
    if (groupDir) groupDir.hidden = esAdminS;
    if (avisoAdminS) avisoAdminS.hidden = !esAdminS;
  });
}


const btnCambiarPass = $('#btn-cambiar-pass');
if (btnCambiarPass) btnCambiarPass.addEventListener('click', abrirModalCambiarPass);
const btnCerrarPass = $('#btn-cerrar-modal-pass');
if (btnCerrarPass) btnCerrarPass.addEventListener('click', cerrarModalCambiarPass);
const btnCancPass = $('#btn-cancelar-pass');
if (btnCancPass) btnCancPass.addEventListener('click', cerrarModalCambiarPass);
const formPass = $('#form-cambiar-pass');
if (formPass) formPass.addEventListener('submit', cambiarPassword);

window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    cerrarModalCrearUsuario();
    cerrarModalCambiarPass();
  }
});

const modalUser = $('#modal-crear-usuario');
if (modalUser) {
  modalUser.addEventListener('click', (e) => {
    if (e.target === modalUser) cerrarModalCrearUsuario();
  });
}
const modalPass = $('#modal-cambiar-pass');
if (modalPass) {
  modalPass.addEventListener('click', (e) => {
    if (e.target === modalPass) cerrarModalCambiarPass();
  });
}

$('#q-disp').addEventListener('input', (e) => {
  state.filtroDisp = e.target.value;
  renderDispositivos();
});

$('#q-usuarios').addEventListener('input', (e) => {
  state.filtroUsuarios = e.target.value;
  renderUsuarios();
});

/* Tema */
const root = document.documentElement;
try { const g = localStorage.getItem('cfs-theme'); if (g) root.dataset.theme = g; } catch (e) {}
$('#theme').addEventListener('click', () => {
  const oscuro = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  root.dataset.theme = oscuro ? 'light' : 'dark';
  try { localStorage.setItem('cfs-theme', root.dataset.theme); } catch (e) {}
});

/* ---- Arranque ---- */
async function iniciar() {
  if (!(await validarSesion())) {
    limpiarSesion();
    irALogin();
    return;
  }

  const u = state.usuario;
  const userBadge = $('#user-badge');
  const userName = $('#user-name');
  const userRole = $('#user-role');

  userName.textContent = u.nombre || u.usuario;

  if (u.tipo_admin === "admin-g") {
    userRole.textContent = "ADMIN-G";
    userRole.className = "user-tag admin-g-tag";
  } else if (u.tipo_admin === "admin-s") {
    userRole.textContent = "ADMIN-S";
    userRole.className = "user-tag admin-s-tag";
  } else {
    userRole.textContent = u.rol || "USUARIO";
    userRole.className = "user-tag";
  }
  userBadge.hidden = false;

  // Determinar la sede a consultar
  const params = new URLSearchParams(window.location.search);
  let idSede = params.get("id_sede");

  // Si no se proporcionó id_sede, consultar las sedes disponibles
  if (!idSede) {
    const resSedes = await apiFetch("/sedes");
    if (resSedes && resSedes.ok) {
      const lista = await resSedes.json();
      if (lista.length > 0) {
        idSede = lista[0].id_sede;
      }
    }
  }

  if (!idSede) {
    window.location.replace(PANEL_SEDES);
    return;
  }

  state.idSede = idSede;
  $('#panel').hidden = false;

  await cargarSedeEspecifica();
  await cargarUsuariosSede();

  // Polling de estado cada 2 segundos
  setInterval(cargarUsuariosSede, 2000);
  setInterval(cargarSedeEspecifica, 2000);

  enviarHeartbeat();
  setInterval(enviarHeartbeat, 30000);
}

iniciar();

