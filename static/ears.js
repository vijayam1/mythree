// Mythree's ears in the browser.
// Listens to the microphone, notices when the speaker pauses, and sends
// each sentence (as a small WAV file) to the server, which asks Meta's ears.

const PAUSE_MS = 1400;       // this much quiet ends a sentence (0.7 s cut Vijaya off mid-thought)
const MIN_SPEECH_MS = 400;   // shorter sounds (a cough, a click) are ignored
const MAX_SENTENCE_MS = 25000;
const PRE_ROLL_MS = 300;     // keep a little sound from just before the voice started
const TARGET_RATE = 16000;   // Meta wants 16 kHz

const ui = {
  start: document.getElementById("start"),
  mood: document.getElementById("mood"),
  heard: document.getElementById("heard"),
  cards: document.querySelectorAll(".person"),
};
let ctx, stream, node;

// --- The two people on the call ---------------------------------------------
// Any two people: each picks a relation, an optional name and a language,
// remembered in this browser only. "a" is shown on the left, "b" on the right.
// The relation tells the brain who is the elder, so Telugu stays respectful.
const RELATIONS = {
  grandpa: ["Grandpa", "తాతయ్య", "🧔"], grandma: ["Grandma", "అమ్మమ్మ / నానమ్మ", "👩‍🦱"],
  father: ["Father", "నాన్న", "👨"], mother: ["Mother", "అమ్మ", "👩"],
  son: ["Son", "కొడుకు", "👦"], daughter: ["Daughter", "కూతురు", "👧"],
  grandson: ["Grandson", "మనవడు", "🧑"], granddaughter: ["Granddaughter", "మనవరాలు", "👧"],
  uncle: ["Uncle", "మావయ్య / బాబాయ్", "👨"], aunt: ["Aunt", "అత్తయ్య / పిన్ని", "👩"],
  friend: ["Friend", "స్నేహితులు", "🧑"], other: ["Someone", "ఇంకెవరైనా", "🙂"],
};
// Grandparents today are often in their 50s: young faces by default, and each
// person can tap their face to pick their own. Faces start without a skin colour
// (people in India have every skin tone); the small round button picks one.
const FACES = ["🧔", "👨", "👩", "👩‍🦱", "🧑", "👦", "👧", "👨‍🦳", "👩‍🦳", "🧑‍🦱", "👱‍♀️", "🙂"];
const TONES = ["", "\u{1F3FB}", "\u{1F3FC}", "\u{1F3FD}", "\u{1F3FE}", "\u{1F3FF}"];
const TONE_COLOURS = ["#ffcc4d", "#f7d7c4", "#e8b894", "#c68e5f", "#8d5524", "#4a2f1d"];
const plain = (face) => face.replace(/[\u{1F3FB}-\u{1F3FF}]/gu, "");
// The skin tone goes right after the first character of the emoji (👩 + 🏽 + ‍🦱).
function withTone(face, tone) {
  if (!tone || face === "🙂") return face;
  const [first, ...rest] = [...face];
  return first + tone + rest.join("");
}
const faceOf = (p) => plain(p.face || (RELATIONS[p.relation] || RELATIONS.other)[2]);
const people = load() || {
  a: { relation: "grandpa", name: "", lang: "te" },
  b: { relation: "grandson", name: "", lang: "en" },
};
let speaker = "a";
const other = (id) => (id === "a" ? "b" : "a");

// How the brain hears about a person: "Ravi, the grandson" or just "the grandson".
function describe(id) {
  const p = people[id], relation = (RELATIONS[p.relation] || RELATIONS.other)[0].toLowerCase();
  return p.name.trim() ? `${p.name.trim()}, the ${relation}` : `the ${relation}`;
}

function load() {
  try {
    const saved = JSON.parse(localStorage.getItem("mythree-people"));
    return saved && saved.a && saved.a.relation ? saved : null;
  } catch { return null; }
}
function save() {
  try { localStorage.setItem("mythree-people", JSON.stringify(people)); } catch { /* private window */ }
}

