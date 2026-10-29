// Mythree as its own call: each person on their own phone, in their own language.
// This phone listens to its own person, sends each sentence to be heard and
// translated, and speaks what the other person said, in that person's own voice.
// The laptop page (index.html, ears.js) is separate and unchanged.

const PAUSE_MS = 1400;       // this much quiet ends a sentence
const MIN_SPEECH_MS = 400;   // shorter sounds (a cough, a click) are ignored
const MAX_SENTENCE_MS = 25000;
const PRE_ROLL_MS = 300;     // keep a little sound from just before the voice started
const TARGET_RATE = 16000;   // Meta wants 16 kHz
const QUIET_STOP_MS = 3 * 60 * 1000;   // nobody spoke for 3 minutes: stop listening

const $ = (id) => document.getElementById(id);
const RELATION_WORDS = { grandfather: "the grandfather", grandmother: "the grandmother", grandson: "the grandson",
  granddaughter: "the granddaughter", father: "the father", mother: "the mother", son: "the son",
  daughter: "the daughter", friend: "a friend" };

// --- Passcode (online only) --------------------------------------------------
let passcode = (() => { try { return localStorage.getItem("mythree-passcode") || ""; } catch { return ""; } })();

async function api(url, options = {}) {
  options.headers = { ...(options.headers || {}), "X-Mythree-Passcode": passcode };
  const reply = await fetch(url, options);
  if (reply.status !== 401) return reply;
  const typed = prompt("Mythree passcode · పాస్‌కోడ్");
  if (!typed) return reply;
  passcode = typed.trim();
  try { localStorage.setItem("mythree-passcode", passcode); } catch { /* private window */ }
  return api(url, options);
}
const postJson = (url, body) => api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
async function problemOf(reply) {
  try { return (await reply.json()).detail || "Something went wrong."; } catch { return "Something went wrong."; }
}
api("/api/hello");   // ask for the passcode right away

// --- Who am I (remembered on this phone) --------------------------------------
const saved = (() => { try { return JSON.parse(localStorage.getItem("mythree-me")) || {}; } catch { return {}; } })();
if (saved.relation) $("relation").value = saved.relation;
if (saved.name) $("name").value = saved.name;
if (saved.lang) $("lang").value = saved.lang;
let myVoice = saved.voice || "";   // the ID of the voice I recorded (it stays on this phone)
const fromLink = new URLSearchParams(location.search).get("code");
if (fromLink) $("code").value = fromLink;

function me() {
  const relation = $("relation").value, name = $("name").value.trim(), lang = $("lang").value;
  try { localStorage.setItem("mythree-me", JSON.stringify({ relation, name, lang, voice: myVoice })); } catch { /* private window */ }
  const role = RELATION_WORDS[relation] || "a family member";
  return { who: name ? `${name}, ${role}` : role, lang, voice: myVoice };
}

// --- Starting or joining a call ----------------------------------------------
let call = null;   // { code, person, lang, people, after }

$("start-call").addEventListener("click", async () => {
  unlockSound();
  const mine = me();
  const reply = await postJson("/api/calls", mine);
  if (!reply.ok) return ($("problem").textContent = await problemOf(reply));
  const { code, person } = await reply.json();
  enter(code, person, mine.lang);
});

$("join-call").addEventListener("click", async () => {
  unlockSound();
  const code = $("code").value.trim();
  if (!/^\d{4}$/.test(code)) return ($("problem").textContent = "Please type the 4-digit code · 4 అంకెల కోడ్");
  const mine = me();
  const reply = await postJson(`/api/calls/${code}/join`, mine);
  if (!reply.ok) return ($("problem").textContent = await problemOf(reply));
  const { person } = await reply.json();
  enter(code, person, mine.lang);
});

function enter(code, person, lang) {
  call = { code, person, lang, people: {}, after: 0 };
  shown.clear();
  $("problem").textContent = "";
  $("setup").hidden = true;
  $("call").hidden = false;
  $("end").hidden = false;
  history.replaceState(null, "", `/phone?code=${code}`);
  showStatus();
  follow(call);
}

