"use strict";

const $ = (s) => document.querySelector(s);
const API = "/api";
const LOGIN = "../index.html";
const BANDEJA = "videollamadas.html";

const state = {
  usuario: null,
  codigoSala: null,
  sala: null,
  esIniciador: false,
  aceptada: false,
  peerId: null,
  estado: "cargando",
  localStream: null,
  peerConnection: null,
  websocket: null,
  reconnectAttempts: 0,
  reconnectTimer: null,
  httpSignalInterval: null,
  usingFallback: false,
  iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
  icePendientes: [],
  ofertaEnviada: false,
  ofertaEnCurso: false,
  micHabilitado: true,
  camHabilitada: true,
  finalizado: false,
  pollEstado: null,
  pingInterval: null,
  heartbeatInterval: null,
  redirectTimer: null,
};

/* ------------------------------------------------------------------ */
/* Utilidades de sesión y API                                          */
/* ------------------------------------------------------------------ */

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

/* ------------------------------------------------------------------ */
/* UI                                                                  */
/* ------------------------------------------------------------------ */

function mostrarAlerta(mensaje, duracion = 4000) {
  const el = $("#call-alert");
  if (!el) return;
  el.textContent = mensaje;
  el.hidden = false;
  clearTimeout(mostrarAlerta._timer);
  mostrarAlerta._timer = setTimeout(() => { el.hidden = true; }, duracion);
}

function setEstado(principal, secundario = "") {
  const status = $("#call-status-text");
  if (status) status.textContent = principal;
  if (secundario) {
    const meta = $("#call-remote-meta");
    if (meta) meta.textContent = secundario;
  }
}

function setBotonColgar(texto) {
  const btn = $("#btn-colgar");
  if (!btn) return;
  const lbl = btn.querySelector(".lbl");
  if (lbl) lbl.textContent = texto;
}

function volverABandeja(mensaje = "") {
  if (mensaje) mostrarAlerta(mensaje, 5000);
  clearTimeout(state.redirectTimer);
  state.redirectTimer = setTimeout(() => {
    window.location.replace(BANDEJA);
  }, mensaje ? 2200 : 0);
}

/* ------------------------------------------------------------------ */
/* Medios locales                                                      */
/* ------------------------------------------------------------------ */

function crearStreamDemo() {
  const canvas = document.createElement("canvas");
  canvas.width = 640;
  canvas.height = 480;
  const ctx = canvas.getContext("2d");
  let frame = 0;
  setInterval(() => {
    frame++;
    ctx.fillStyle = "#1e3a29";
    ctx.fillRect(0, 0, 640, 480);
    ctx.fillStyle = "#f6c945";
    ctx.font = "22px sans-serif";
    ctx.fillText("Cámara de prueba CFS", 30, 220);
    ctx.fillText(`Frame ${frame}`, 30, 260);
  }, 100);
  return canvas.captureStream(15);
}

async function iniciarMediosLocales() {
  const localVideo = $("#local-video");
  const demo = new URLSearchParams(window.location.search).get("demo") === "1";

  if (demo) {
    state.localStream = crearStreamDemo();
    if (localVideo) localVideo.srcObject = state.localStream;
    mostrarAlerta("Modo de prueba: video generado por el sistema, sin audio real.");
    return;
  }

  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error(
      "Tu navegador no permite captura de medios. La videollamada requiere HTTPS fuera de localhost."
    );
  }

  try {
    state.localStream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: { echoCancellation: true, noiseSuppression: true },
    });
  } catch (err) {
    if (err.name === "NotAllowedError") {
      throw new Error("Permiso de cámara/micrófono denegado. Habilítalo en el navegador.");
    }
    if (err.name === "NotFoundError") {
      throw new Error("No se encontró cámara o micrófono en este equipo.");
    }
    if (err.name === "NotReadableError") {
      throw new Error("La cámara está siendo usada por otra aplicación.");
    }
    throw new Error(
      "No se pudo acceder a cámara/micrófono. Si accedes por red local, la página debe usar HTTPS."
    );
  }

  if (localVideo) localVideo.srcObject = state.localStream;
}