function showPeople() {
  ui.cards.forEach((card) => {
    const id = card.dataset.person, p = people[id];
    card.querySelector(".face").textContent = withTone(faceOf(p), p.tone || "");
    card.querySelector(".tone").style.background = TONE_COLOURS[TONES.indexOf(p.tone || "")];
    card.querySelector(".relation").value = p.relation;
    card.querySelector(".name").value = p.name;
    card.querySelector(".lang").value = p.lang;
    card.setAttribute("aria-pressed", id === speaker);
  });
}

ui.cards.forEach((card) => {
  const id = card.dataset.person;
  const relation = card.querySelector(".relation");
  for (const [key, [en, te]] of Object.entries(RELATIONS)) relation.add(new Option(`${te} · ${en}`, key));
  card.addEventListener("click", (e) => {
    if (e.target.closest("input, select, .face, .tone")) return;
    speaker = id;
    showPeople();
  });
  card.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === " ") && e.target === card) { e.preventDefault(); card.click(); }
  });
  relation.addEventListener("change", (e) => {
    people[id].relation = e.target.value;
    delete people[id].face;   // a new relation brings its own face, until they pick one
    save(); showPeople();
  });
  card.querySelector(".tone").addEventListener("click", () => {
    people[id].tone = TONES[(TONES.indexOf(people[id].tone || "") + 1) % TONES.length];
    save(); showPeople();
  });
  card.querySelector(".face").addEventListener("click", () => {
    people[id].face = FACES[(FACES.indexOf(faceOf(people[id])) + 1) % FACES.length];
    save(); showPeople();
  });
  card.querySelector(".name").addEventListener("input", (e) => { people[id].name = e.target.value; save(); });
  card.querySelector(".lang").addEventListener("change", (e) => {
    people[id].lang = e.target.value;
    if (people[other(id)].lang === e.target.value) {   // the two must speak different languages
      people[other(id)].lang = e.target.value === "te" ? "en" : "te";
    }
    save(); showPeople();
  });
});
showPeople();

// --- Controls: voice on/off, animation on/off, type instead of speaking -----
const prefs = (() => { try { return JSON.parse(localStorage.getItem("mythree-prefs")) || {}; } catch { return {}; } })();
function applyPrefs() {
  document.body.classList.toggle("quiet", !!prefs.quiet);
  document.body.classList.toggle("still", !!prefs.still);
  document.getElementById("typing").hidden = !prefs.typing;
  const set = (id, on, onText, offText) => {
    const b = document.getElementById(id);
    b.setAttribute("aria-pressed", on);
    b.textContent = on ? onText : offText;
  };
  set("voice-btn", !prefs.quiet, "🔊 Voice on", "🔇 Voice off");
  set("motion-btn", !prefs.still, "🕊️ Animation on", "⏸️ Animation off");
  set("type-btn", !!prefs.typing, "⌨️ Typing on", "⌨️ Type instead");
  try { localStorage.setItem("mythree-prefs", JSON.stringify(prefs)); } catch { /* private window */ }
}
document.getElementById("voice-btn").addEventListener("click", () => { prefs.quiet = !prefs.quiet; applyPrefs(); });
document.getElementById("motion-btn").addEventListener("click", () => {
  prefs.still = !prefs.still; applyPrefs(); dispatchEvent(new Event("resize"));   // send her home
});
document.getElementById("type-btn").addEventListener("click", () => {
  prefs.typing = !prefs.typing; applyPrefs();
  if (prefs.typing) document.getElementById("type-text").focus();
});
applyPrefs();

// Typing: the chosen person types instead of speaking; the rest is the same.
document.getElementById("typing").addEventListener("submit", async (e) => {
  e.preventDefault();
  const box = document.getElementById("type-text"), text = box.value.trim();
  if (!text) return;
  box.value = "";
  const who = speaker, lang = people[who].lang, line = newBubble(who);
  showSaid(line, text, lang);
  await translate(line, { text, lang }, who);
});

