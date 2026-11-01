// Try Mythree: speak any language, hear yourself speak any other, even in your own voice.
// 1. Choose "I speak" (or let Meta find it) and "Hear it in". Tap the mic, speak, tap again: Meta's ears
//    hear it, the brain translates it, and a ready-made voice says it. 🔁 plays it again, free.
// 2. If they like it: the visitor records about 20 seconds (with consent), Mythree copies the voice for
//    one hour, and says their last sentence again, now as them.

const TARGET_RATE = 16000;   // Meta wants 16 kHz
const RECORD_S = 21, SHOWN_S = 20, MAX_SENTENCE_S = 30;   // records 21 s, shows 20: a little spare, so it's never short
const $ = (id) => document.getElementById(id);

// --- Talking to the server (open to everyone, no passcode) ------------------
const api = (url, options = {}) => fetch(url, options);
async function problemOf(reply) {
  try { return (await reply.json()).detail || "Something went wrong."; } catch { return "Something went wrong."; }
}

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

// --- The two language lists (from the server, so the page and the server always agree) ---
let voiceCode = {};   // language → its voice code, or null when Mythree can only show it in writing

function fill(select, groups, first) {
  select.replaceChildren();
  if (first) select.append(new Option(first, ""));
  for (const [label, list] of groups) {
    const group = document.createElement("optgroup");
    group.label = label;
    for (const l of list) {
      const name = l.native === l.name ? l.name : `${l.native} · ${l.name}`;
      group.append(new Option(select.id === "to" && !l.code ? `${name} (read only)` : name, l.name));
    }
    select.append(group);
  }
}

function remembered(key, fallback) {
  try { return localStorage.getItem(key) || fallback; } catch { return fallback; }   // private window
}
function remember(key, value) {
  try { localStorage.setItem(key, value); } catch { /* private window */ }
}

async function loadLanguages() {
  const { india, world } = await (await api("/api/try/languages")).json();
  for (const l of [...india, ...world]) voiceCode[l.name] = l.code;
  const groups = [["India's 22 languages", india], ["The world", world]];
  fill($("language"), groups, "✨ Let Meta find my language");
  fill($("to"), groups);
  const from = remembered("mythree-try-language", "");
  $("language").value = from in voiceCode ? from : "";
  const to = remembered("mythree-try-to", "English");
  $("to").value = to in voiceCode ? to : "English";
  showPassage();
}
loadLanguages();

$("language").addEventListener("change", () => { remember("mythree-try-language", $("language").value); showPassage(); });
$("to").addEventListener("change", () => remember("mythree-try-to", $("to").value));
$("swap").addEventListener("click", () => {
  const from = $("language").value, to = $("to").value;
  $("language").value = to;
  $("to").value = from && from !== to ? from : to === "English" ? "Hindi" : "English";
  remember("mythree-try-language", $("language").value);
  remember("mythree-try-to", $("to").value);
  showPassage();
});

// --- Step 2 (if they like it): your voice ----------------------------------------
let myVoice = "", recording = null;
let last = null;   // the last sentence heard ({line, text, to}), said again in the visitor's voice once it's ready

function showPassage() {   // a passage in the visitor's language, or "talk freely"
  $("passage").textContent = PASSAGES[$("language").value] ?? PASSAGES[""];
}

$("want-voice").addEventListener("click", () => {
  unlockSound();
  $("offer").hidden = true;
  $("step-voice").hidden = false;
  $("step-voice").scrollIntoView({ behavior: "smooth", block: "start" });
});

