"use strict";

const $ = (s) => document.querySelector(s);
const API = "/api";
const LOGIN = "../index.html";
const PANEL_SEDES = "index.html";

const state = {
  usuario: null,
  logs: [],
  filtros: {
    q: "",
    entidad: "",
    actor: "",
    desde: "",
    hasta: "",
  },
};

function leerToken(clave) {
  try { return sessionStorage.getItem(clave); } catch (e) { return null; }
}

function irALogin() {
  window.location.replace(LOGIN);
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

  return fetch(`${API}${endpoint}`, {
    ...opciones,
    headers,
    cache: "no-store",
  });
}

function esc(t) {
  const d = document.createElement("div");
  d.textContent = t == null ? "" : String(t);
  return d.innerHTML;
}

function obtenerClaseBadge(accion) {
  const a = (accion || "").toUpperCase();
  if (a.includes("PERMISO")) return "badge-permiso";
  if (a.includes("DESACTIV") || a.includes("DESHABILIT")) return "badge-desactivar";
  if (a.includes("DISPOSITIVO")) return "badge-disp";
  if (a.includes("SEDE")) return "badge-sede";
  if (a.includes("USUARIO") || a.includes("ADMIN")) return "badge-usuario";
  return "badge-otro";
}

async function cargarLogs() {
  const params = new URLSearchParams({ limit: "500", offset: "0" });
  if (state.filtros.q) params.set("q", state.filtros.q);
  if (state.filtros.entidad) params.set("entidad", state.filtros.entidad);
  if (state.filtros.actor) params.set("actor", state.filtros.actor);
  if (state.filtros.desde) params.set("desde", new Date(state.filtros.desde + "T00:00:00Z").toISOString());
  if (state.filtros.hasta) params.set("hasta", new Date(state.filtros.hasta + "T23:59:59Z").toISOString());

  try {
    const res = await apiFetch(`/logs?${params.toString()}`);
    if (!res || !res.ok) {
      if (res && res.status === 403) {
        alert("Acceso denegado: se requieren permisos de Administrador General (admin-g).");
        window.location.replace(PANEL_SEDES);
      }
      return;
    }

    state.logs = await res.json();
    renderLogs();
    actualizarKpis();
  } catch (e) {
    console.error("Error al cargar registros de auditoría:", e);
  }
}

function renderLogs() {
  const tbody = $("#rows-logs");
  const empty = $("#empty-logs");
  const badgeCount = $("#badge-logs-count");
  const subContador = $("#subtitulo-contador");

  const lista = state.logs;
  badgeCount.textContent = `${lista.length} evento${lista.length !== 1 ? 's' : ''}`;
  if (subContador) {
    subContador.textContent = lista.length > 0
      ? `Listando ${lista.length} eventos registrados recientemente`
      : "Sin registros para los filtros aplicados";
  }

  if (lista.length === 0) {
    tbody.innerHTML = "";
    empty.hidden = false;
    return;
  }

  empty.hidden = true;
  tbody.innerHTML = lista.map((l) => {
    const claseBadge = obtenerClaseBadge(l.accion);
    const fecha = l.creado_en ? new Date(l.creado_en).toLocaleString() : "—";
    const ip = l.ip_origen || "local";

    return `
      <tr>
        <td class="num">#${l.id}</td>
        <td style="font-size:0.78rem; opacity:0.85;">${fecha}</td>
        <td><span class="badge-accion ${claseBadge}">${esc(l.accion)}</span></td>
        <td><span class="chip" style="cursor:default; height:24px; font-size:0.75rem;">${esc(l.entidad)}</span></td>
        <td class="mono" style="font-size:0.8rem; font-weight:600;">${esc(l.actor_usuario || 'sistema')}</td>
        <td class="mono" style="font-size:0.75rem; opacity:0.75;">${esc(ip)}</td>
        <td style="font-size:0.83rem; line-height:1.4;">${esc(l.detalle || '—')}</td>
      </tr>
    `;
  }).join("");
}

function actualizarKpis() {
  const total = state.logs.length;
  const permisos = state.logs.filter((l) => (l.accion || "").includes("PERMISO")).length;
  const dispositivos = state.logs.filter((l) => (l.accion || "").includes("DISPOSITIVO")).length;
  const desactivados = state.logs.filter((l) =>
    (l.accion || "").includes("DESHABILIT") || (l.accion || "").includes("DESACTIV")
  ).length;

  $("#kpi-total-logs").textContent = total;
  $("#kpi-permisos").textContent = permisos;
  $("#kpi-dispositivos").textContent = dispositivos;
  $("#kpi-desactivados").textContent = desactivados;
}