function setMood(name, text) {
  ui.mood.className = "mood sr-only " + name;  // read aloud by screen readers; the koel shows it on screen
  ui.mood.textContent = text;
  document.body.dataset.mood = name;  // the koel acts out the mood
}

ui.start.addEventListener("click", () => (ctx ? stop() : start()));

// Start fresh: clears the conversation and loads the newest version of the page.
document.getElementById("refresh").addEventListener("click", () => location.reload());

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
  showButton(true);
  setMood("listening", "Listening… · వింటున్నాను…");
}

function stop() {
  node.disconnect();
  stream.getTracks().forEach((t) => t.stop());
  ctx.close();
  ctx = null;
  reset();
  showButton(false);
  setMood("goodbye", "Goodbye");
  window.mythreeBird?.goodbye();
  setTimeout(() => { if (!ctx) setMood("sleeping", "Sleeping"); }, 2200);
}

function showButton(on) {
  const words = on ? "Stop listening" : "Start listening";
  ui.start.classList.toggle("on", on);
  ui.start.textContent = on ? "⏹" : "🎙️";
  ui.start.setAttribute("aria-label", words);
  document.getElementById("start-label").textContent = words;
}

// --- Finding sentences ------------------------------------------------------
let noise = 0.01, speaking = false, chunks = [], preRoll = [], speechMs = 0, quietMs = 0;

function reset() {
  speaking = false; chunks = []; preRoll = []; speechMs = 0; quietMs = 0;
}

function listen(chunk) {
  if (muted) { reset(); return; }   // Mythree is speaking: don't hear itself
  const ms = (chunk.length / ctx.sampleRate) * 1000;
  const level = Math.sqrt(chunk.reduce((s, x) => s + x * x, 0) / chunk.length);
  const start = Math.max(0.015, noise * 3);
  const loud = level > start;

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
  // Once talking, soft word endings still count as talking: only clear quiet counts as a pause.
  quietMs = level > start * 0.5 ? 0 : quietMs + ms;
  if (quietMs >= PAUSE_MS || speechMs >= MAX_SENTENCE_MS) {
    const sentence = chunks, long = speechMs - quietMs;
    reset();
    setMood("listening", "Listening… · వింటున్నాను…");
    if (long >= MIN_SPEECH_MS) send(sentence, ctx.sampleRate);
  }
}

// --- Sending a sentence -----------------------------------------------------
function newBubble(who) {
  const line = document.createElement("li");
  line.className = "thinking";
  line.dataset.side = who;  // the first person's bubbles on the left, the second's on the right
  line.textContent = "…";
  ui.heard.append(line);
  line.scrollIntoView({ behavior: "smooth", block: "end" });
  return line;
}

function showSaid(line, text, lang) {
  line.className = "";
  line.textContent = "";
  const said = document.createElement("div");
  said.lang = lang;
  said.textContent = text;
  line.append(said);
}

async function send(sentence, rate) {
  const who = speaker, lang = people[who].lang;   // who was talking when this sentence was heard
  const line = newBubble(who);
  const form = new FormData();
  form.append("audio", toWav(sentence, rate), "sentence.wav");
  form.append("lang", lang);
  try {
    const reply = await fetch("/api/hear", { method: "POST", body: form });
    const data = await reply.json();
    if (!reply.ok) throw new Error(data.detail);
    if (!data.text) { line.className = ""; line.textContent = "(nothing heard)"; return; }
    showSaid(line, data.text, data.lang);
    await translate(line, data, who);
  } catch (err) {
    line.textContent = err.message || "Mythree couldn't hear that. Please say it again.";
    line.className = "error";
  }
}

// --- Brain: translate for the other person ----------------------------------
const history = [];  // earlier sentences, kept only in this page, gone when it closes

