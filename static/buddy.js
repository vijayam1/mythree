// Mythree's koel (కోకిల, the bird with the sweetest voice) flies around the page,
// flapping its wings,
// and goes wherever the action is.
//   sleeping  → rests in its nest at the top
//   listening → hovers by the microphone, drifting a little now and then
//   hearing   → flies to the person who is talking
//   thinking / speaking → flies to the newest chat bubble
//   goodbye   → waves a wing, then flies home to sleep
// She lands on a little branch when she settles, and moves only now and then,
// so people can read in peace. "Pause animation" keeps her still in her nest.

const buddy = document.getElementById("buddy");
const nest = document.getElementById("nest");
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
let pos = { x: 0, y: 0 }, landTimer, wanderTimer;
const still = () => document.body.classList.contains("still");

function size() { return { w: buddy.offsetWidth, h: buddy.offsetHeight }; }

function place(x, y, fly = true) {
  const { w, h } = size();
  x = Math.max(4, Math.min(innerWidth - w - 4, x));
  y = Math.max(4, Math.min(innerHeight - h - 4, y));
  if (Math.abs(x - pos.x) < 3 && Math.abs(y - pos.y) < 3) return;
  if (!fly || reduce || still()) { fly = false; buddy.style.transition = "none"; }
  if (Math.abs(x - pos.x) > 6) buddy.classList.toggle("left", x < pos.x);  // face the way it flies
  buddy.classList.add("flying");
  buddy.style.transform = `translate(${x}px, ${y}px)`;
  pos = { x, y };
  buddy.getBoundingClientRect();
  buddy.style.transition = "";
  clearTimeout(landTimer);
  landTimer = setTimeout(() => {
    buddy.classList.remove("flying");
    if (fly) {   // a little bounce as she lands on her branch
      buddy.classList.add("landing");
      setTimeout(() => buddy.classList.remove("landing"), 400);
    }
  }, fly ? 1150 : 0);
}

// Where to go, as a point beside an element on screen.
function beside(el, side = "right") {
  const r = el.getBoundingClientRect(), { w, h } = size();
  const x = side === "left" ? r.left - w + 10 : r.right - 10;
  return { x, y: r.top + r.height / 2 - h / 2 };
}

function target() {
  const mood = document.body.dataset.mood;
  if (mood === "goodbye") return pos;   // wave where she is
  const mic = document.getElementById("start");
  const bubbles = document.querySelectorAll("#heard li");
  const last = bubbles[bubbles.length - 1];
  if (!still() && (mood === "thinking" || mood === "speaking") && last) {
    return beside(last, last.dataset.side === "b" ? "left" : "right");
  }
  if (!still() && mood === "hearing") {
    const who = document.querySelector('.person[aria-pressed="true"]');
    return beside(who, who.dataset.person === "a" ? "left" : "right");
  }
  if (!still() && (mood === "listening" || mood === "error")) return beside(mic, "right");
  const r = nest.getBoundingClientRect(), { w, h } = size();   // sleeping: home in the nest
  return { x: r.left + r.width / 2 - w / 2, y: r.top + r.height / 2 - h / 2 };
}

function go(fly = true) {
  const t = target();
  place(t.x, t.y, fly);
}

// Now and then, a small hop while listening, so she feels alive (not too often: people are reading).
function wander() {
  clearInterval(wanderTimer);
  wanderTimer = setInterval(() => {
    if (document.body.dataset.mood !== "listening" || still()) return;
    const t = target();
    place(t.x + (Math.random() * 40 - 20), t.y + (Math.random() * 30 - 15));
  }, 14000);
}

new MutationObserver(() => go()).observe(document.body, { attributes: true, attributeFilter: ["data-mood"] });
new MutationObserver(() => go()).observe(document.getElementById("heard"), { childList: true });
document.querySelectorAll(".person").forEach((p) => p.addEventListener("click", () => setTimeout(go, 50)));
addEventListener("resize", () => go(false));
addEventListener("scroll", () => go(false), { passive: true });

// A speech bubble above her for a moment.
function bubble(text, ms = 2600) {
  document.getElementById("hello").textContent = text;
  buddy.classList.remove("happy");
  void buddy.offsetWidth;   // restart the animation
  buddy.classList.add("happy");
  clearTimeout(buddy.happyTimer);
  buddy.happyTimer = setTimeout(() => buddy.classList.remove("happy"), ms);
}

// Tap her: she flaps her wings happily and says hello.
const greetings = ["నమస్తే! I'm Mythree", "Hello! మాట్లాడదామా? 😊", "I'm listening for you 👂"];
let greet = 0;
buddy.querySelector("svg").addEventListener("click", () => {
  bubble(greetings[greet++ % greetings.length]);
});

// --- Her beak follows the real voice: the louder the sound, the wider it opens ---
// It only *listens* to a copy of the sound (captureStream), so it can never hold up the voice.
// Browsers without captureStream get the plain talking animation instead.
let voiceCtx;
function lipsync(audio) {
  if (!audio.captureStream) return;
  const begin = () => {
    try {
      voiceCtx ??= new AudioContext();
      voiceCtx.resume();
      const ears = voiceCtx.createAnalyser();
      ears.fftSize = 512;
      voiceCtx.createMediaStreamSource(audio.captureStream()).connect(ears);   // not connected to the speakers
      const wave = new Uint8Array(ears.fftSize);
      buddy.classList.add("lipsync");
      const tick = () => {
        if (audio.ended || audio.paused) {
          buddy.classList.remove("lipsync");
          return buddy.style.setProperty("--beak", "0deg");
        }
        ears.getByteTimeDomainData(wave);
        let sum = 0;
        for (const v of wave) sum += (v - 128) ** 2;
        const level = Math.sqrt(sum / wave.length) / 128;
        buddy.style.setProperty("--beak", `${Math.min(26, level * 220).toFixed(1)}deg`);
        requestAnimationFrame(tick);
      };
      tick();
    } catch { buddy.classList.remove("lipsync"); }
  };
  audio.addEventListener("playing", begin, { once: true });
}

// Waving goodbye when listening stops, then home to sleep.
function goodbye() {
  bubble("Bye! మళ్ళీ కలుద్దాం 👋", 2000);
}

window.mythreeBird = { lipsync, goodbye, bubble };

// Arrive: fly in from the side of the screen, land in the nest, and say hello.
place(innerWidth + 40, 40, false);
setTimeout(() => go(), 300);
setTimeout(() => bubble("నమస్తే! I'm Mythree", 3000), 1600);
wander();