$("end").addEventListener("click", () => {
  if (ctx) stop();
  hush();
  call = null;
  $("talk").replaceChildren();
  $("call").hidden = true;
  $("end").hidden = true;
  $("setup").hidden = false;
  history.replaceState(null, "", "/phone");
});

const them = () => call && call.people[call.person === "a" ? "b" : "a"];

function showStatus(note) {
  const box = $("status");
  if (note) { box.textContent = note; return; }
  const other = them();
  if (other) {
    box.textContent = `Talking with ${other.who} · మాట్లాడుతున్నారు`;
    return;
  }
  box.innerHTML = "";
  box.append("Share this code · ఈ కోడ్ పంపండి", document.createElement("br"));
  const code = document.createElement("strong");
  code.textContent = call.code;
  box.append(code, document.createElement("br"));
  const share = document.createElement("button");
  share.className = "plain";
  share.textContent = "Send the link · లింక్ పంపండి";
  share.addEventListener("click", () => shareLink());
  box.append(share);
}

async function shareLink() {
  const link = `${location.origin}/phone?code=${call.code}`;
  const text = `Join me on Mythree · మైత్రిలో చేరండి: ${link}`;
  try {
    if (navigator.share) await navigator.share({ title: "Mythree", text, url: link });
    else { await navigator.clipboard.writeText(link); showStatus("Link copied · లింక్ కాపీ అయింది"); setTimeout(() => showStatus(), 2000); }
  } catch { /* the person closed the share sheet */ }
}

// --- Waiting for news from the other phone -----------------------------------
// The phone asks "anything new?" and the server answers as soon as there is news (or after 25 s).
const shown = new Set();   // message numbers already on screen

async function follow(mine) {
  while (call === mine) {
    let news;
    try {
      const known = Object.keys(mine.people).length;
      const reply = await api(`/api/calls/${mine.code}?after=${mine.after}&known=${known}`);
      if (reply.status === 404) { showStatus("This call has ended · కాల్ ముగిసింది"); return; }
      if (!reply.ok) throw new Error(String(reply.status));
      news = await reply.json();
    } catch {
      await new Promise((wait) => setTimeout(wait, 2000));   // no internet for a moment: try again
      continue;
    }
    if (call !== mine) return;
    const joined = !them() && news.people[mine.person === "a" ? "b" : "a"];
    mine.people = news.people;
    if (joined) showStatus();
    for (const m of news.messages) {
      mine.after = Math.max(mine.after, m.n);
      if (m.person === mine.person || shown.has(m.n)) continue;   // my own sentences are shown as I say them
      shown.add(m.n);
      lastHeard = Date.now();
      say(addLine("theirs", m.translation, m.text), m.translation, m.to, m.n);
    }
  }
}

function addLine(kind, big, small) {
  const line = document.createElement("li");
  line.className = kind;
  line.textContent = big;
  if (small) {
    const note = document.createElement("small");
    note.textContent = small;
    line.append(note);
  }
  $("talk").append(line);
  line.scrollIntoView({ behavior: "smooth", block: "end" });
  return line;
}

// --- Listening to my own person ----------------------------------------------
let ctx, stream, node;
let noise = 0.01, speaking = false, chunks = [], preRoll = [], speechMs = 0, quietMs = 0, lastHeard = 0;

$("mic").addEventListener("click", () => { unlockSound(); ctx ? stop() : start(); });

async function start() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
    });
  } catch {
    showStatus("Please allow the microphone · మైక్ అనుమతి ఇవ్వండి");
    return;
  }
  ctx = new AudioContext();
  const source = ctx.createMediaStreamSource(stream);
  node = ctx.createScriptProcessor(4096, 1, 1);
  source.connect(node);
  node.connect(ctx.destination);
  node.onaudioprocess = (e) => listen(new Float32Array(e.inputBuffer.getChannelData(0)));
  stream.getAudioTracks().forEach((t) => (t.onended = () => ctx && stop("Microphone stopped · మైక్ ఆగిపోయింది")));
  lastHeard = Date.now();
  showMic(true);
}

