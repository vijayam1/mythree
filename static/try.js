// Try Mythree: speak any language, hear yourself speak English, in your own voice.
// 1. The visitor records about 20 seconds (with consent); Mythree copies the voice for one hour.
// 2. Tap the mic, speak, tap again: Meta's ears find the language, the brain makes it English,
//    and the visitor hears it in their own voice. 🔁 plays it again, free.

const TARGET_RATE = 16000;   // Meta wants 16 kHz
const RECORD_S = 21, SHOWN_S = 20, MAX_SENTENCE_S = 30;   // records 21 s, shows 20: a little spare, so it's never short
const $ = (id) => document.getElementById(id);

// --- Passcode (the same one testers get for Mythree) ---------------------------
let passcode = (() => { try { return localStorage.getItem("mythree-passcode") || ""; } catch { return ""; } })();

async function api(url, options = {}) {
  options.headers = { ...(options.headers || {}), "X-Mythree-Passcode": passcode };
  const reply = await fetch(url, options);
  if (reply.status !== 401) return reply;
  const typed = prompt("Mythree passcode (from the hackathon post)");
  if (!typed) return reply;
  passcode = typed.trim();
  try { localStorage.setItem("mythree-passcode", passcode); } catch { /* private window */ }
  return api(url, options);
}
async function problemOf(reply) {
  try { return (await reply.json()).detail || "Something went wrong."; } catch { return "Something went wrong."; }
}
api("/api/hello");   // ask for the passcode right away

// --- Recording from the microphone ---------------------------------------------
async function record(onTick, seconds) {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 } });
  const ctx = new AudioContext();
  const node = ctx.createScriptProcessor(4096, 1, 1);
  const pieces = [];
  node.onaudioprocess = (e) => pieces.push(new Float32Array(e.inputBuffer.getChannelData(0)));
  ctx.createMediaStreamSource(stream).connect(node);
  node.connect(ctx.destination);
  const began = Date.now();
  let stopped = false;
  const tick = setInterval(() => {
    const s = (Date.now() - began) / 1000;
    onTick(s);
    if (s >= seconds) finish();
  }, 200);
  let done;
  const result = new Promise((ok) => (done = ok));
  function finish() {
    if (stopped) return;
    stopped = true;
    clearInterval(tick);
    node.disconnect();
    stream.getTracks().forEach((t) => t.stop());
    const rate = ctx.sampleRate;
    ctx.close();
    done({ wav: toWav(pieces, rate), seconds: (Date.now() - began) / 1000 });
  }
  return { finish, result };
}

const clock = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

// --- Step 1: your voice --------------------------------------------------------
let myVoice = "", recording = null;

// The visitor chooses a language and sees a passage to read; the recording stops by itself.
const chosen = () => ($("language").value === "pick" ? "" : $("language").value);

function showPassage() {
  const pick = $("language").value;
  if (pick !== "pick") $("voice-problem").textContent = "";
  $("passage-box").hidden = pick === "pick";
  $("passage").textContent = PASSAGES[pick] ?? "";
  $("passage").dir = RIGHT_TO_LEFT.has(pick) ? "rtl" : "ltr";
  try { localStorage.setItem("mythree-try-language", pick); } catch { /* private window */ }
}
try { $("language").value = localStorage.getItem("mythree-try-language") || "pick"; } catch { /* private window */ }
if (!$("language").value) $("language").value = "pick";
$("language").addEventListener("change", showPassage);
showPassage();

$("rec").addEventListener("click", async () => {
  unlockSound();
  if (recording) {   // tapped while recording: start over
    const stopping = recording;
    recording = null;
    stopping.finish();
    $("rec").classList.remove("on");
    $("rec").textContent = "● Start reading";
    $("rec-time").textContent = "0:20";
    $("rec-bar").style.width = "0";
    return;
  }
  if ($("language").value === "pick") return ($("voice-problem").textContent = "First choose your language above.");
  if (!$("consent").checked) return ($("voice-problem").textContent = "Tick the box to agree, then tap Start.");
  $("voice-problem").textContent = "";
  try {
    recording = await record((s) => {
      $("rec-time").textContent = clock(Math.max(0, SHOWN_S - s));
      $("rec-bar").style.width = `${Math.min(100, (s / SHOWN_S) * 100)}%`;
    }, RECORD_S);
  } catch {
    $("mic-help").open = true;
    return ($("voice-problem").textContent = "Mythree can't use your microphone yet. See how to allow it, just below.");
  }
  $("rec").classList.add("on");
  $("rec").textContent = "Reading… (tap to start over)";
  const mine = recording;
  mine.result.then(({ wav }) => {   // 20 seconds done: it stops by itself
    if (recording !== mine) return;   // started over
    recording = null;
    $("rec").classList.remove("on");
    learn(wav);
  });
});

async function learn(wav) {
  $("rec").textContent = "Learning your voice… (about 5 seconds)";
  const form = new FormData();
  form.append("audio", wav, "voice.wav");
  form.append("consent", "true");
  const reply = await api("/api/try/voice", { method: "POST", body: form });
  $("rec").textContent = "● Start recording";
  if (reply.status === 503) return showTalk(await problemOf(reply));   // all voice places in use: go on with a standard voice
  if (!reply.ok) return ($("voice-problem").textContent = (await problemOf(reply)) + " You can also use a standard voice.");
  myVoice = (await reply.json()).voice;
  $("rec-bar").style.width = "0";
  showTalk("🎉 Your voice is ready. Listen: that's you, speaking English!");
  greet();
}

