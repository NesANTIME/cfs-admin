"use strict";

const $ = (s) => document.querySelector(s);
const API = "/api";
const LOGIN = "../index.html";
const state = { clientes: [], filtro: "all", texto: "" };
const ETIQUETA = { up: "En línea", warn: "Alerta", down: "Caído" };

/* ---- Sesión ---- */
function leerToken(clave) {
  try { return sessionStorage.getItem(clave); } catch (e) { return null; }
}

function guardarTokens(access, refresh) {
  try {
    sessionStorage.setItem("access_token", access);
    sessionStorage.setItem("refresh_token", refresh);
  } catch (e) { /* almacenamiento no disponible */ }
}

function limpiarSesion() {
  try {
    sessionStorage.removeItem("access_token");
    sessionStorage.removeItem("refresh_token");
  } catch (e) { /* almacenamiento no disponible */ }
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

    if (respuesta.status === 401 && await renovarSesion()) {
      const nuevoAccess = leerToken("access_token");
      respuesta = await fetch(`${API}/me`, {
        headers: { "Authorization": `Bearer ${nuevoAccess}`, "Accept": "application/json" },
        cache: "no-store",
      });
    }

    return respuesta.ok;
  } catch (e) {
    return false;
  }
}

function cerrarSesion() {
  const refresh = leerToken("refresh_token");

  if (refresh) {
    // keepalive permite que la petición termine aunque naveguemos de inmediato.
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

/* ---- Datos: reemplaza esta función por tu API (fetch) ---- */
const BASE = [
  ['Inversiones Caribe', 'API de pagos'], ['Hotel Bocagrande', 'Sitio web'],
  ['Naviera del Sur', 'Base de datos'], ['Clínica Santa Rita', 'VPN'],
  ['Textiles Bolívar', 'ERP'], ['Puerto Seco S.A.', 'Correo'],
  ['Alcaldía Local', 'Portal ciudadano'], ['Café Getsemaní', 'Punto de venta'],
  ['Logística Rápida', 'Rastreo GPS'], ['Colegio Mayor', 'Plataforma virtual'],
].map(([cliente, servicio], i) => ({
  id: i, cliente, servicio,
  lecturas: Array.from({ length: 14 }, () => 40 + Math.random() * 120),
  caido: i === 2, disp: 99.9 - Math.random() * (i === 2 ? 6 : 1.2),
}));

async function cargarDatos() {
  // Ejemplo real: const r = await fetch('/api/clientes'); return r.json();
  BASE.forEach((c) => {
    if (Math.random() < 0.04) c.caido = !c.caido;
    const base = c.caido ? 0 : 40 + Math.random() * (Math.random() < 0.15 ? 420 : 140);
    c.lecturas = [...c.lecturas.slice(1), base];
  });
  return BASE.map((c) => {
    const lat = c.lecturas[c.lecturas.length - 1];
    const estado = c.caido ? 'down' : lat > 250 ? 'warn' : 'up';
    return { ...c, lat, estado };
  });
}

/* ---- Render ---- */
function esc(t) { const d = document.createElement('div'); d.textContent = t; return d.innerHTML; }

function spark(c) {
  return '<div class="spark" aria-hidden="true">' + c.lecturas.map((v) => {
    const cls = v === 0 ? 'd' : v > 250 ? 'w' : '';
    return `<i class="${cls}" style="height:${v === 0 ? 3 : Math.min(26, 5 + v / 12)}px"></i>`;
  }).join('') + '</div>';
}

function render() {
  const t = state.texto.toLowerCase();
  const lista = state.clientes.filter((c) =>
    (state.filtro === 'all' || c.estado === state.filtro) &&
    (c.cliente + ' ' + c.servicio).toLowerCase().includes(t));
  $('#rows').innerHTML = lista.map((c) => `
    <tr>
      <td class="cli">${esc(c.cliente)}</td>
      <td>${esc(c.servicio)}</td>
      <td><span class="pill ${c.estado}">${ETIQUETA[c.estado]}</span></td>
      <td class="num">${c.estado === 'down' ? '—' : Math.round(c.lat) + ' ms'}</td>
      <td>${spark(c)}</td>
      <td class="num">${c.disp.toFixed(2)} %</td>
    </tr>`).join('');
  $('#empty').hidden = lista.length > 0;
  const n = (e) => state.clientes.filter((c) => c.estado === e).length;
  $('#k-total').textContent = state.clientes.length;
  $('#k-up').textContent = n('up');
  $('#k-warn').textContent = n('warn');
  $('#k-down').textContent = n('down');
}

async function actualizar() {
  const btn = $('#refresh');
  btn.disabled = true;
  try {
    state.clientes = await cargarDatos();
    render();
    $('#updated').textContent = 'Actualizado a las ' + new Date().toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch (e) {
    $('#updated').textContent = 'No se pudieron cargar los datos. Revisa tu conexión e intenta de nuevo.';
  } finally { btn.disabled = false; }
}

/* ---- Eventos ---- */
$('#q').addEventListener('input', (e) => { state.texto = e.target.value; render(); });
document.querySelectorAll('.chip').forEach((b) => b.addEventListener('click', () => {
  document.querySelectorAll('.chip').forEach((x) => x.classList.toggle('on', x === b));
  state.filtro = b.dataset.f; render();
}));
$('#refresh').addEventListener('click', actualizar);
$('#logout').addEventListener('click', cerrarSesion);

/* Tema claro/oscuro */
const root = document.documentElement;
try { const g = localStorage.getItem('cfs-theme'); if (g) root.dataset.theme = g; } catch (e) {}
$('#theme').addEventListener('click', () => {
  const oscuro = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  root.dataset.theme = oscuro ? 'light' : 'dark';
  try { localStorage.setItem('cfs-theme', root.dataset.theme); } catch (e) {}
});

/* ---- Arranque: sin sesión válida no se muestra el panel ---- */
async function iniciar() {
  if (!(await validarSesion())) {
    limpiarSesion();
    irALogin();
    return;
  }

  $('#panel').hidden = false;
  await actualizar();
  setInterval(actualizar, 15000);
}

iniciar();