function stop(why) {
  node.disconnect();
  stream.getTracks().forEach((t) => t.stop());
  ctx.close();
  ctx = null;
  reset();
  showMic(false, why);
}

function showMic(on, why) {
  $("mic").classList.toggle("on", on);
  $("mic").textContent = on ? "⏹" : "🎙️";
  $("mic").setAttribute("aria-label", on ? "Stop talking" : "Start talking");
  $("mic-label").textContent = why || (on ? "Listening… · వింటున్నాను…" : "Tap to talk · మాట్లాడటానికి నొక్కండి");
}

function reset() {
  speaking = false; chunks = []; preRoll = []; speechMs = 0; quietMs = 0;
}

function listen(chunk) {
  if (muted) { reset(); lastHeard = Date.now(); return; }   // this phone is speaking: don't hear itself
  if (Date.now() - lastHeard > QUIET_STOP_MS) {
    stop("No one spoke for 3 minutes · 3 నిమిషాలు ఎవరూ మాట్లాడలేదు");
    return;
  }
  const ms = (chunk.length / ctx.sampleRate) * 1000;
  const level = Math.sqrt(chunk.reduce((s, x) => s + x * x, 0) / chunk.length);
  const start = Math.max(0.015, noise * 3);
  const loud = level > start;

  if (!speaking) {
    noise = noise * 0.95 + level * 0.05;   // learn how quiet the room is
    preRoll.push(chunk);
    while (preRoll.length * ms > PRE_ROLL_MS) preRoll.shift();
    if (loud) { speaking = true; chunks = [...preRoll]; $("mic-label").textContent = "Hearing you… · వింటున్నాను…"; }
    return;
  }
  chunks.push(chunk);
  speechMs += ms;
  quietMs = level > start * 0.5 ? 0 : quietMs + ms;
  if (quietMs >= PAUSE_MS || speechMs >= MAX_SENTENCE_MS) {
    const sentence = chunks, long = speechMs - quietMs;
    reset();
    $("mic-label").textContent = "Listening… · వింటున్నాను…";
    if (long >= MIN_SPEECH_MS) { lastHeard = Date.now(); send(sentence, ctx.sampleRate); }
  }
}

// One sentence: Meta's ears turn it into words, then Mythree translates it for the other phone.
async function send(sentence, rate) {
  const mine = call;
  if (!mine) return;
  const line = addLine("mine", "…");
  const form = new FormData();
  form.append("audio", toWav(sentence, rate), "sentence.wav");
  form.append("lang", mine.lang);
  try {
    const heard = await api("/api/hear", { method: "POST", body: form });
    if (!heard.ok) throw new Error(await problemOf(heard));
    const { text } = await heard.json();
    if (!text) { line.remove(); return; }
    line.textContent = text;
    const reply = await postJson(`/api/calls/${mine.code}/said`, { person: mine.person, text });
    if (!reply.ok) throw new Error(await problemOf(reply));
    const m = await reply.json();
    const note = document.createElement("small");
    note.textContent = m.translation;
    line.append(note);
  } catch (e) {
    line.textContent = e.message || "Please say it again · మళ్ళీ చెప్పండి";
  }
}

// --- Speaking what the other person said, in their own voice ------------------
// Phones only let a page play sound after a tap, so the first tap "unlocks" one
// sound player that is then used for every sentence.
const voice = new Audio();
let unlocked = false, muted = false, queue = Promise.resolve();

function unlockSound() {
  if (unlocked) return;
  unlocked = true;
  voice.src = URL.createObjectURL(toWav([new Float32Array(1600)], TARGET_RATE));   // a tenth of a second of silence
  voice.play().catch(() => { unlocked = false; });
}

function hush() {
  voice.pause();
  window.speechSynthesis?.cancel();
  queue = Promise.resolve();
  muted = false;
}

function say(line, text, lang, n) {
  const mine = call;
  queue = queue.then(() => sayNow(line, text, lang, n, mine));
  return queue;
}

