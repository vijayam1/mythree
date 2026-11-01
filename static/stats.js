// Vijaya's private Visitors page: counts from /api/stats (behind the family passcode), refreshed every minute.
const $ = (id) => document.getElementById(id);
let passcode = (() => { try { return localStorage.getItem("mythree-passcode") || ""; } catch { return ""; } })();

async function api(url) {
  const reply = await fetch(url, { headers: { "X-Mythree-Passcode": passcode } });
  if (reply.status !== 401) return reply;
  const typed = prompt("Mythree passcode · పాస్‌కోడ్");
  if (!typed) return reply;
  passcode = typed.trim();
  try { localStorage.setItem("mythree-passcode", passcode); } catch { /* private window */ }
  return api(url);
}

const number = (n) => (n == null ? "–" : n.toLocaleString());

async function show() {
  const reply = await api("/api/stats");
  if (!reply.ok) return ($("when").textContent = "Couldn't read the numbers just now.");
  const s = await reply.json();
  $("today-voices").textContent = number(s.today.voices || 0);
  $("today-sentences").textContent = number(s.today.sentences || 0);
  $("today-characters").textContent = number(s.today.characters || 0);
  $("today-characters-what").textContent = `voice characters used, of ${number(s.characters_per_day)} a day`;
  $("week-voices").textContent = number(s.week.voices);
  $("week-sentences").textContent = number(s.week.sentences);
  $("in-use").textContent = s.voices_in_use == null ? "–" : `${s.voices_in_use} of ${s.voice_places}`;
  $("characters").textContent = number(s.characters_left);
  $("reserve").textContent = s.characters_left == null ? ""
    : s.characters_left > s.family_reserve
      ? `Visitors may use about ${number(s.characters_left - s.family_reserve)} more; ${number(s.family_reserve)} are kept for the family.`
      : "The family's reserve is reached: visitors now hear a standard voice.";
  showCounts("languages", s.week.languages);
  showCounts("heard-in", s.week.heard_in || {});
  const closes = new Date(s.open_until * 1000);
  $("when").textContent = `Updated ${new Date().toLocaleTimeString()}. The Try page closes ${closes.toLocaleString()}.`;
}

$("refresh").addEventListener("click", show);
show();
setInterval(show, 60_000);

// One list of languages, most used first: the languages people spoke, or the ones they chose to hear.
function showCounts(id, counts) {
  const rows = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  $(id).replaceChildren(...(rows.length ? rows : [["No one yet", ""]]).map(([name, n]) => {
    const li = document.createElement("li");
    const left = document.createElement("span");
    const right = document.createElement("b");
    left.textContent = name;
    right.textContent = n;
    li.append(left, right);
    return li;
  }));
}