async function cargarIceServers() {
  try {
    const res = await apiFetch("/videoconferencia/ice");
    if (res && res.ok) {
      const datos = await res.json();
      if (Array.isArray(datos.iceServers) && datos.iceServers.length) {
        state.iceServers = datos.iceServers;
      }
    }
  } catch (e) {
    // Se conserva el STUN por defecto.
  }
}

/* ------------------------------------------------------------------ */
/* WebRTC                                                              */
/* ------------------------------------------------------------------ */

function crearPeerConnection() {
  if (state.peerConnection) return state.peerConnection;

  const pc = new RTCPeerConnection({ iceServers: state.iceServers });
  state.peerConnection = pc;

  if (state.localStream) {
    state.localStream.getTracks().forEach((track) => {
      pc.addTrack(track, state.localStream);
    });
  }

  pc.ontrack = (event) => {
    const remoteVideo = $("#remote-video");
    const placeholder = $("#remote-placeholder");
    if (event.streams && event.streams[0] && remoteVideo) {
      remoteVideo.srcObject = event.streams[0];
      if (placeholder) placeholder.hidden = true;
    }
  };

  pc.onicecandidate = (event) => {
    if (event.candidate) {
      enviarSenal({ type: "candidate", candidate: event.candidate });
    }
  };

  pc.onconnectionstatechange = () => {
    const estado = pc.connectionState;
    if (estado === "connected") {
      state.estado = "en_llamada";
      setEstado("Conexión establecida. La videollamada está en curso.");
      setBotonColgar("Finalizar");
    } else if (estado === "disconnected") {
      setEstado("Reconectando la videollamada…");
    } else if (estado === "failed") {
      setEstado("La conexión falló. Intentando reiniciar el ICE…");
      if (state.esIniciador) {
        try { pc.restartIce(); } catch (e) { /* no-op */ }
        state.ofertaEnviada = false;
        crearOferta(true);
      }
    }
  };

  return pc;
}

async function flushIcePendientes() {
  const pc = state.peerConnection;
  if (!pc || !pc.remoteDescription) return;
  const pendientes = state.icePendientes.splice(0);
  for (const candidate of pendientes) {
    try {
      await pc.addIceCandidate(new RTCIceCandidate(candidate));
    } catch (e) {
      // Un candidato inválido no debe tumbar la llamada.
    }
  }
}

async function crearOferta(forzar = false) {
  const pc = state.peerConnection;
  if (!pc || !state.esIniciador || state.finalizado) return;
  if (state.ofertaEnCurso) return;
  if (state.ofertaEnviada && !forzar) return;
  if (!state.localStream) return;

  state.ofertaEnCurso = true;
  try {
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    state.ofertaEnviada = true;
    enviarSenal({ type: "offer", sdp: pc.localDescription });
  } catch (e) {
    mostrarAlerta("No se pudo generar la oferta WebRTC.");
  } finally {
    state.ofertaEnCurso = false;
  }
}

/* ------------------------------------------------------------------ */
/* Señalización                                                        */
/* ------------------------------------------------------------------ */

function construirWsUrl() {
  const protocolo = window.location.protocol === "https:" ? "wss:" : "ws:";
  const token = leerToken("access_token") || "";
  return `${protocolo}//${window.location.host}${API}/videoconferencia/ws/${encodeURIComponent(state.codigoSala)}?token=${encodeURIComponent(token)}`;
}