async function sayNow(line, text, lang, n, mine) {   // in the voice of the person who said it
  if (call !== mine) return;
  muted = true;
  try {
    const reply = await postJson(`/api/calls/${mine.code}/speak`, { n });
    if (!reply.ok) throw new Error("no own voice");
    await play(URL.createObjectURL(await reply.blob()));
  } catch {
    line.querySelector("small")?.append(" · standard voice");
    await standardVoice(text, lang);
  } finally {
    muted = false;
  }
}

function play(src) {
  return new Promise((resolve) => {
    let last = -1, still = 0;
    const guard = setInterval(() => {   // never wait forever if the sound gets stuck
      still = voice.currentTime === last ? still + 1 : 0;
      last = voice.currentTime;
      if (still >= 6) { voice.pause(); done(); }
    }, 1000);
    const done = () => { clearInterval(guard); voice.onended = voice.onerror = voice.onpause = null; resolve(); };
    voice.src = src;
    voice.onended = voice.onerror = voice.onpause = done;
    voice.play().catch(done);
  });
}

function standardVoice(text, lang) {
  return new Promise((done) => {
    if (!window.speechSynthesis) return done();
    const words = new SpeechSynthesisUtterance(text);
    words.lang = lang === "te" ? "te-IN" : "en-US";
    words.onend = words.onerror = done;
    speechSynthesis.speak(words);
  });
}

// --- Recording my own voice (with my consent) ---------------------------------
const READ_THIS = {
  en: "Hello! I'm recording my voice for Mythree, so my family can hear me in my own voice, even in another language. " +
      "Every week we try to talk, and sometimes the words don't come easily. I want to tell them about my day: what I cooked, " +
      "who I met, what made me laugh, and what I'm looking forward to. I want to hear their stories too: about school, about work, " +
      "about friends, about the little things that make a day special. Distance is hard, but a familiar voice makes it feel closer. " +
      "When I say I'm proud of you, I want it to sound like me. When I ask, have you eaten, I want it to sound warm and caring, " +
      "just like home. Thank you for listening, and see you soon.",
  te: "నమస్కారం! మా కుటుంబం నా మాటలను నా సొంత గొంతులోనే వినాలని, మైత్రి కోసం నా గొంతును రికార్డ్ చేస్తున్నాను. " +
      "ప్రతి వారం మేము మాట్లాడుకోవాలని అనుకుంటాం, కానీ కొన్నిసార్లు మాటలు సులభంగా రావు. ఈ రోజు నేను ఏం వండాను, ఎవరిని కలిశాను, " +
      "నన్ను ఏది నవ్వించింది, అన్నీ వాళ్ళకు చెప్పాలని ఉంది. వాళ్ళ చదువు, ఉద్యోగం, స్నేహితుల గురించి, రోజును ప్రత్యేకంగా మార్చే " +
      "చిన్న చిన్న విషయాల గురించి కూడా వినాలని ఉంది. దూరం కష్టమే, కానీ తెలిసిన గొంతు వింటే దగ్గరగా అనిపిస్తుంది. " +
      "నేను మిమ్మల్ని చూసి గర్వపడుతున్నాను అని చెప్పినప్పుడు, అది నా గొంతులాగే వినిపించాలి. భోజనం చేశావా అని అడిగినప్పుడు, " +
      "ఇంట్లో లాగే ఆప్యాయంగా వినిపించాలి. విన్నందుకు ధన్యవాదాలు, త్వరలో కలుద్దాం.",
};
const MIN_RECORD_S = 20, MAX_RECORD_S = 90;

function showVoice() {
  $("voice-state").textContent = myVoice
    ? "✅ Your own voice is ready · మీ గొంతు సిద్ధంగా ఉంది"
    : "Your own voice isn't recorded yet. Until then, Mythree uses a standard voice. · మీ గొంతు ఇంకా రికార్డ్ చేయలేదు.";
  $("record-open").textContent = myVoice ? "Record again · మళ్ళీ రికార్డ్ చేయండి" : "Record my voice · నా గొంతు రికార్డ్ చేయండి";
  $("voice-hello").hidden = $("voice-delete").hidden = !myVoice;
}
showVoice();

function saveVoice(id) {
  myVoice = id;
  me();   // remember it on this phone
  showVoice();
}

