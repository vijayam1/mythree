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
const RELATION_TE = { grandfather: "తాతగారు", grandmother: "అమ్మమ్మ", grandson: "మనవడు", granddaughter: "మనవరాలు",
  father: "నాన్న", mother: "అమ్మ", son: "కొడుకు", daughter: "కూతురు", friend: "స్నేహితుడు" };

// --- Passcode (online only) --------------------------------------------------
let passcode = (() => { try { return localStorage.getItem("mythree-passcode") || ""; } catch { return ""; } })();
// Each call's link has a hidden key next to the 4-digit code, so nobody can join or read a call
// by guessing codes. The phone sends it with every request about the call.
let callKey = "";

async function api(url, options = {}) {
  options.headers = { ...(options.headers || {}), "X-Mythree-Passcode": passcode, "X-Mythree-Call-Key": callKey };
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
// Ask for the passcode right away, except when the page was opened from a call's link: its hidden
// key is enough to answer that call, so a grandmother never sees a passcode.
if (!new URLSearchParams(location.search).get("key")) api("/api/hello");

// --- Demo view (/demo): two phones side by side on one screen, for testing alone ---
// Each side is this same phone app, so later the two phones simply go to two places.
const DEMO = new URLSearchParams(location.search).get("demo");   // "a" (left), "b" (right), or null on a real phone
const ME_KEY = DEMO === "b" ? "mythree-me-b" : "mythree-me";     // the right phone remembers its own person
const demo = DEMO ? new BroadcastChannel("mythree-demo") : null;  // how the two sides tell each other things
const demoTail = DEMO ? `&demo=${DEMO}` : "";

// --- Who am I (remembered on this phone) --------------------------------------
const saved = (() => { try { return JSON.parse(localStorage.getItem(ME_KEY)) || {}; } catch { return {}; } })();
if (saved.relation) $("relation").value = saved.relation;
if (saved.name) $("name").value = saved.name;
if (saved.lang) $("lang").value = saved.lang;
let myVoice = saved.voice || "";   // the ID of the voice I recorded (it stays on this phone)
if (saved.theirPhone) $("their-phone").value = saved.theirPhone;
if (saved.theirEmail) $("their-email").value = saved.theirEmail;
if (saved.theirRelation) $("their-relation").value = saved.theirRelation;
// With two languages, the person I call always speaks the other one: changing either choice
// changes the other, so a grandson is never sent a Telugu invitation by mistake.
const otherLang = (lang) => (lang === "te" ? "en" : "te");
$("their-lang").value = otherLang($("lang").value);
$("lang").addEventListener("change", () => { $("their-lang").value = otherLang($("lang").value); });
$("their-lang").addEventListener("change", () => { $("lang").value = otherLang($("their-lang").value); });
const link = new URLSearchParams(location.search);
if (link.get("code")) invited(link.get("code"), link.get("key") || "");

async function invited(code, key) {   // opened from a link
  callKey = key;
  $("code").value = code;
  const reply = key ? await api(`/api/calls/${code}?after=0&known=0`) : null;
  const news = reply?.ok ? await reply.json() : null;
  if (news?.invite && !news.people.b) return showAnswer(code, news.invite);   // the caller chose for them: one button
  $("invite").hidden = false;   // otherwise: the steps and the Join button, not "Start a call"
  for (const id of ["calling", "start-call", "or"]) $(id).hidden = true;
}

// --- Answering: the invited person (often a grandparent) taps one big button -----
const ANSWER = {
  te: { calling: (c) => `${c} కాల్ చేస్తున్నారు`, answer: "ఎత్తండి", ended: "కాల్ ముగిసింది",
        allow: "ఫోన్ \"Allow\" అని అడిగితే, Allow నొక్కండి", listening: "మాట్లాడండి, మైత్రి వింటోంది",
        tap: "గ్రీన్ బటన్ నొక్కి మాట్లాడండి" },
  en: { calling: (c) => `${c} is calling`, answer: "Answer", ended: "The call has ended",
        allow: "If your phone asks, tap \"Allow\"", listening: "Just talk, Mythree is listening",
        tap: "Tap the green button to talk" },
};
let simple = null;   // the words for a grandparent's screen, in their language (null = the full app)

function showAnswer(code, invite) {
  const words = ANSWER[invite.lang] || ANSWER.en;
  $("setup").hidden = true;
  $("answer").hidden = false;
  $("caller-line").textContent = words.calling(invite.caller || "Mythree");
  $("answer-word").textContent = words.answer;
  $("allow-hint").textContent = words.allow;
  $("answer-btn").hidden = false;
  $("answer-btn").onclick = async () => {
    unlockSound();
    const reply = await postJson(`/api/calls/${code}/join`, { answer: true });
    if (!reply.ok) return ($("answer-problem").textContent = await problemOf(reply));
    const { person } = await reply.json();
    simple = words;
    document.body.classList.add("simple");
    $("answer").hidden = true;
    enter(code, person, invite.lang);
    showMic(false);   // her words under the mic, in her language
    start();   // the mic turns on by itself: there is nothing to press, just talk
  };
}

function me() {
  const relation = $("relation").value, name = $("name").value.trim(), lang = $("lang").value;
  const theirPhone = $("their-phone").value.trim(), theirEmail = $("their-email").value.trim();
  const theirRelation = $("their-relation").value, theirLang = $("their-lang").value;
  try {
    localStorage.setItem(ME_KEY, JSON.stringify({ relation, name, lang, voice: myVoice, theirPhone, theirEmail,
                                                   theirRelation, theirLang }));
  } catch { /* private window */ }
  const role = RELATION_WORDS[relation] || "a family member";
  // Who I'm calling: then their screen shows only "<me> is calling" and one Answer button.
  const caller = name || (theirLang === "te" ? `మీ ${RELATION_TE[relation] || ""}`.trim()
                                             : role.replace(/^(the|a) /, "your ").replace(/^./, (c) => c.toUpperCase()));
  const them = theirRelation && theirLang !== lang
    ? { who: RELATION_WORDS[theirRelation], lang: theirLang, caller } : null;
  return { who: name ? `${name}, ${role}` : role, lang, voice: myVoice, them };
}

// --- Starting or joining a call ----------------------------------------------
let call = null;   // { code, person, lang, people, after }

$("start-call").addEventListener("click", async () => {
  unlockSound();
  const mine = me();
  const reply = await postJson("/api/calls", mine);
  if (!reply.ok) return ($("problem").textContent = await problemOf(reply));
  const { code, person, key } = await reply.json();
  callKey = key;
  enter(code, person, mine.lang);
});

$("join-call").addEventListener("click", async () => {
  unlockSound();
  const code = $("code").value.trim();
  if (!/^\d{4}$/.test(code)) return ($("problem").textContent = "Please type the 4-digit code · 4 అంకెల కోడ్");
  if (!callKey) return ($("problem").textContent = "Please tap the link you were sent · మీకు వచ్చిన లింక్ నొక్కండి");
  const mine = me();
  const reply = await postJson(`/api/calls/${code}/join`, mine);
  if (reply.status === 404) {   // the call has ended (or Mythree restarted): offer a new call instead
    $("invite").hidden = true;
    for (const id of ["calling", "start-call", "or"]) $(id).hidden = false;
  }
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
  history.replaceState(null, "", `/phone?code=${code}&key=${callKey}${demoTail}`);
  if (DEMO && person === "a") demo.postMessage({ code, key: callKey });   // the other side gets the call by itself
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
  if (simple) {   // a grandparent's phone: just say the call has ended
    $("answer").hidden = false;
    $("caller-line").textContent = simple.ended;
    $("answer-btn").hidden = true;
    $("allow-hint").textContent = "";
    return;
  }
  $("setup").hidden = false;
  history.replaceState(null, "", DEMO ? `/phone?demo=${DEMO}` : "/phone");
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
  const steps = document.createElement("div");
  steps.className = "steps";
  steps.innerHTML = `<h2>Your call code · మీ కోడ్: <strong></strong></h2>
    <ol>
      <li>Tap WhatsApp, Email or Text below · కింద WhatsApp, Email లేదా Text బటన్ నొక్కండి</li>
      <li>There, tap <b>Send</b> · అక్కడ <b>Send</b> నొక్కండి</li>
      <li>Come back here and wait. This box turns to "Talking with…" when they join · వాళ్ళు జాయిన్ అయ్యే వరకు ఇక్కడే ఉండండి</li>
      <li>Then tap the green mic button 🎙️. When it turns red, talk · తర్వాత గ్రీన్ మైక్ బటన్ 🎙️ నొక్కండి. అది ఎరుపు అయ్యాక మాట్లాడండి</li>
    </ol>`;
  steps.querySelector("strong").textContent = call.code;
  const sends = document.createElement("div");
  sends.className = "sends";
  const { whatsapp, email, text } = invitation();
  sends.append(sendButton("whatsapp", "WhatsApp", whatsapp), sendButton("email", "Email", email),
               sendButton("text", "Text · SMS", text), copyButton());
  box.append(steps, sends);
}

// The invitation: the link plus clear steps, in English and Telugu, ready to send.
// A web page can't send a message by itself; it opens WhatsApp, email or messages with
// everything filled in, and the caller taps Send.
function invitation() {
  const link = `${location.origin}/phone?code=${call.code}&key=${callKey}`;
  const mine = me();
  const who = mine.who.replace(/^./, (c) => c.toUpperCase());   // "the grandson" starts the message: "The grandson"
  const message = mine.them   // I chose who I'm calling: a short message in their language, one button for them
    ? (mine.them.lang === "te"
      ? `${mine.them.caller} మైత్రిలో మీకు కాల్ చేస్తున్నారు 📞\nఈ లింక్ నొక్కండి, తర్వాత పెద్ద గ్రీన్ "ఎత్తండి" బటన్ నొక్కండి:\n${link}`
      : `${mine.them.caller} is calling you on Mythree 📞\nTap this link, then the big green "Answer" button:\n${link}`)
    :
    `${who} is calling you on Mythree, so we can talk, each in our own language.\n` +
    `1. Tap this link: ${link}\n` +
    `2. Choose who you are and the language you speak.\n` +
    `3. Tap the green "Join" button (the code ${call.code} is already filled in).\n` +
    `4. If it asks for a passcode, type the one I gave you.\n` +
    `5. Tap the green mic button 🎙️. When it turns red, talk. Pause a little after each sentence.\n\n` +
    `మైత్రిలో మీకు కాల్ చేస్తున్నాను, ఎవరి భాషలో వాళ్ళు మాట్లాడుకోవచ్చు.\n` +
    `1. ఈ లింక్ నొక్కండి: ${link}\n` +
    `2. మీరు ఎవరు, మీ భాష ఏమిటి, ఎంచుకోండి.\n` +
    `3. గ్రీన్ "Join" బటన్ నొక్కండి. కాల్‌లో జాయిన్ అవుతారు (కోడ్ ${call.code} ముందే ఉంటుంది).\n` +
    `4. పాస్‌కోడ్ అడిగితే, నేను ఇచ్చింది టైప్ చేయండి.\n` +
    `5. గ్రీన్ మైక్ బటన్ 🎙️ నొక్కండి. అది ఎరుపు అయ్యాక మాట్లాడండి. ప్రతి మాట తర్వాత కొంచెం ఆగండి.`;
  const phone = $("their-phone").value.replace(/[^\d]/g, "");   // WhatsApp wants only digits, with country code
  const email = $("their-email").value.trim();
  const words = encodeURIComponent(message);
  return {
    message,
    whatsapp: `https://wa.me/${phone}?text=${words}`,
    email: `mailto:${encodeURIComponent(email)}?subject=${encodeURIComponent("Mythree call · మైత్రి కాల్ " + call.code)}&body=${words}`,
    text: `sms:${phone ? "+" + phone : ""}?&body=${words}`,
  };
}

function sendButton(kind, label, href) {
  const a = document.createElement("a");
  a.className = `send ${kind}`;
  a.textContent = label;
  a.href = href;
  if (kind === "whatsapp") a.target = "_blank";
  return a;
}

function copyButton() {
  const b = document.createElement("button");
  b.className = "send copy";
  b.textContent = "Copy · కాపీ";
  b.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(invitation().message); b.textContent = "Copied ✓"; }
    catch { b.textContent = "Couldn't copy"; }
    setTimeout(() => (b.textContent = "Copy · కాపీ"), 2000);
  });
  return b;
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
  $("talk").scrollTop = $("talk").scrollHeight;   // always show the newest line
  return line;
}

