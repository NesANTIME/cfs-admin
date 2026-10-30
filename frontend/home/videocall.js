"use strict";

const $ = (s) => document.querySelector(s);
const API = "/api";
const LOGIN = "../index.html";

const state = {
  usuario: null,
  codigoSala: null,
  contactoId: null,
  localStream: null,
  peerConnection: null,
  websocket: null,
  httpSignalInterval: null,
  micHabilitado: true,
  camHabilitada: true,
};

const ICE_SERVERS = {
  iceServers: [
    { urls: "stun:stun.l.google.com:19302" },
    { urls: "stun:stun1.l.google.com:19302" },
  ],
};

function leerToken(clave) {
  try { return sessionStorage.getItem(clave); } catch (e) { return null; }
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

async function validarSesion() {
  const res = await apiFetch("/me");
  if (!res || !res.ok) return false;
  state.usuario = await res.json();
  return true;
}

function mostrarAlerta(msg, duracion = 3000) {
  const el = $("#call-alert");
  if (!el) return;
  el.textContent = msg;
  el.hidden = false;
  setTimeout(() => { el.hidden = true; }, duracion);
}

/* ---- Captura de Medios Locales ---- */

async function iniciarMediosLocales() {
  const localVideo = $("#local-video");

  try {
    // Intentar acceder a cámara y micrófono reales
    state.localStream = await navigator.mediaDevices.getUserMedia({
      video: { width: 640, height: 480 },
      audio: true,
    });
    localVideo.srcObject = state.localStream;
  } catch (err) {
    console.warn("Dispositivo multimedia no disponible o bloqueado. Usando flujo simulado de prueba:", err);
    // Crear un stream simulado mediante canvas para permitir pruebas funcionales en navegadores sin cámara
    const canvas = document.createElement("canvas");
    canvas.width = 320;
    canvas.height = 240;
    const ctx = canvas.getContext("2d");
    let frame = 0;
    setInterval(() => {
      frame++;
      ctx.fillStyle = "#1e3a29";
      ctx.fillRect(0, 0, 320, 240);
      ctx.fillStyle = "#f6c945";
      ctx.font = "16px sans-serif";
      ctx.fillText(`Cámara CFS [Frame ${frame}]`, 20, 120);
      ctx.fillText(state.usuario ? state.usuario.nombre : "Usuario", 20, 150);
    }, 100);

    const videoStream = canvas.captureStream(15);
    state.localStream = videoStream;
    localVideo.srcObject = videoStream;
    mostrarAlerta("Modo de prueba: Transmitiendo video generado por el sistema.");
  }
}

/* ---- Inicialización de WebRTC ---- */

function crearPeerConnection() {
  const pc = new RTCPeerConnection(ICE_SERVERS);

  // Agregar tracks locales al peer
  if (state.localStream) {
    state.localStream.getTracks().forEach((track) => {
      pc.addTrack(track, state.localStream);
    });
  }

  // Recibir stream remoto
  pc.ontrack = (event) => {
    const remoteVideo = $("#remote-video");
    const placeholder = $("#remote-placeholder");
    if (event.streams && event.streams[0]) {
      remoteVideo.srcObject = event.streams[0];
      if (placeholder) placeholder.hidden = true;
      mostrarAlerta("Conectado con el participante remoto.");
    }
  };

  // Enviar candidatos ICE
  pc.onicecandidate = (event) => {
    if (event.candidate) {
      enviarSenal({ type: "candidate", candidate: event.candidate });
    }
  };

  pc.onconnectionstatechange = () => {
    const statusText = $("#call-status-text");
    if (statusText) {
      if (pc.connectionState === "connected") {
        statusText.textContent = "Conexión WebRTC establecida en tu sede.";
      } else if (pc.connectionState === "disconnected" || pc.connectionState === "failed") {
        statusText.textContent = "El contacto se ha desconectado.";
      }
    }
  };

  state.peerConnection = pc;
  return pc;
}

/* ---- Señalización (WebSocket + Fallback) ---- */

function conectarSenalizacion() {
  const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${wsProtocol}//${window.location.host}${API}/videoconferencia/ws/${state.codigoSala}`;

  try {
    const ws = new WebSocket(wsUrl);

    ws.onopen = async () => {
      console.log("[WS] Conectado a la sala:", state.codigoSala);
      crearPeerConnection();
      // Si el iniciador entra, envía una oferta WebRTC
      await iniciarLlamada();
    };

    ws.onmessage = async (event) => {
      try {
        const msg = JSON.parse(event.data);
        await procesarSenal(msg);
      } catch (e) {
        console.error("Error al procesar mensaje de señal:", e);
      }
    };

    ws.onerror = () => {
      console.warn("[WS] Error de WebSocket. Activando fallback de señalización HTTP.");
      iniciarFallbackHttp();
    };

    state.websocket = ws;
  } catch (e) {
    iniciarFallbackHttp();
  }
}

function iniciarFallbackHttp() {
  if (state.httpSignalInterval) return;
  crearPeerConnection();
  iniciarLlamada();

  state.httpSignalInterval = setInterval(async () => {
    try {
      const res = await apiFetch(`/videoconferencia/sala/${state.codigoSala}/signal`);
      if (res && res.ok) {
        const data = await res.json();
        for (const sig of data.signals || []) {
          await procesarSenal(sig);
        }
      }
    } catch (e) {}
  }, 1500);
}

function enviarSenal(senal) {
  if (state.websocket && state.websocket.readyState === WebSocket.OPEN) {
    state.websocket.send(JSON.stringify(senal));
  } else {
    apiFetch(`/videoconferencia/sala/${state.codigoSala}/signal`, {
      method: "POST",
      body: JSON.stringify(senal),
    }).catch(() => {});
  }
}

async function procesarSenal(msg) {
  const pc = state.peerConnection;
  if (!pc) return;

  if (msg.type === "offer") {
    await pc.setRemoteDescription(new RTCSessionDescription(msg.offer));
    const answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);
    enviarSenal({ type: "answer", answer: answer });
  } else if (msg.type === "answer") {
    await pc.setRemoteDescription(new RTCSessionDescription(msg.answer));
  } else if (msg.type === "candidate" && msg.candidate) {
    try {
      await pc.addIceCandidate(new RTCIceCandidate(msg.candidate));
    } catch (e) {}
  } else if (msg.type === "peer_disconnected") {
    mostrarAlerta("El contacto ha salido de la llamada.");
    const placeholder = $("#remote-placeholder");
    if (placeholder) placeholder.hidden = false;
    $("#call-status-text").textContent = "Llamada finalizada por el contacto.";
  }
}