function conectarSenalizacion() {
  if (state.finalizado || state.usingFallback) return;
  let ws;
  try {
    ws = new WebSocket(construirWsUrl());
  } catch (e) {
    iniciarFallbackHttp();
    return;
  }
  state.websocket = ws;

  ws.onopen = () => {
    state.reconnectAttempts = 0;
  };

  ws.onmessage = async (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch (e) {
      return;
    }
    try {
      await procesarSenal(msg);
    } catch (e) {
      mostrarAlerta("Error al procesar la señalización de la llamada.");
    }
  };

  ws.onerror = () => { /* onclose decide la reconexión */ };

  ws.onclose = (event) => {
    if (state.finalizado) return;
    if (event.code === 4001 || event.code === 4003 || event.code === 4004) {
      finalizarLlamada("No tienes autorización para esta sala.", false);
      return;
    }
    programarReconexion();
  };
}

function programarReconexion() {
  if (state.finalizado || state.usingFallback) return;
  clearTimeout(state.reconnectTimer);

  if (state.reconnectAttempts >= 3) {
    iniciarFallbackHttp();
    return;
  }

  const espera = [1000, 2000, 4000][state.reconnectAttempts] || 4000;
  state.reconnectAttempts += 1;
  setEstado("Conexión de señalización interrumpida. Reintentando…");
  state.reconnectTimer = setTimeout(conectarSenalizacion, espera);
}

function iniciarFallbackHttp() {
  if (state.httpSignalInterval || state.finalizado) return;
  state.usingFallback = true;
  setEstado("Usando señalización HTTP de respaldo…");

  state.httpSignalInterval = setInterval(async () => {
    if (state.finalizado) return;
    try {
      const res = await apiFetch(`/videoconferencia/salas/${encodeURIComponent(state.codigoSala)}/signal`);
      if (!res) return;
      if (!res.ok) return;
      const datos = await res.json();
      if (datos.sala_activa === false) {
        finalizarLlamada("La videollamada terminó.", false);
        return;
      }
      for (const senal of datos.signals || []) {
        await procesarSenal(senal);
      }
    } catch (e) {
      // Se reintenta en el siguiente ciclo.
    }
  }, 1500);

  if (state.esIniciador) {
    setTimeout(() => crearOferta(true), 600);
  }
}

function enviarSenal(senal) {
  const tipo = senal.type;
  const paquete = { type: tipo };
  if (tipo === "candidate") paquete.candidate = senal.candidate;
  else paquete.sdp = senal.sdp;

  if (state.websocket && state.websocket.readyState === WebSocket.OPEN) {
    state.websocket.send(JSON.stringify(paquete));
    return;
  }

  if (!state.peerId) return;
  apiFetch(`/videoconferencia/salas/${encodeURIComponent(state.codigoSala)}/signal`, {
    method: "POST",
    body: JSON.stringify({
      tipo,
      para_id: state.peerId,
      sdp: paquete.sdp || null,
      candidate: paquete.candidate || null,
    }),
  }).catch(() => {});
}

async function procesarSenal(msg) {
  const tipo = msg.type || msg.tipo;
  const pc = state.peerConnection;

  if (tipo === "sala_info") {
    if (typeof msg.es_iniciador === "boolean") state.esIniciador = msg.es_iniciador;
    if (msg.peer_id) state.peerId = msg.peer_id;
    if (msg.peer_id && state.esIniciador) crearOferta();
    return;
  }

  if (tipo === "peer_joined") {
    if (msg.peer_id) state.peerId = msg.peer_id;
    setEstado("El contacto se unió. Conectando…");
    if (state.esIniciador) crearOferta();
    return;
  }

  if (tipo === "peer_left") {
    setEstado("El contacto salió de la llamada.");
    setBotonColgar("Volver");
    return;
  }

  if (tipo === "sala_finalizada" || tipo === "sala_cancelada") {
    finalizarLlamada("La videollamada terminó.", false);
    return;
  }

  if (tipo === "invitacion_rechazada") {
    finalizarLlamada("El contacto rechazó la invitación.", false);
    return;
  }

  if (tipo === "invitacion_aceptada") {
    if (msg.peer_id) state.peerId = msg.peer_id;
    return;
  }

  if (tipo === "error") {
    mostrarAlerta(msg.detail || "Error de señalización.");
    return;
  }

  if (tipo === "pong") return;
  if (!pc) return;

  if (tipo === "offer") {
    if (state.esIniciador) return;
    const sdp = msg.sdp || msg.offer;
    if (!sdp) return;
    await pc.setRemoteDescription(new RTCSessionDescription(sdp));
    await flushIcePendientes();
    const answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);
    enviarSenal({ type: "answer", sdp: answer });
    return;
  }

  if (tipo === "answer") {
    if (!state.esIniciador) return;
    const sdp = msg.sdp || msg.answer;
    if (!sdp) return;
    await pc.setRemoteDescription(new RTCSessionDescription(sdp));
    await flushIcePendientes();
    return;
  }

  if (tipo === "candidate" && msg.candidate) {
    if (!pc.remoteDescription) {
      state.icePendientes.push(msg.candidate);
      return;
    }
    try {
      await pc.addIceCandidate(new RTCIceCandidate(msg.candidate));
    } catch (e) {
      // Algunos candidatos llegan tarde o duplicados; se ignoran.
    }
  }
}