// The first wow: as soon as the voice is learned, Mythree says hello in English, in that voice.
async function greet() {
  const reply = await api(`/api/voices/${myVoice}/hello?lang=en`, { method: "POST" });
  if (reply.ok) play(URL.createObjectURL(await reply.blob()));
}

$("skip").addEventListener("click", () => { unlockSound(); showTalk("You'll hear a standard voice (not your own)."); });

function showTalk(note) {
  $("step-voice").hidden = true;
  $("step-talk").hidden = false;
  $("voice-note").textContent = note;
  const name = $("language").selectedOptions[0]?.text;
  $("lang-note").textContent = chosen() ? `Your language: ${name}` : "Mythree will find your language by itself.";
  $("step-done").hidden = !myVoice;
}

$("forget").addEventListener("click", async () => {
  await api(`/api/voices/${myVoice}`, { method: "DELETE" });
  myVoice = "";
  $("step-done").hidden = true;
  $("voice-note").textContent = "Your voice copy is deleted. Thank you for trying Mythree! (From now on you'll hear a standard voice.)";
});

// Closing or leaving the page deletes the voice copy too ("keepalive" lets the request finish after
// the page is gone). If even that fails, it is deleted after one hour anyway.
window.addEventListener("pagehide", () => {
  if (!myVoice) return;
  fetch(`/api/voices/${myVoice}`, { method: "DELETE", keepalive: true, headers: { "X-Mythree-Passcode": passcode } });
  myVoice = "";
});

// --- Step 2: talk, and hear it in English ---------------------------------------
let talking = null;

$("mic").addEventListener("click", async () => {
  unlockSound();
  if (talking) {   // second tap: send it
    const stopping = talking;
    talking = null;
    stopping.finish();
    const { wav } = await stopping.result;
    showMic(false);
    return send(wav);
  }
  $("talk-problem").textContent = "";
  try {
    talking = await record(() => {}, MAX_SENTENCE_S);
  } catch {
    return ($("talk-problem").textContent = "Mythree can't use your microphone. Allow it in your browser (see step 1's help), then reload.");
  }
  showMic(true);
  talking.result.then(({ wav }) => { if (talking) { talking = null; showMic(false); send(wav); } });
});

function showMic(on) {
  $("mic").classList.toggle("on", on);
  $("mic").textContent = on ? "⏹" : "🎙️";
  $("mic-label").textContent = on ? "Listening… speak now, then tap the red button" : "Tap to start talking";
}

async function send(wav) {
  const line = document.createElement("li");
  line.innerHTML = '<div class="said"></div><div class="english"></div><div class="status">Hearing and translating… (a few seconds)</div>';
  $("lines").prepend(line);
  const form = new FormData();
  form.append("audio", wav, "sentence.wav");
  form.append("language", chosen());   // told to the ears, so Telugu isn't written in Kannada letters
  const reply = await api("/api/try/heard", { method: "POST", body: form });
  const status = line.querySelector(".status");
  if (!reply.ok) { status.textContent = await problemOf(reply); return; }
  const { text, english } = await reply.json();
  if (!text) {
    status.textContent = "Mythree didn't hear any words. Speak a little louder, for a few seconds, then tap the red button.";
    return;
  }
  line.querySelector(".said").textContent = text;
  line.querySelector(".english").textContent = english;
  status.textContent = myVoice ? "Speaking in your voice…" : "";
  await speak(line, english);
  status.textContent = "";
}

// --- Speaking: the visitor's own voice, or a standard one -------------------------
const voice = new Audio();
let unlocked = false;

function unlockSound() {   // phones play sound only after a tap
  if (unlocked) return;
  unlocked = true;
  voice.src = URL.createObjectURL(toWav([new Float32Array(1600)], TARGET_RATE));
  voice.play().catch(() => { unlocked = false; });
}

async function speak(line, english) {
  let again = () => standardVoice(english);
  if (myVoice) {
    const reply = await api("/api/try/speak", { method: "POST", headers: { "Content-Type": "application/json" },
                                                body: JSON.stringify({ text: english, voice: myVoice }) });
    if (reply.ok) {
      const sound = URL.createObjectURL(await reply.blob());
      again = () => play(sound);
    }
  }
  const button = document.createElement("button");
  button.className = "replay";
  button.textContent = "🔁";
  button.setAttribute("aria-label", "Hear it again");
  button.addEventListener("click", () => { unlockSound(); again(); });
  line.prepend(button);
  again();
}

function play(src) {
  voice.src = src;
  return voice.play().catch(() => {});
}

function standardVoice(text) {
  if (!window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const words = new SpeechSynthesisUtterance(text);
  words.lang = "en-US";
  window.speechSynthesis.speak(words);
}

// --- A plain WAV file (16 kHz, 16-bit, mono), the format Meta's ears want ----------
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
    pcm[i] = Math.max(-1, Math.min(1, sum / (to - from))) * 32767;
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