async function iniciarLlamada() {
  const pc = state.peerConnection;
  if (!pc) return;

  try {
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    enviarSenal({ type: "offer", offer: offer });
  } catch (err) {
    console.error("Error al crear oferta WebRTC:", err);
  }
}

/* ---- Gestión de Sala ---- */

async function obtenerOCrearSala() {
  const params = new URLSearchParams(window.location.search);
  let codigo = params.get("codigo_sala") || params.get("sala_id");
  const contactoId = params.get("contacto_id");

  if (codigo) {
    state.codigoSala = codigo;
    const res = await apiFetch(`/videoconferencia/sala/${codigo}`);
    if (res && res.ok) {
      const datos = await res.json();
      $("#call-room-code").textContent = `Sala: #${datos.codigo_sala}`;
      return true;
    }
  }

  // Crear una nueva sala
  try {
    const res = await apiFetch("/videoconferencia/sala", {
      method: "POST",
      body: JSON.stringify({ id_contacto: contactoId ? parseInt(contactoId, 10) : null }),
    });

    if (res && res.ok) {
      const sala = await res.json();
      state.codigoSala = sala.codigo_sala;
      $("#call-room-code").textContent = `Sala: #${sala.codigo_sala}`;
      return true;
    } else {
      const err = await (res ? res.json().catch(() => ({})) : {});
      alert(err.detail || "No se pudo iniciar la sala. Verifica que tu servicio de videoconferencia esté habilitado.");
      window.history.back();
      return false;
    }
  } catch (e) {
    alert("Error de conexión al crear sala.");
    window.history.back();
    return false;
  }
}

function finalizarLlamada() {
  if (state.localStream) {
    state.localStream.getTracks().forEach((t) => t.stop());
  }
  if (state.peerConnection) {
    state.peerConnection.close();
  }
  if (state.websocket) {
    state.websocket.close();
  }
  if (state.httpSignalInterval) {
    clearInterval(state.httpSignalInterval);
  }

  if (state.codigoSala) {
    apiFetch(`/videoconferencia/sala/${state.codigoSala}/finalizar`, { method: "POST" }).catch(() => {});
  }

  if (state.usuario && state.usuario.tipo_admin === "usuario") {
    window.location.replace("usuario.html");
  } else {
    window.location.replace("index.html");
  }
}

/* ---- Controles Multimedia ---- */

function toggleMic() {
  if (!state.localStream) return;
  state.micHabilitado = !state.micHabilitado;
  state.localStream.getAudioTracks().forEach((track) => {
    track.enabled = state.micHabilitado;
  });

  const btn = $("#btn-toggle-mic");
  if (state.micHabilitado) {
    btn.classList.remove("off");
    btn.querySelector(".icon").textContent = "🎤";
    btn.querySelector(".lbl").textContent = "Micrófono";
  } else {
    btn.classList.add("off");
    btn.querySelector(".icon").textContent = "🔇";
    btn.querySelector(".lbl").textContent = "Silenciado";
  }
}

function toggleCam() {
  if (!state.localStream) return;
  state.camHabilitada = !state.camHabilitada;
  state.localStream.getVideoTracks().forEach((track) => {
    track.enabled = state.camHabilitada;
  });

  const btn = $("#btn-toggle-cam");
  if (state.camHabilitada) {
    btn.classList.remove("off");
    btn.querySelector(".icon").textContent = "📹";
    btn.querySelector(".lbl").textContent = "Cámara";
  } else {
    btn.classList.add("off");
    btn.querySelector(".icon").textContent = "🚫";
    btn.querySelector(".lbl").textContent = "Apagada";
  }
}

/* Eventos */
$("#btn-colgar").addEventListener("click", finalizarLlamada);
$("#btn-toggle-mic").addEventListener("click", toggleMic);
$("#btn-toggle-cam").addEventListener("click", toggleCam);

$("#btn-copiar-sala").addEventListener("click", () => {
  if (state.codigoSala && navigator.clipboard) {
    navigator.clipboard.writeText(state.codigoSala).then(() => {
      mostrarAlerta("¡Código de sala copiado al portapapeles!");
    });
  }
});

/* ---- Arranque ---- */
async function iniciar() {
  if (!(await validarSesion())) {
    irALogin();
    return;
  }

  const okSala = await obtenerOCrearSala();
  if (!okSala) return;

  await iniciarMediosLocales();
  conectarSenalizacion();

  // Heartbeat continuo
  setInterval(() => {
    apiFetch("/heartbeat", { method: "POST" }).catch(() => {});
  }, 30000);
}

iniciar();