/* ------------------------------------------------------------------ */
/* Sala y ciclo de vida                                                */
/* ------------------------------------------------------------------ */

async function cargarSala() {
  const params = new URLSearchParams(window.location.search);
  const codigo = params.get("codigo_sala") || params.get("sala_id");
  if (!codigo) {
    volverABandeja("No se indicó una sala de videollamada.");
    return false;
  }
  state.codigoSala = codigo;

  const res = await apiFetch(`/videoconferencia/salas/${encodeURIComponent(codigo)}`);
  if (!res) {
    irALogin();
    return false;
  }
  if (!res.ok) {
    const datos = await res.json().catch(() => ({}));
    volverABandeja(datos.detail || "No se pudo acceder a la sala.");
    return false;
  }

  state.sala = await res.json();
  state.esIniciador = Boolean(state.sala.es_iniciador);
  state.aceptada = state.sala.estado_invitacion === "aceptada";
  state.peerId = state.esIniciador ? state.sala.id_invitado : state.sala.id_iniciador;

  const roomCode = $("#call-room-code");
  if (roomCode) roomCode.textContent = `Sala: #${state.sala.codigo_sala}`;

  const titulo = $("#call-title");
  if (titulo) titulo.textContent = state.esIniciador ? "Videollamada iniciada" : "Videollamada";

  const remoteName = $("#remote-user-name");
  if (remoteName) {
    if (state.esIniciador) {
      remoteName.textContent = state.sala.nombre_invitado || "Invitación enviada";
    } else {
      remoteName.textContent = state.sala.nombre_iniciador || "Contacto";
    }
  }

  const meta = $("#call-remote-meta");
  if (meta) {
    const partes = [];
    if (state.esIniciador) {
      if (state.sala.usuario_invitado) partes.push(`@${state.sala.usuario_invitado}`);
      if (state.sala.sede_invitado) partes.push(state.sala.sede_invitado);
    } else {
      if (state.sala.sede_iniciador) partes.push(state.sala.sede_iniciador);
    }
    meta.textContent = partes.filter(Boolean).join(" · ");
  }
  return true;
}

function mostrarEspera() {
  state.estado = "esperando_aceptacion";
  let minutos = 2;
  if (state.sala.expira_en) {
    const restante = new Date(state.sala.expira_en).getTime() - Date.now();
    if (!Number.isNaN(restante)) minutos = Math.max(1, Math.ceil(restante / 60000));
  }
  setEstado(
    "Esperando que el contacto acepte la invitación…",
    `La invitación expira en ${minutos} minuto(s).`
  );
  $("#waiting-actions").hidden = false;
  setBotonColgar("Cancelar");
}

