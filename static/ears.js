// Mythree's ears in the browser.
// Listens to the microphone, notices when the speaker pauses, and sends
// each sentence (as a small WAV file) to the server, which asks Meta's ears.

const PAUSE_MS = 700;        // this much quiet ends a sentence
const MIN_SPEECH_MS = 400;   // shorter sounds (a cough, a click) are ignored
const MAX_SENTENCE_MS = 15000;
const PRE_ROLL_MS = 300;     // keep a little sound from just before the voice started
const TARGET_RATE = 16000;   // Meta wants 16 kHz

const ui = {
  start: document.getElementById("start"),
  mood: document.getElementById("mood"),
  heard: document.getElementById("heard"),
  langs: document.querySelectorAll("[data-lang]"),
};
let lang = "te";
let ctx, stream, node;

ui.langs.forEach((b) => b.addEventListener("click", () => {
  lang = b.dataset.lang;
  ui.langs.forEach((x) => x.setAttribute("aria-pressed", x === b));
}));

function setMood(name, text) {
  ui.mood.className = "mood " + name;
  ui.mood.textContent = text;
}

ui.start.addEventListener("click", () => (ctx ? stop() : start()));

async function start() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
    });
  } catch {
    setMood("error", "Microphone not allowed · మైక్ అనుమతి ఇవ్వండి");
    return;
  }
  ctx = new AudioContext();
  const source = ctx.createMediaStreamSource(stream);
  node = ctx.createScriptProcessor(4096, 1, 1);
  source.connect(node);
  node.connect(ctx.destination);
  node.onaudioprocess = (e) => listen(new Float32Array(e.inputBuffer.getChannelData(0)));
  ui.start.textContent = "Stop listening";
  setMood("listening", "Listening… · వింటున్నాను…");
}

function stop() {
  node.disconnect();
  stream.getTracks().forEach((t) => t.stop());
  ctx.close();
  ctx = null;
  reset();
  ui.start.textContent = "Start listening";
  setMood("sleeping", "Sleeping · నిద్రపోతున్నాను");
}

// --- Finding sentences ------------------------------------------------------
let noise = 0.01, speaking = false, chunks = [], preRoll = [], speechMs = 0, quietMs = 0;

function reset() {
  speaking = false; chunks = []; preRoll = []; speechMs = 0; quietMs = 0;
}

function listen(chunk) {
  const ms = (chunk.length / ctx.sampleRate) * 1000;
  const level = Math.sqrt(chunk.reduce((s, x) => s + x * x, 0) / chunk.length);
  const loud = level > Math.max(0.015, noise * 3);

  if (!speaking) {
    noise = noise * 0.95 + level * 0.05;   // learn how quiet the room is
    preRoll.push(chunk);
    while (preRoll.length * ms > PRE_ROLL_MS) preRoll.shift();
    if (loud) {
      speaking = true;
      chunks = [...preRoll];
      setMood("hearing", "Hearing you… · వింటున్నాను…");
    }
    return;
  }
  chunks.push(chunk);
  speechMs += ms;
  quietMs = loud ? 0 : quietMs + ms;
  if (quietMs >= PAUSE_MS || speechMs >= MAX_SENTENCE_MS) {
    const sentence = chunks, long = speechMs - quietMs;
    reset();
    setMood("listening", "Listening… · వింటున్నాను…");
    if (long >= MIN_SPEECH_MS) send(sentence, ctx.sampleRate);
  }
}

// --- Sending a sentence -----------------------------------------------------
async function send(sentence, rate) {
  const line = document.createElement("li");
  line.className = "thinking";
  line.textContent = "…";
  ui.heard.prepend(line);
  const form = new FormData();
  form.append("audio", toWav(sentence, rate), "sentence.wav");
  form.append("lang", lang);
  try {
    const reply = await fetch("/api/hear", { method: "POST", body: form });
    const data = await reply.json();
    if (!reply.ok) throw new Error(data.detail);
    line.lang = data.lang;
    line.textContent = data.text || "(nothing heard)";
    line.className = "";
  } catch (err) {
    line.textContent = err.message || "Mythree couldn't hear that. Please say it again.";
    line.className = "error";
  }
}

// Join the pieces, bring them down to 16 kHz, and wrap them in a plain WAV header.
function toWav(pieces, rate) {
  const all = new Float32Array(pieces.reduce((n, p) => n + p.length, 0));
  let at = 0;
  for (const p of pieces) { all.set(p, at); at += p.length; }

  const step = rate / TARGET_RATE;
  const count = Math.floor(all.length / step);
  const pcm = new Int16Array(count);
  for (let i = 0; i < count; i++) {
    const from = Math.floor(i * step), to = Math.floor((i + 1) * step);
    let sum = 0;
    for (let j = from; j < to; j++) sum += all[j];
    const x = Math.max(-1, Math.min(1, sum / (to - from)));
    pcm[i] = x * 32767;
  }

  const head = new DataView(new ArrayBuffer(44));
  const text = (at, s) => [...s].forEach((c, i) => head.setUint8(at + i, c.charCodeAt(0)));
  text(0, "RIFF"); head.setUint32(4, 36 + pcm.byteLength, true); text(8, "WAVE");
  text(12, "fmt "); head.setUint32(16, 16, true); head.setUint16(20, 1, true);
  head.setUint16(22, 1, true); head.setUint32(24, TARGET_RATE, true);
  head.setUint32(28, TARGET_RATE * 2, true); head.setUint16(32, 2, true); head.setUint16(34, 16, true);
  text(36, "data"); head.setUint32(40, pcm.byteLength, true);
  return new Blob([head, pcm], { type: "audio/wav" });
}