async function cargarArchivosCarpetaLogs() {
  const cont = $("#lista-archivos-logs");
  if (!cont) return;

  try {
    const res = await apiFetch("/logs/archivos");
    if (!res || !res.ok) {
      cont.innerHTML = "No se pudo consultar el directorio físico de logs.";
      return;
    }
    const data = await res.json();
    const archivos = data.archivos || [];
    if (archivos.length === 0) {
      cont.innerHTML = `Carpeta: <code>${esc(data.carpeta)}</code> (Sin archivos creados todavía).`;
      return;
    }

    cont.innerHTML = `
      <div style="margin-bottom:6px;"><strong>Directorio Servidor:</strong> <code>${esc(data.carpeta)}</code></div>
      <ul style="margin:0; padding-left:20px;">
        ${archivos.map(a => `
          <li>
            📄 <strong>${esc(a.nombre)}</strong>
            <span style="opacity:0.65;">(${Math.round(a.tamano_bytes / 1024 * 10) / 10} KB · Modificado: ${new Date(a.modificado).toLocaleString()})</span>
          </li>
        `).join("")}
      </ul>
    `;
  } catch (e) {
    cont.innerHTML = "Error al listar archivos físicos de logs.";
  }
}

/* ---- Exportaciones ---- */

async function exportarAPDF() {
  // Requisito 5: exportar a PDF para Admin-G
  // Abre el reporte formal imprimible en una nueva pestaña y activa el diálogo de impresión / Guardar en PDF
  const access = leerToken("access_token");
  const url = `${API}/logs/exportar/html-imprimible?autoprint=1`;

  // Abrir ventana y permitir que el usuario imprima o guarde como PDF
  const ventana = window.open("", "_blank");
  if (!ventana) {
    alert("Por favor permite ventanas emergentes para abrir el reporte en PDF.");
    return;
  }
  ventana.document.write("<p style='font-family:sans-serif;'>Cargando reporte oficial para exportación a PDF…</p>");

  try {
    const res = await apiFetch("/logs/exportar/html-imprimible?autoprint=1");
    if (res && res.ok) {
      const html = await res.text();
      ventana.document.open();
      ventana.document.write(html);
      ventana.document.close();
    } else {
      ventana.close();
      alert("No se pudo generar el reporte en PDF.");
    }
  } catch (e) {
    ventana.close();
    alert("Error de conexión al generar PDF.");
  }
}

async function exportarACSV() {
  try {
    const res = await apiFetch("/logs/exportar/csv");
    if (!res || !res.ok) {
      alert("No se pudo exportar el archivo CSV.");
      return;
    }
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `cfs_admin_auditoria_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  } catch (e) {
    alert("Error al descargar CSV de auditoría.");
  }
}

/* ---- Arranque y Verificación de Permisos ---- */

async function iniciar() {
  const access = leerToken("access_token");
  if (!access) {
    irALogin();
    return;
  }

  try {
    const resMe = await apiFetch("/me");
    if (!resMe || !resMe.ok) {
      irALogin();
      return;
    }
    const u = await resMe.json();
    state.usuario = u;

    // Solo Admin-G tiene acceso a la página especial de logs
    if (u.tipo_admin !== "admin-g") {
      alert("Acceso Restringido: esta página de auditoría y registros es exclusiva para Administradores Generales (admin-g).");
      window.location.replace(PANEL_SEDES);
      return;
    }

    $("#user-name").textContent = u.nombre || u.usuario;
    $("#user-badge").hidden = false;
    $("#panel").hidden = false;

    await cargarLogs();
    await cargarArchivosCarpetaLogs();

    // Polling suave de logs cada 10 segundos
    setInterval(cargarLogs, 10000);
  } catch (e) {
    irALogin();
  }
}

/* Eventos */
$("#logout").addEventListener("click", () => {
  sessionStorage.clear();
  irALogin();
});

$("#btn-refrescar").addEventListener("click", () => {
  cargarLogs();
  cargarArchivosCarpetaLogs();
});

$("#btn-exportar-pdf").addEventListener("click", exportarAPDF);
$("#btn-exportar-csv").addEventListener("click", exportarACSV);

$("#filtro-texto").addEventListener("input", (e) => {
  state.filtros.q = e.target.value.trim();
  cargarLogs();
});
$("#filtro-entidad").addEventListener("change", (e) => {
  state.filtros.entidad = e.target.value;
  cargarLogs();
});
$("#filtro-actor").addEventListener("input", (e) => {
  state.filtros.actor = e.target.value.trim();
  cargarLogs();
});
$("#filtro-desde").addEventListener("change", (e) => {
  state.filtros.desde = e.target.value;
  cargarLogs();
});
$("#filtro-hasta").addEventListener("change", (e) => {
  state.filtros.hasta = e.target.value;
  cargarLogs();
});

$("#btn-limpiar-filtros").addEventListener("click", () => {
  $("#filtro-texto").value = "";
  $("#filtro-entidad").value = "";
  $("#filtro-actor").value = "";
  $("#filtro-desde").value = "";
  $("#filtro-hasta").value = "";
  state.filtros = { q: "", entidad: "", actor: "", desde: "", hasta: "" };
  cargarLogs();
});

/* Tema */
const root = document.documentElement;
try { const g = localStorage.getItem("cfs-theme"); if (g) root.dataset.theme = g; } catch (e) {}
$("#theme").addEventListener("click", () => {
  const oscuro = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = oscuro ? "light" : "dark";
  try { localStorage.setItem("cfs-theme", root.dataset.theme); } catch (e) {}
});

iniciar();