async function esperarAceptacion() {
  mostrarEspera();
  clearInterval(state.pollEstado);
  state.pollEstado = setInterval(async () => {
    if (state.finalizado) return;
    const res = await apiFetch(`/videoconferencia/salas/${encodeURIComponent(state.codigoSala)}`);
    if (!res) return;
    if (!res.ok) {
      clearInterval(state.pollEstado);
      volverABandeja("La sala ya no está disponible.");
      return;
    }
    const sala = await res.json();
    state.sala = sala;

    if (sala.estado_invitacion === "aceptada") {
      clearInterval(state.pollEstado);
      state.aceptada = true;
      $("#waiting-actions").hidden = true;
      await comenzarLlamada();
      return;
    }
    if (["rechazada", "cancelada", "expirada", "finalizada"].includes(sala.estado_invitacion)) {
      clearInterval(state.pollEstado);
      state.finalizado = true;
      const mensajes = {
        rechazada: "El contacto rechazó la videollamada.",
        cancelada: "La invitación fue cancelada.",
        expirada: "La invitación expiró.",
        finalizada: "La videollamada finalizó.",
      };
      volverABandeja(mensajes[sala.estado_invitacion] || "La invitación ya no está disponible.");
    }
  }, 2000);
}

async function comenzarLlamada() {
  if (state.estado === "conectando" || state.estado === "en_llamada" || state.finalizado) return;
  state.estado = "conectando";
  setEstado("Solicitando cámara y micrófono…");

  try {
    await iniciarMediosLocales();
  } catch (err) {
    mostrarAlerta(err.message || "No se pudo acceder a cámara/micrófono.", 8000);
    setEstado("No se pudo iniciar la videollamada.", err.message || "");
    setBotonColgar("Volver");
    // La sala ya está aceptada: hay que cerrarla para no dejarla zombie.
    enviarSalida(true);
    limpiarRecursos();
    state.finalizado = true;
    clearTimeout(state.redirectTimer);
    state.redirectTimer = setTimeout(() => window.location.replace(BANDEJA), 8000);
    return;
  }

  await cargarIceServers();
  crearPeerConnection();
  setEstado("Conectando con el otro participante…");
  conectarSenalizacion();

  clearInterval(state.pingInterval);
  state.pingInterval = setInterval(() => {
    if (state.websocket && state.websocket.readyState === WebSocket.OPEN) {
      state.websocket.send(JSON.stringify({ type: "ping" }));
    }
  }, 25000);

  clearInterval(state.heartbeatInterval);
  state.heartbeatInterval = setInterval(() => {
    apiFetch("/heartbeat", { method: "POST" }).catch(() => {});
  }, 30000);
}

function limpiarRecursos() {
  clearInterval(state.pollEstado);
  clearInterval(state.httpSignalInterval);
  clearInterval(state.pingInterval);
  clearInterval(state.heartbeatInterval);
  clearTimeout(state.reconnectTimer);
  state.pollEstado = null;
  state.httpSignalInterval = null;
  state.pingInterval = null;
  state.heartbeatInterval = null;
  state.reconnectTimer = null;

  if (state.websocket) {
    try { state.websocket.close(); } catch (e) { /* no-op */ }
    state.websocket = null;
  }
  if (state.peerConnection) {
    try { state.peerConnection.close(); } catch (e) { /* no-op */ }
    state.peerConnection = null;
  }
  if (state.localStream) {
    state.localStream.getTracks().forEach((track) => {
      try { track.stop(); } catch (e) { /* no-op */ }
    });
    state.localStream = null;
  }
}

function enviarSalida(keepalive = false) {
  if (!state.codigoSala) return;
  const access = leerToken("access_token");
  if (!access) return;
  const endpoint = state.aceptada
    ? `/videoconferencia/salas/${encodeURIComponent(state.codigoSala)}/salir`
    : `/videoconferencia/salas/${encodeURIComponent(state.codigoSala)}/cancelar`;
  fetch(`${API}${endpoint}`, {
    method: "POST",
    headers: { "Authorization": `Bearer ${access}`, "Accept": "application/json" },
    keepalive,
  }).catch(() => {});
}

