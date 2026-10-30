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

/* ---- Datos de monitoreo simulados para la sede ---- */
const SERVICIOS_BASE = [
  ['Troncal Principal', 'Enlace WAN BGP'], ['Enlace de Backup', 'Fibra Óptica Secundaria'],
  ['VLAN Gestión', 'Switches y Access Points'], ['VLAN Telefonía IP', 'VoIP PBX'],
  ['Servidor Local', 'Base de datos de sede'], ['Portal Cautivo', 'Wi-Fi Visitantes'],
  ['VPN Inter-sedes', 'Túnel IPSec'], ['Videovigilancia', 'CCTV IP Sede'],
].map(([cliente, servicio], i) => ({
  id: i, cliente, servicio,
  lecturas: Array.from({ length: 14 }, () => 20 + Math.random() * 80),
  caido: i === 7, disp: 99.8 - Math.random() * (i === 7 ? 5 : 0.8),
}));

async function cargarServicios() {
  SERVICIOS_BASE.forEach((c) => {
    if (Math.random() < 0.04) c.caido = !c.caido;
    const base = c.caido ? 0 : 20 + Math.random() * (Math.random() < 0.15 ? 280 : 70);
    c.lecturas = [...c.lecturas.slice(1), base];
  });
  return SERVICIOS_BASE.map((c) => {
    const lat = c.lecturas[c.lecturas.length - 1];
    const estado = c.caido ? 'down' : lat > 180 ? 'warn' : 'up';
    return { ...c, lat, estado };
  });
}

function spark(c) {
  return '<div class="spark" aria-hidden="true">' + c.lecturas.map((v) => {
    const cls = v === 0 ? 'd' : v > 180 ? 'w' : '';
    return `<i class="${cls}" style="height:${v === 0 ? 3 : Math.min(26, 5 + v / 10)}px"></i>`;
  }).join('') + '</div>';
}

function renderServicios() {
  const t = state.textoServicios.toLowerCase();
  const lista = state.servicios.filter((c) =>
    (state.filtroServicios === 'all' || c.estado === state.filtroServicios) &&
    (c.cliente + ' ' + c.servicio).toLowerCase().includes(t)
  );

  const tbody = $('#rows-servicios');
  const empty = $('#empty-servicios');

  if (lista.length === 0) {
    tbody.innerHTML = "";
    empty.hidden = false;
    return;
  }

  empty.hidden = true;
  tbody.innerHTML = lista.map((c) => `
    <tr>
      <td class="cli">${esc(c.cliente)}</td>
      <td>${esc(c.servicio)}</td>
      <td><span class="pill ${c.estado}">${ETIQUETA_SERV[c.estado]}</span></td>
      <td class="num">${c.estado === 'down' ? '—' : Math.round(c.lat) + ' ms'}</td>
      <td>${spark(c)}</td>
      <td class="num">${c.disp.toFixed(2)} %</td>
    </tr>
  `).join('');
}

async function actualizarServicios() {
  try {
    state.servicios = await cargarServicios();
    renderServicios();
  } catch (e) {
    console.error("Error al actualizar servicios:", e);
  }
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
    (u.nombre + " " + u.usuario).toLowerCase().includes(t)
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
      : `<span class="pill down">Fuera de línea</span>`;

    const btnDeshabilitado = _esBtnDeshabilitado(u);
    const disabledAttr = btnDeshabilitado ? " disabled" : "";

    const svcVideo = _obtenerServicio(u, "videoconferencia");
    const videoHabilitado = svcVideo ? svcVideo.habilitado : false;
    const videoClase = videoHabilitado ? "on" : "off";
    const videoTexto = videoHabilitado ? "Deshabilitar" : "Habilitar";

    const svcChat = _obtenerServicio(u, "chat");
    const chatHabilitado = svcChat ? svcChat.habilitado : false;
    const chatClase = chatHabilitado ? "on" : "off";
    const chatTexto = chatHabilitado ? "Deshabilitar" : "Habilitar";

    return `
      <tr>
        <td class="num">#${u.id_empleado}</td>
        <td class="cli">${esc(u.nombre)}</td>
        <td class="mono">${esc(u.usuario)}</td>
        <td>${esc(u.tipo)}</td>
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
      </tr>
    `;
  }).join("");

  // Delegación de eventos para los botones toggle
  tbody.querySelectorAll(".btn-toggle:not([disabled])").forEach((btn) => {
    btn.addEventListener("click", () => {
      const idEmpleado = parseInt(btn.dataset.id, 10);
      const tipoServicio = btn.dataset.tipo;
      const habilitado = btn.dataset.habilitado === "true";
      toggleServicio(idEmpleado, tipoServicio, habilitado);
    });
  });
}

async function toggleServicio(idEmpleado, tipoServicio, estaHabilitado) {
  // Si está habilitado, lo deshabilitamos; si no, lo habilitamos
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
    // Recargar la lista de usuarios para reflejar el cambio
    await cargarUsuariosSede();
  } catch (e) {
    console.error(`Error al ${accion} servicio '${tipoServicio}' para empleado ${idEmpleado}:`, e);
  }
}

/* Eventos */
$('#logout').addEventListener('click', cerrarSesion);
$('#refresh-sede').addEventListener('click', () => {
  cargarSedeEspecifica();
  actualizarServicios();
});

$('#q-disp').addEventListener('input', (e) => {
  state.filtroDisp = e.target.value;
  renderDispositivos();
});

$('#q-usuarios').addEventListener('input', (e) => {
  state.filtroUsuarios = e.target.value;
  renderUsuarios();
});

$('#q-servicios').addEventListener('input', (e) => {
  state.textoServicios = e.target.value;
  renderServicios();
});

document.querySelectorAll('.chip[data-f]').forEach((b) => b.addEventListener('click', () => {
  document.querySelectorAll('.chip[data-f]').forEach((x) => x.classList.toggle('on', x === b));
  state.filtroServicios = b.dataset.f;
  renderServicios();
}));

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
    // No hay sede accesible: volver a la lista principal
    window.location.replace(PANEL_SEDES);
    return;
  }

  state.idSede = idSede;
  $('#panel').hidden = false;

  await cargarSedeEspecifica();
  await cargarUsuariosSede();
  await actualizarServicios();
  setInterval(actualizarServicios, 15000);
}

iniciar();