$("record-open").addEventListener("click", () => {
  unlockSound();
  $("read-this").lang = $("lang").value;
  $("read-this").textContent = READ_THIS[$("lang").value];
  $("rec-problem").textContent = "";
  $("setup").hidden = true;
  $("recorder").hidden = false;
});

$("rec-cancel").addEventListener("click", () => {
  if (recording) finishRecording(false);
  $("recorder").hidden = true;
  $("setup").hidden = false;
});

let recording = null;   // { ctx, stream, node, chunks, began, timer }

$("rec").addEventListener("click", async () => {
  if (recording) return finishRecording(true);
  if (!$("consent").checked) {
    $("rec-problem").textContent = "Please tick the box to agree first · ముందు అంగీకరించండి";
    return;
  }
  $("rec-problem").textContent = "";
  let mic;
  try {
    mic = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 } });
  } catch {
    $("rec-problem").textContent = "Please allow the microphone · మైక్ అనుమతి ఇవ్వండి";
    return;
  }
  const rctx = new AudioContext();
  const rnode = rctx.createScriptProcessor(4096, 1, 1);
  rctx.createMediaStreamSource(mic).connect(rnode);
  rnode.connect(rctx.destination);
  recording = { ctx: rctx, stream: mic, node: rnode, chunks: [], began: Date.now() };
  rnode.onaudioprocess = (e) => recording?.chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
  recording.timer = setInterval(() => {
    const s = Math.floor((Date.now() - recording.began) / 1000);
    $("rec-time").textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    if (s >= MAX_RECORD_S) finishRecording(true);
  }, 250);
  $("rec").classList.add("on");
  $("rec").textContent = "■ Stop and save · ఆపి సేవ్ చేయండి";
});

async function finishRecording(keep) {
  const r = recording;
  recording = null;
  clearInterval(r.timer);
  r.node.disconnect();
  r.stream.getTracks().forEach((t) => t.stop());
  const rate = r.ctx.sampleRate, seconds = (Date.now() - r.began) / 1000;
  r.ctx.close();
  $("rec").classList.remove("on");
  $("rec").textContent = "● Start recording · మొదలుపెట్టండి";
  $("rec-time").textContent = "0:00";
  if (!keep) return;
  if (seconds < MIN_RECORD_S) {
    $("rec-problem").textContent = "Please talk for at least 20 seconds · కనీసం 20 సెకన్లు మాట్లాడండి";
    return;
  }
  $("rec-problem").textContent = "Mythree is learning your voice… · మైత్రి మీ గొంతు నేర్చుకుంటోంది…";
  const form = new FormData();
  form.append("audio", toWav(r.chunks, rate), "voice.wav");
  form.append("name", $("name").value.trim() || ($("relation").selectedOptions[0]?.text.split(" · ")[0] ?? ""));
  form.append("consent", "true");
  try {
    const reply = await api("/api/voices", { method: "POST", body: form });
    if (!reply.ok) throw new Error(await problemOf(reply));
    const old = myVoice;
    saveVoice((await reply.json()).voice);
    if (old) api(`/api/voices/${old}`, { method: "DELETE" });   // the new recording replaces the old one
    $("recorder").hidden = true;
    $("setup").hidden = false;
    hearMyVoice();
  } catch (e) {
    $("rec-problem").textContent = e.message || "Please try again · మళ్ళీ ప్రయత్నించండి";
  }
}

async function hearMyVoice() {
  const reply = await api(`/api/voices/${myVoice}/hello?lang=${$("lang").value}`, { method: "POST" });
  if (reply.ok) play(URL.createObjectURL(await reply.blob()));
}
$("voice-hello").addEventListener("click", () => { unlockSound(); hearMyVoice(); });

$("voice-delete").addEventListener("click", async () => {
  if (!confirm("Delete your voice from Mythree? · మీ గొంతును తొలగించాలా?")) return;
  const reply = await api(`/api/voices/${myVoice}`, { method: "DELETE" });
  if (reply.ok) saveVoice("");
  else $("problem").textContent = await problemOf(reply);
});

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
