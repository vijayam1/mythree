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

// --- Talking to the server --------------------------------------------------
// Each call's link has a hidden key next to the 4-digit code, so nobody can join or read a call
// by guessing codes. The phone sends it with every request about the call.
let callKey = "";

async function api(url, options = {}) {
  options.headers = { ...(options.headers || {}), "X-Mythree-Call-Key": callKey };
  return fetch(url, options);
}
const postJson = (url, body) => api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
async function problemOf(reply) {
  try { return (await reply.json()).detail || "Something went wrong."; } catch { return "Something went wrong."; }
}

// --- Demo view (/demo): two phones side by side on one screen, for testing alone ---
// Each side is this same phone app, so later the two phones simply go to two places.
const DEMO = new URLSearchParams(location.search).get("demo");   // "a" (left), "b" (right), or null on a real phone
const ME_KEY = DEMO === "b" ? "mythree-me-b" : "mythree-me";     // the right phone remembers its own person
const CALL_KEY = `${ME_KEY}-call`;                                 // and the call it is in
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
// Back to my call: sending the invitation leaves this page (WhatsApp opens), and the phone may
// reload it or open it fresh. The phone remembers the call it is in, so the page comes back to it.
const back = rememberedCall();
if (back && (!link.get("code") || link.get("code") === back.code)) {
  resume(back).then((ok) => ok || !link.get("code") || invited(link.get("code"), link.get("key") || ""));
} else if (link.get("code")) invited(link.get("code"), link.get("key") || "");

async function invited(code, key) {   // opened from a link
  callKey = key;
  $("code").value = code;
  const reply = key ? await api(`/api/calls/${code}?after=0&known=0`) : null;
  const news = reply?.ok ? await reply.json() : null;
  if (news?.invite && !news.people.b) return showAnswer(code, news.invite);   // the caller chose for them: one button
  $("invite").hidden = false;   // otherwise: the steps and the Join button, not "Start a call"
  // and no "Record my voice": only the caller records theirs, the invited person just joins
  for (const id of ["calling", "start-call", "or", "voice-box"]) $(id).hidden = true;
}