function finalizarLlamada(mensaje = "Videollamada finalizada.", notificar = true) {
  if (state.finalizado) return;
  state.finalizado = true;
  state.estado = "finalizada";
  limpiarRecursos();

  if (notificar) enviarSalida(false);

  setEstado(mensaje, "");
  setBotonColgar("Volver");
  $("#waiting-actions").hidden = true;
  const placeholder = $("#remote-placeholder");
  if (placeholder) placeholder.hidden = false;
  const remoteVideo = $("#remote-video");
  if (remoteVideo) remoteVideo.srcObject = null;

  clearTimeout(state.redirectTimer);
  state.redirectTimer = setTimeout(() => window.location.replace(BANDEJA), 1800);
}

/* ------------------------------------------------------------------ */
/* Controles                                                           */
/* ------------------------------------------------------------------ */

function toggleMic() {
  if (!state.localStream) return;
  state.micHabilitado = !state.micHabilitado;
  state.localStream.getAudioTracks().forEach((track) => { track.enabled = state.micHabilitado; });
  const btn = $("#btn-toggle-mic");
  if (!btn) return;
  btn.classList.toggle("off", !state.micHabilitado);
  btn.setAttribute("aria-pressed", String(state.micHabilitado));
  const icon = btn.querySelector(".icon");
  const lbl = btn.querySelector(".lbl");
  if (icon) icon.textContent = state.micHabilitado ? "🎤" : "🔇";
  if (lbl) lbl.textContent = state.micHabilitado ? "Micrófono" : "Silenciado";
}

function toggleCam() {
  if (!state.localStream) return;
  state.camHabilitada = !state.camHabilitada;
  state.localStream.getVideoTracks().forEach((track) => { track.enabled = state.camHabilitada; });
  const btn = $("#btn-toggle-cam");
  if (!btn) return;
  btn.classList.toggle("off", !state.camHabilitada);
  btn.setAttribute("aria-pressed", String(state.camHabilitada));
  const icon = btn.querySelector(".icon");
  const lbl = btn.querySelector(".lbl");
  if (icon) icon.textContent = state.camHabilitada ? "📹" : "🚫";
  if (lbl) lbl.textContent = state.camHabilitada ? "Cámara" : "Apagada";
}

/* ------------------------------------------------------------------ */
/* Arranque                                                            */
/* ------------------------------------------------------------------ */

async function iniciar() {
  if (!(await validarSesion())) {
    limpiarSesion();
    irALogin();
    return;
  }

  const cargada = await cargarSala();
  if (!cargada) return;

  if (state.sala.estado_invitacion === "aceptada") {
    await comenzarLlamada();
    return;
  }

  if (state.esIniciador && state.sala.estado_invitacion === "pendiente") {
    await esperarAceptacion();
    return;
  }

  state.finalizado = true;
  volverABandeja("Esta invitación no está disponible.");
}

$("#btn-colgar").addEventListener("click", () => {
  if (state.finalizado) {
    window.location.replace(BANDEJA);
    return;
  }
  finalizarLlamada("Has finalizado la videollamada.", true);
});
$("#btn-toggle-mic").addEventListener("click", toggleMic);
$("#btn-toggle-cam").addEventListener("click", toggleCam);

const btnCancelarEspera = $("#btn-cancelar-espera");
if (btnCancelarEspera) {
  btnCancelarEspera.addEventListener("click", () => {
    finalizarLlamada("Invitación cancelada.", true);
  });
}

const btnCopiar = $("#btn-copiar-sala");
if (btnCopiar) {
  btnCopiar.addEventListener("click", () => {
    if (state.codigoSala && navigator.clipboard) {
      navigator.clipboard.writeText(state.codigoSala)
        .then(() => mostrarAlerta("Código de sala copiado."))
        .catch(() => {});
    }
  });
}

window.addEventListener("beforeunload", () => {
  if (!state.finalizado && state.codigoSala) {
    enviarSalida(true);
  }
});

iniciar();