async function translate(line, said, who) {
  const to = other(who);
  const out = document.createElement("div");
  out.className = "translation thinking";
  out.textContent = "Translating…";
  line.append(out);
  if (!muted) setMood("thinking", "Thinking… · ఆలోచిస్తున్నాను…");
  try {
    const reply = await fetch("/api/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: said.text, lang: said.lang, to: people[to].lang,
        who: describe(who), listener: describe(to), history: history.slice(-6),
      }),
    });
    const data = await reply.json();
    if (!reply.ok) throw new Error(data.detail);
    out.lang = data.lang;
    out.textContent = data.text;
    out.className = "translation";
    await say(out, data.text, data.lang, who);
  } catch (err) {
    out.textContent = err.message || "Mythree couldn't translate that. Please say it again.";
    out.className = "translation error";
  }
  history.push({ text: said.text, lang: said.lang, who: describe(who) });
}

// --- Voice: speak the translation -------------------------------------------
// Sentences are spoken one after another, never on top of each other, and
// Mythree stops listening while it speaks so it never hears itself.
let muted = false, queue = Promise.resolve();

function say(out, text, lang, person) {
  queue = queue.then(() => sayNow(out, text, lang, person));
  return queue;
}

async function sayNow(out, text, lang, person) {  // in the voice of the person who spoke
  const tag = document.createElement("span");
  tag.className = "voice-tag";
  out.append(tag);
  if (document.body.classList.contains("quiet")) {   // "Voice off": text only
    tag.textContent = "voice off";
    setMood(ctx ? "listening" : "sleeping", ctx ? "Listening…" : "Sleeping");
    return;
  }
  muted = true;
  setMood("speaking", "Speaking… · మాట్లాడుతున్నాను…");
  try {
    const reply = await fetch("/api/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, lang, person }),
    });
    if (!reply.ok) throw new Error("no own voice");
    tag.textContent = "translated voice · own voice";
    await playStream(reply);
  } catch {
    tag.textContent = "standard voice";
    await standardVoice(text, lang);
  } finally {
    muted = false;
    setMood(ctx ? "listening" : "sleeping", ctx ? "Listening…" : "Sleeping");   // after typing, she rests again
  }
}

function play(audio) {
  try { window.mythreeBird?.lipsync(audio); } catch { /* her beak just uses the plain animation */ }
  return new Promise((resolve) => {
    // Never wait forever: if the sound stops moving for 6 s, carry on so Mythree keeps listening.
    let last = -1, still = 0;
    const guard = setInterval(() => {
      still = audio.currentTime === last ? still + 1 : 0;
      last = audio.currentTime;
      if (still >= 6) { audio.pause(); done(); }
    }, 1000);
    const done = () => { clearInterval(guard); resolve(); };
    audio.onended = audio.onerror = done;
    audio.play().catch(done);
  });
}

// Start playing as soon as the first piece of sound arrives (where the browser can).
async function playStream(reply) {
  if (!window.MediaSource || !MediaSource.isTypeSupported("audio/mpeg")) {
    return play(new Audio(URL.createObjectURL(await reply.blob())));
  }
  const source = new MediaSource();
  const audio = new Audio(URL.createObjectURL(source));
  await new Promise((open) => source.addEventListener("sourceopen", open, { once: true }));
  const buffer = source.addSourceBuffer("audio/mpeg");
  const reader = reply.body.getReader();
  let started = null;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer.appendBuffer(value);
    await new Promise((ok) => buffer.addEventListener("updateend", ok, { once: true }));
    started ??= play(audio);
  }
  source.endOfStream();
  await (started ?? play(audio));
}

// The browser's own voice, used only if the own voice can't be made.
function standardVoice(text, lang) {
  return new Promise((done) => {
    if (!window.speechSynthesis) return done();
    const words = new SpeechSynthesisUtterance(text);
    words.lang = lang === "te" ? "te-IN" : "en-US";
    words.onend = words.onerror = done;
    speechSynthesis.speak(words);
  });
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