$("skip").addEventListener("click", () => {
  $("step-voice").hidden = true;
  $("offer").hidden = false;
  $("step-talk").scrollIntoView({ behavior: "smooth", block: "start" });
});

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
  if (!$("consent").checked) return ($("voice-problem").textContent = "Tick the box to agree, then tap Start.");
  $("voice-problem").textContent = "";
  try {
    recording = await record((s) => {
      $("rec-time").textContent = clock(Math.max(0, SHOWN_S - s));
      $("rec-bar").style.width = `${Math.min(100, (s / SHOWN_S) * 100)}%`;
    }, RECORD_S);
  } catch {
    $("mic-help").open = true;
    return ($("voice-problem").textContent = "Mythree can't use your microphone yet. See how to allow it in step 1.");
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

let lastWav = null;   // the visitor's 20 seconds, kept on this phone, so "Try my own voice again" needs no re-reading

async function lendVoice(wav) {
  const form = new FormData();
  form.append("audio", wav, "voice.wav");
  form.append("consent", "true");
  return api("/api/try/voice", { method: "POST", body: form });
}

async function learn(wav) {
  lastWav = wav;
  $("rec").textContent = "Learning your voice… (about 5 seconds)";
  const reply = await lendVoice(wav);
  $("rec").textContent = "● Start reading";
  $("rec-bar").style.width = "0";
  if (reply.status === 503) {   // all voice places in use: go on with a standard voice, and offer to try again later
    backToTalk(await problemOf(reply));
    $("retry-voice").hidden = false;
    return;
  }
  if (!reply.ok) return ($("voice-problem").textContent = (await problemOf(reply)) + " You can also go on with a standard voice.");
  voiceReady((await reply.json()).voice);
}

$("retry-voice").addEventListener("click", async () => {
  $("retry-voice").hidden = true;
  $("voice-note").textContent = "Learning your voice… (about 5 seconds)";
  const reply = await lendVoice(lastWav);
  if (!reply.ok) {
    $("voice-note").textContent = await problemOf(reply);
    $("retry-voice").hidden = false;
    return;
  }
  voiceReady((await reply.json()).voice);
});

function backToTalk(note) {
  $("step-voice").hidden = true;
  $("voice-note").textContent = note;
  $("step-talk").scrollIntoView({ behavior: "smooth", block: "start" });
}

// The wow: as soon as the voice is learned, Mythree says the last sentence again, as the visitor.
function voiceReady(id) {
  myVoice = id;
  $("step-done").hidden = false;
  if (last) {
    backToTalk("🎉 Your voice is ready. Listen: your last sentence, now in your own voice!");
    speak(last.line, last.text, last.to);
  } else {
    backToTalk("🎉 Your voice is ready. Listen: that's you!");
    greet();
  }
}

async function greet() {
  const reply = await api(`/api/try/hello/${myVoice}`, { method: "POST" });
  if (reply.ok) play(URL.createObjectURL(await reply.blob()));
}

$("forget").addEventListener("click", async () => {
  await api(`/api/try/voice/${myVoice}`, { method: "DELETE" });
  myVoice = "";
  $("step-done").hidden = true;
  $("voice-note").textContent = "Your voice copy is deleted. Thank you for trying Mythree! (From now on you'll hear a standard voice.)";
});

// Closing or leaving the page deletes the voice copy too ("keepalive" lets the request finish after
// the page is gone). If even that fails, it is deleted after one hour anyway.
window.addEventListener("pagehide", () => {
  if (!myVoice) return;
  fetch(`/api/try/voice/${myVoice}`, { method: "DELETE", keepalive: true });
  myVoice = "";
});

// --- Step 1: talk, and hear it in the language you chose -------------------------
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
    $("mic-help").open = true;
    return ($("talk-problem").textContent = "Mythree can't use your microphone. See how to allow it just below, then reload.");
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
  line.innerHTML = '<div class="said" dir="auto"></div><div class="translation" dir="auto"></div>'
                 + '<div class="status">Hearing and translating… (a few seconds)</div><div class="meta-work"></div>';
  $("lines").prepend(line);
  const to = $("to").value || "English";
  const form = new FormData();
  form.append("audio", wav, "sentence.wav");
  form.append("language", $("language").value);   // told to the ears, so Telugu isn't written in Kannada letters
  form.append("to", to);
  const reply = await api("/api/try/heard", { method: "POST", body: form });
  const status = line.querySelector(".status");
  if (!reply.ok) { status.textContent = await problemOf(reply); return; }
  const { text, translation, meta } = await reply.json();
  metaAtWork(line.querySelector(".meta-work"), meta);
  if (!text) {
    status.textContent = "Mythree didn't hear any words. Speak a little louder, for a few seconds, then tap the red button.";
    return;
  }
  line.querySelector(".said").textContent = text;
  line.querySelector(".translation").textContent = translation;
  last = { line, text: translation, to };
  await speak(line, translation, to);
  if (!myVoice && $("step-voice").hidden) $("offer").hidden = false;
}

// "Meta at work", for the hackathon demo: which Meta model heard the sentence, which translated it, and how fast.
const META_JOBS = { hear: ["👂", "heard"], translate: ["🧠", "translated"] };

function metaAtWork(box, work) {
  for (const w of work || []) {
    const [icon, did] = META_JOBS[w.job] || ["✨", "worked"];
    const where = w.where === "on Baseten" ? " on Baseten" : w.where === "Meta API" ? " (Meta API)" : "";
    const row = document.createElement("div");
    row.textContent = `${icon} Meta · ${w.model}${where} · ${did} in ${w.s} s`;
    box.append(row);
  }
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

async function speak(line, text, to) {
  const status = line.querySelector(".status");
  const code = voiceCode[to];
  if (!code) { status.textContent = `Mythree has no voice for ${to} yet. Read it above!`; return; }
  status.textContent = myVoice ? "Speaking in your voice…" : "Speaking…";
  let again = () => standardVoice(text, code);
  const reply = await api("/api/try/speak", { method: "POST", headers: { "Content-Type": "application/json" },
                                              body: JSON.stringify({ text, voice: myVoice, language: to }) });
  if (reply.ok) {
    const sound = URL.createObjectURL(await reply.blob());
    again = () => play(sound);
  } else if (reply.status === 503) {   // Mythree's voices are resting (today's share is used): the phone speaks
    $("voice-note").textContent = await problemOf(reply);
  }
  line.querySelector(".replay")?.remove();   // said again in the visitor's own voice: the new one replaces it
  const button = document.createElement("button");
  button.className = "replay";
  button.textContent = "🔁";
  button.setAttribute("aria-label", "Hear it again");
  button.addEventListener("click", () => { unlockSound(); again(); });
  line.prepend(button);
  again();
  status.textContent = "";
}

function play(src) {
  voice.src = src;
  return voice.play().catch(() => {});
}

function standardVoice(text, code) {   // the browser's own voice, when Mythree's voices are resting
  if (!window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const words = new SpeechSynthesisUtterance(text);
  words.lang = code;
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