// --- Listening to my own person ----------------------------------------------
let ctx, stream, node;
let noise = 0.01, speaking = false, chunks = [], preRoll = [], speechMs = 0, quietMs = 0, lastHeard = 0;

$("mic").addEventListener("click", () => {
  unlockSound();
  if (!ctx && !them()) {   // nobody to talk to yet: the words would go nowhere
    $("mic-label").textContent = "Nobody has joined yet. Send the link first, then wait · " +
      "ఇంకా ఎవరూ జాయిన్ అవ్వలేదు. ముందు లింక్ పంపండి, తర్వాత ఆగండి";
    return;
  }
  ctx ? stop() : start();
});

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
  ctx.resume?.();   // started right after Answer (not a tap of its own): make sure it really runs
  demo?.postMessage({ mic: DEMO });   // one microphone for both sides: the other side stops listening
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
  $("mic-label").textContent = why || (simple ? (on ? simple.listening : simple.tap) : on
    ? "Red: talk now. Pause after each sentence. Tap red to stop · ఎరుపు: ఇప్పుడు మాట్లాడండి. ఆపాలంటే ఎరుపు బటన్ నొక్కండి"
    : "Green: tap to talk · గ్రీన్ బటన్ నొక్కి మాట్లాడండి");
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
  form.append("person", mine.person);
  try {   // one trip: the server hears, translates and shares it (from India, each trip adds time)
    const reply = await api(`/api/calls/${mine.code}/heard`, { method: "POST", body: form });
    if (!reply.ok) throw new Error(await problemOf(reply));
    const m = await reply.json();
    if (!m.text) { line.remove(); return; }
    line.textContent = m.text;
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
    const sound = URL.createObjectURL(await reply.blob());
    addReplay(line, () => play(sound));
    await play(sound);
  } catch {
    line.querySelector("small")?.append(" · standard voice");
    addReplay(line, () => standardVoice(text, lang));
    await standardVoice(text, lang);
  } finally {
    muted = false;
  }
}

// 🔁 Hear a sentence again. The sound is kept on this phone, so a replay is instant and costs nothing.
function addReplay(line, again) {
  if (line.querySelector(".replay")) return;
  const button = document.createElement("button");
  button.className = "replay";
  button.textContent = "🔁";
  button.setAttribute("aria-label", "Hear it again · మళ్ళీ వినండి");
  button.addEventListener("click", () => {
    unlockSound();
    queue = queue.then(async () => {   // after anything already playing; the mic doesn't hear it
      muted = true;
      try { await again(); } finally { muted = false; }
    });
  });
  line.prepend(button);
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

// --- Demo view: the two sides take turns with the one microphone ---------------
if (demo) {
  if (DEMO === "b" && !saved.lang) {   // the right phone starts as the English-speaking grandson
    $("lang").value = "en";
    $("relation").value = "grandson";
    $("their-lang").value = "te";
  }
  demo.onmessage = ({ data }) => {
    if (data.mic && data.mic !== DEMO && ctx) stop("The other phone is listening now · ఇప్పుడు ఇంకో ఫోన్ వింటోంది");
    if (data.code && !call) invited(data.code, data.key);
  };
}