// --- Answering: the invited person (often a grandparent) taps one big button -----
const ANSWER = {
  te: { calling: (c) => `${c} కాల్ చేస్తున్నారు`, answer: "ఫోన్ ఎత్తండి", ended: "కాల్ ముగిసింది",
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
    // the voice this phone recorded before (if any), so the answering person speaks in their own voice too
    const reply = await postJson(`/api/calls/${code}/join`, { answer: true, voice: myVoice });
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

function rememberedCall() {
  try {
    const back = JSON.parse(localStorage.getItem(CALL_KEY));
    return back && Date.now() - back.at < 3 * 3600 * 1000 ? back : null;   // a call is forgotten after 3 hours
  } catch { return null; }
}

function forgetCall() {
  try { localStorage.removeItem(CALL_KEY); } catch { /* private window */ }
}

async function resume(back) {   // the page came back while its call goes on: carry on where it was
  callKey = back.key;
  const reply = await api(`/api/calls/${back.code}?after=0&known=0&person=${back.person}&notes=0`).catch(() => null);
  if (!reply?.ok) { forgetCall(); return false; }
  if (back.simple) {
    simple = ANSWER[back.simple] || ANSWER.en;
    document.body.classList.add("simple");
  }
  enter(back.code, back.person, back.lang, await reply.json());
  showMic(false);
  return true;
}

function enter(code, person, lang, news) {
  call = { code, person, lang, people: {}, after: 0, notes: 0 };
  try {
    localStorage.setItem(CALL_KEY, JSON.stringify({ code, key: callKey, person, lang, simple: simple ? lang : "",
                                                    at: Date.now() }));
  } catch { /* private window */ }
  shown.clear();
  $("talk").replaceChildren();
  if (news) {   // came back to the call: show what was said, without saying it all again
    call.people = news.people;
    call.notes = news.notes?.at(-1)?.n || 0;   // old video notes are for the page that was here before
    for (const m of news.messages) {
      call.after = m.n;
      shown.add(m.n);
      const mine = m.person === person;
      addLine(mine ? "mine" : "theirs", mine ? m.text : m.translation, mine ? m.translation : m.text);
    }
  }
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
  if (call) sendNote(call, { kind: "bye" });
  forgetCall();
  if (ctx) stop();
  closeVideo();
  closeMedia();
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
      <li>Can't find this page? Tap the Mythree link again (the one you just sent works too). Your call comes back · ఈ పేజీ కనిపించకపోతే, మైత్రి లింక్ మళ్ళీ నొక్కండి (మీరు పంపిన లింక్ కూడా పనిచేస్తుంది). మీ కాల్ తిరిగి వస్తుంది</li>
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
      ? `${mine.them.caller} మైత్రిలో మీకు కాల్ చేస్తున్నారు 📞\nఈ లింక్ నొక్కండి, తర్వాత పెద్ద గ్రీన్ "ఫోన్ ఎత్తండి" బటన్ నొక్కండి:\n${link}`
      : `${mine.them.caller} is calling you on Mythree 📞\nTap this link, then the big green "Answer" button:\n${link}`)
    :
    `${who} is calling you on Mythree, so we can talk, each in our own language.\n` +
    `1. Tap this link: ${link}\n` +
    `2. Choose who you are and the language you speak.\n` +
    `3. Tap the green "Join" button (the code ${call.code} is already filled in).\n` +
    `4. Tap the green mic button 🎙️. When it turns red, talk. Pause a little after each sentence.\n\n` +
    `మైత్రిలో మీకు కాల్ చేస్తున్నాను, ఎవరి భాషలో వాళ్ళు మాట్లాడుకోవచ్చు.\n` +
    `1. ఈ లింక్ నొక్కండి: ${link}\n` +
    `2. మీరు ఎవరు, మీ భాష ఏమిటి, ఎంచుకోండి.\n` +
    `3. గ్రీన్ "Join" బటన్ నొక్కండి. కాల్‌లో జాయిన్ అవుతారు (కోడ్ ${call.code} ముందే ఉంటుంది).\n` +
    `4. గ్రీన్ మైక్ బటన్ 🎙️ నొక్కండి. అది ఎరుపు అయ్యాక మాట్లాడండి. ప్రతి మాట తర్వాత కొంచెం ఆగండి.`;
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
  // On a computer WhatsApp opens in a new tab, next to this one. On a phone the WhatsApp app opens
  // instead; a new tab there would hide this page behind an empty one when the caller comes back.
  if (kind === "whatsapp" && !matchMedia("(pointer: coarse)").matches) a.target = "_blank";
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
      const reply = await api(`/api/calls/${mine.code}?after=${mine.after}&known=${known}` +
                              `&person=${mine.person}&notes=${mine.notes}`);
      if (reply.status === 404) { forgetCall(); showStatus("This call has ended · కాల్ ముగిసింది"); return; }
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
    if (news.notes?.length) mine.notes = news.notes.at(-1).n;   // (after a restart the numbers start again)
    for (const n of news.notes || []) onNote(n, mine);
    for (const m of news.messages) {
      mine.after = Math.max(mine.after, m.n);
      if (m.person === mine.person || shown.has(m.n)) continue;   // my own sentences are shown as I say them
      shown.add(m.n);
      lastHeard = Date.now();
      caption(m.translation);
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
    media ||= await openMedia();
  } catch {
    showStatus("Please allow the microphone · మైక్ అనుమతి ఇవ్వండి");
    return;
  }
  stream = media;
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
  if (hasVideo()) showVideo();
}

function stop(why) {
  node.disconnect();
  if (!hasVideo()) closeMedia();   // in a video call the camera and the real voice go on; only the listening stops
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
  live?.abort(); live = null;
}

function listen(chunk) {
  if (muted) { reset(); lastHeard = Date.now(); return; }   // this phone is speaking: don't hear itself
  if (!hasVideo() && Date.now() - lastHeard > QUIET_STOP_MS) {   // (on video they may just be looking)
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
    if (loud) {
      speaking = true; chunks = [...preRoll]; $("mic-label").textContent = "Hearing you… · వింటున్నాను…";
      live = openLive(ctx.sampleRate);
      chunks.forEach((c) => live?.hear(c));
    }
    return;
  }
  chunks.push(chunk);
  live?.hear(chunk);
  speechMs += ms;
  quietMs = level > start * 0.5 ? 0 : quietMs + ms;
  if (quietMs >= PAUSE_MS || speechMs >= MAX_SENTENCE_MS) {
    const sentence = chunks, long = speechMs - quietMs, line = live;
    live = null;   // this sentence keeps its live line; reset() must not close it
    reset();
    $("mic-label").textContent = "Listening… · వింటున్నాను…";
    if (long >= MIN_SPEECH_MS) { lastHeard = Date.now(); send(sentence, ctx.sampleRate, line); }
    else line?.abort();   // a cough or a click
  }
}

// --- Live listening ---------------------------------------------------------------
// While the person talks, the sound goes to Mythree in small pieces, and Mythree passes it
// on to Meta's live ears, so the words are ready about 0.3 s after the pause instead of
// 1–4 s later. (The key stays on the server: the phone never talks to Meta directly.)
// If anything goes wrong, the whole sentence is sent the old way, so nothing is lost.
const LIVE_WAIT_MS = 10000;   // no answer this long after the pause: use the old way
let live = null;              // the live line of the sentence being said right now

function openLive(rate) {
  const mine = call;
  if (!mine || !window.WebSocket) return null;
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${scheme}://${location.host}/api/calls/${mine.code}/live`);
  const l = { line: null, waiting: [JSON.stringify({ key: callKey, person: mine.person })], done: null, failed: false };
  const give = (m) => { l.failed = true; l.done?.(m); l.done = null; };
  socket.onopen = () => { l.waiting.forEach((x) => socket.send(x)); l.waiting = []; };
  socket.onmessage = ({ data }) => {
    const m = JSON.parse(data);
    if ("partial" in m) {   // the words so far, while the person is still talking
      if (!m.partial) return;
      l.line ||= addLine("mine", "");
      l.line.textContent = m.partial + " …";
    } else {
      give(m.error ? null : m);
      socket.close();
    }
  };
  socket.onclose = socket.onerror = () => give(null);
  const send = (x) => {
    if (socket.readyState === WebSocket.OPEN) socket.send(x);
    else if (socket.readyState === WebSocket.CONNECTING) l.waiting.push(x);
  };
  l.hear = (chunk) => { if (!l.failed) send(toPcm16(chunk, rate).buffer); };
  l.finish = () => new Promise((resolve) => {   // the reply (as from /heard), or null: use the old way
    if (l.failed) return resolve(null);
    l.done = resolve;
    send(JSON.stringify({ end: true }));
    setTimeout(() => { give(null); socket.close(); }, LIVE_WAIT_MS);
  });
  l.abort = () => { l.failed = true; l.done = null; l.line?.remove(); socket.close(); };
  return l;
}

// One sentence: Meta's ears turn it into words, then Mythree translates it for the other phone.
async function send(sentence, rate, liveLine) {
  const mine = call;
  if (!mine) return;
  const line = liveLine?.line || addLine("mine", "…");
  if (liveLine) liveLine.line = line;   // late words so far go into this same line
  try {
    let m = liveLine ? await liveLine.finish() : null;   // heard live: ready almost at once
    if (!m) {   // the old way, one trip: the server hears, translates and shares it
      line.textContent = "…";
      const form = new FormData();
      form.append("audio", toWav(sentence, rate), "sentence.wav");
      form.append("person", mine.person);
      const reply = await api(`/api/calls/${mine.code}/heard`, { method: "POST", body: form });
      if (!reply.ok) throw new Error(await problemOf(reply));
      m = await reply.json();
    }
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
  realVoice.ctx ||= new AudioContext();   // made during a tap, or phones keep it silent
  realVoice.ctx.resume?.();
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
  const voiced = postJson(`/api/calls/${mine.code}/speak`, { n }).then(async (reply) => {
    if (!reply.ok) throw new Error("no own voice");
    return URL.createObjectURL(await reply.blob());
  });
  voiced.catch(() => {});   // handled below, after the wait
  await untilPaused();
  if (call !== mine) return;
  muted = true;
  dip(true);
  try {
    const sound = await voiced;
    addReplay(line, () => play(sound));
    await play(sound);
  } catch {
    line.querySelector("small")?.append(" · standard voice");
    addReplay(line, () => standardVoice(text, lang));
    await standardVoice(text, lang);
  } finally {
    muted = false;
    dip(false);
  }
}

// The other person's sentence arrived while my person is still talking: the words are already
// on the screen, and the voice waits for the pause. Playing at once would stop the listening
// and throw away the sentence my person is in the middle of (found in the phone test, 30 Oct).
function untilPaused() {
  return new Promise((resolve) => {
    const check = () => (speaking ? setTimeout(check, 200) : resolve());
    check();
  });
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

// --- Seeing each other (video) ------------------------------------------------------
// The picture and the real voice go straight from phone to phone (WebRTC); Mythree only passes
// on the notes the phones need to find each other. Grandpa's phone ("a" or "b") hears "ready"
// from the other camera; person "a" then sends an offer ("how to reach me"), and "b" answers.
// The translation still travels the usual way, and plays loud over the soft real voice.
const REAL_VOICE = 0.25;          // the other person's real voice, softly: their laugh and tone, under the translation
const REAL_VOICE_DIPPED = 0.08;   // while their translation plays
const VIDEO_WAIT_MS = 15000;      // no picture by then: the voice call simply goes on
const CAMERA = (facing) => ({ facingMode: facing, width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 20, max: 24 } });
const VIDEO_KBPS = 600;           // modest, like a WhatsApp call on weak internet: works on village mobile data

let media = null;                 // this phone's camera and microphone, for the whole call
let peer = null;                  // the line to the other phone: { pc, id, connected }
let facing = "user";              // front camera; 🔄 turns it around to show the fields or the temple
let offers = 0, lastOffer = 0, routes = null, videoTimer = null, captionTimer = null;
const realVoice = { ctx: null, gain: null };

const hasVideo = () => !!media?.getVideoTracks().length;

async function openMedia() {
  const audio = { echoCancellation: true, noiseSuppression: true, channelCount: 1 };
  try {
    return await navigator.mediaDevices.getUserMedia({ audio, video: CAMERA(facing) });
  } catch {
    return navigator.mediaDevices.getUserMedia({ audio });   // no camera, or not allowed: a voice call, as before
  }
}

function closeMedia() {
  media?.getTracks().forEach((t) => t.stop());
  media = null;
}

function sendNote(mine, note) {
  postJson(`/api/calls/${mine.code}/video`, { person: mine.person, ...note }).catch(() => {});
}

function showVideo() {   // my camera is on: show it small, and tell the other phone
  if (call.video) return;
  call.video = true;
  $("my-video").srcObject = media;
  $("my-video").play().catch(() => {});
  $("video").hidden = false;
  videoNote("Waiting for their camera… · వాళ్ళ కెమెరా కోసం చూస్తున్నాం…");
  sendNote(call, { kind: "ready" });
  clearTimeout(videoTimer);
  videoTimer = setTimeout(() => {
    if (peer?.connected) return;
    videoNote("The video couldn't connect. The voice call goes on · వీడియో రాలేదు, మాటలు కొనసాగుతాయి");
    videoTimer = setTimeout(() => { if (!peer?.connected) $("video").hidden = true; }, 6000);
  }, VIDEO_WAIT_MS);
}

function videoNote(text) {
  $("video-note").textContent = text;
}

function onNote(note, mine) {
  if (note.kind === "ready") {
    if (!note.reply && hasVideo()) sendNote(mine, { kind: "ready", reply: true });   // "me too"
    if (mine.person === "a") offer(mine);
  } else if (note.kind === "offer" && mine.person === "b") {
    answer(note, mine);
  } else if (note.kind === "answer" && mine.person === "a" && peer?.id === note.id) {
    peer.pc.setRemoteDescription({ type: "answer", sdp: note.sdp }).catch(() => {});
  } else if (note.kind === "bye") {
    closeVideo();
  }
}

async function offer(mine) {
  if (!hasVideo() || call !== mine || Date.now() - lastOffer < 4000) return;   // both said "ready" at once: one offer
  lastOffer = Date.now();
  const id = ++offers;
  const pc = await newPeer(mine, id);
  await pc.setLocalDescription(await pc.createOffer());
  await gathered(pc);
  if (peer?.pc === pc) sendNote(mine, { kind: "offer", id, sdp: pc.localDescription.sdp });
}

async function answer(note, mine) {
  if (!hasVideo() || call !== mine) return;
  const pc = await newPeer(mine, note.id);
  try {
    await pc.setRemoteDescription({ type: "offer", sdp: note.sdp });
    await pc.setLocalDescription(await pc.createAnswer());
  } catch {
    return;
  }
  await gathered(pc);
  if (peer?.pc === pc) sendNote(mine, { kind: "answer", id: note.id, sdp: pc.localDescription.sdp });
}

async function newPeer(mine, id) {
  closePeer();
  if (!routes) {   // how the phones may reach each other: direct, or through the relay
    const reply = await api(`/api/calls/${mine.code}/ice`).catch(() => null);
    routes = reply?.ok ? (await reply.json()).iceServers : [];
  }
  const pc = new RTCPeerConnection({ iceServers: routes });
  const line = peer = { pc, id, connected: false };
  // Only the picture goes along, not the real voice: a phone's microphone caught it from the
  // speaker and sent it again as new words (30 Oct). The translation in the speaker's own voice is enough.
  media.getVideoTracks().forEach((t) => pc.addTrack(t, media));
  pc.ontrack = ({ streams }) => showThem(streams[0]);
  pc.onconnectionstatechange = () => {
    if (peer !== line) return;
    if (pc.connectionState === "connected") {
      line.connected = true;
      videoNote("");
      $("video").hidden = false;
      modest(pc);
    } else if (pc.connectionState === "failed" && mine.person === "a") {
      videoNote("Connecting the video again… · వీడియో మళ్ళీ కలుపుతున్నాం…");
      offer(mine);
    }
  };
  return pc;
}

// The whole "how to reach me" in one note (not piece by piece): fewer trips through Mythree.
function gathered(pc) {
  return new Promise((done) => {
    if (pc.iceGatheringState === "complete") return done();
    const timer = setTimeout(done, 3000);
    pc.addEventListener("icegatheringstatechange", () => {
      if (pc.iceGatheringState === "complete") { clearTimeout(timer); done(); }
    });
  });
}

function modest(pc) {
  for (const sender of pc.getSenders()) {
    if (sender.track?.kind !== "video") continue;
    const settings = sender.getParameters();
    if (!settings.encodings?.length) continue;
    settings.encodings[0].maxBitrate = VIDEO_KBPS * 1000;
    sender.setParameters(settings).catch(() => {});
  }
}

function showThem(stream) {
  const picture = $("their-video");
  if (picture.srcObject === stream) return;
  picture.srcObject = stream;   // muted here: the real voice plays through realVoice, where it can be made soft
  picture.play().catch(() => {});
  if (!realVoice.ctx || !stream.getAudioTracks().length) return;
  realVoice.gain?.disconnect();
  realVoice.gain = realVoice.ctx.createGain();
  realVoice.gain.gain.value = REAL_VOICE;   // (phones ignore a video's own volume, so it goes through here)
  realVoice.ctx.createMediaStreamSource(stream).connect(realVoice.gain).connect(realVoice.ctx.destination);
  realVoice.ctx.resume?.();
}

function dip(down) {   // the real voice steps aside while the translation speaks
  const gain = realVoice.gain;
  if (gain) gain.gain.setTargetAtTime(down ? REAL_VOICE_DIPPED : REAL_VOICE, realVoice.ctx.currentTime, 0.15);
}

function caption(text) {   // the translation in big letters on the picture, before the voice is ready
  $("caption").textContent = text;
  clearTimeout(captionTimer);
  captionTimer = setTimeout(() => ($("caption").textContent = ""), 12000);
}

function closePeer() {
  peer?.pc.close();
  peer = null;
}

function closeVideo() {
  closePeer();
  clearTimeout(videoTimer);
  realVoice.gain?.disconnect();
  realVoice.gain = null;
  $("their-video").srcObject = $("my-video").srcObject = null;
  $("caption").textContent = "";
  $("video").hidden = true;
  if (call) call.video = false;
  routes = null;
}

$("flip").addEventListener("click", async () => {   // front camera ↔ back camera
  if (!hasVideo()) return;
  const old = media.getVideoTracks()[0];
  const want = facing === "user" ? "environment" : "user";
  old.stop();   // some phones open only one camera at a time
  const camera = (f) => navigator.mediaDevices.getUserMedia({ video: CAMERA(f) }).then((s) => s.getVideoTracks()[0], () => null);
  let fresh = await camera(want);
  if (fresh) facing = want;
  else fresh = await camera(facing);   // only one camera: keep the one we had
  if (!fresh) return;
  media.removeTrack(old);
  media.addTrack(fresh);
  peer?.pc.getSenders().find((s) => s.track === old)?.replaceTrack(fresh);
  $("my-video").classList.toggle("mirror", facing === "user");
  $("my-video").srcObject = media;
});

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
  const pcm = toPcm16(all, rate);

  const head = new DataView(new ArrayBuffer(44));
  const text = (at, s) => [...s].forEach((c, i) => head.setUint8(at + i, c.charCodeAt(0)));
  text(0, "RIFF"); head.setUint32(4, 36 + pcm.byteLength, true); text(8, "WAVE");
  text(12, "fmt "); head.setUint32(16, 16, true); head.setUint16(20, 1, true);
  head.setUint16(22, 1, true); head.setUint32(24, TARGET_RATE, true);
  head.setUint32(28, TARGET_RATE * 2, true); head.setUint16(32, 2, true); head.setUint16(34, 16, true);
  text(36, "data"); head.setUint32(40, pcm.byteLength, true);
  return new Blob([head, pcm], { type: "audio/wav" });
}

// Sound from the microphone (numbers from -1 to 1, at the phone's rate) → 16 kHz, 16-bit, as Meta wants.
function toPcm16(all, rate) {
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
  return pcm;
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
