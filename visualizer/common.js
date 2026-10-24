// Shared helpers for every visualization variant.
const NS = "http://www.w3.org/2000/svg";
const $ = id => document.getElementById(id);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const WORD = { OBSERVE: "WATCHING", DEEPEN: "OPEN NEW ROOM", LURE: "LEAVE BAIT", SLOW: "SLOW DOWN", CONTAIN: "LOCKED OUT" };
let svg;

function el(tag, attrs = {}, parent = svg, text) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text !== undefined) e.textContent = text;
  parent.appendChild(e);
  return e;
}

// 0..1 danger level derived from the Maze state the real code computed.
function threat(s) {
  return Math.min(1, ((s.state.exposure + s.state.alert + s.state.progress + s.state.intel * 0.5) / 8.5) * 1.15);
}
const threatColor = t => (t > .66 ? css("--bad") : t > .33 ? css("--gold") : css("--ok"));

function setButtons(disabled) { document.querySelectorAll("button").forEach(b => b.disabled = disabled); }

/**
 * mount({ viewBox, build(), play(data, name), buttons, order })
 * buttons: [{ name, label }] shown under the scene (default: skilled attacker + beginner)
 * order:   scenario names replayed in sequence when ?loop is set
 */
function mount({ viewBox = "0 0 960 440", build, play, buttons, order }) {
  const q = new URLSearchParams(location.search);
  if (q.has("embed")) document.body.classList.add("embed");
  buttons = buttons || [{ name: "skilled", label: "Skilled attacker" }, { name: "novice", label: "Beginner" }];
  order = order || ["skilled", "novice"];
  $("app").innerHTML = `
    <div class="top"><b>LabyrinthAI</b><a href="/">← all versions</a></div>
    <div class="scene"><svg id="svg" viewBox="${viewBox}" role="img" aria-label="LabyrinthAI animation"></svg></div>
    <div class="result" id="result" hidden></div>
    <div class="bar">
      <div class="caption" id="cap">Pick a visitor →</div>
      <div class="controls">${buttons.map((b, i) => `<button data-n="${b.name}" class="${i ? "alt" : ""}">${b.label}</button>`).join("")}</div>
    </div>`;
  svg = $("svg");
  let running = false, idx = 0;
  async function run(name) {
    if (running) return;
    running = true; setButtons(true);
    $("result").hidden = true;
    build();
    $("cap").textContent = "…";
    try {
      const data = await (await fetch("/api/run?scenario=" + name)).json();
      await play(data, name);
    } catch (e) { $("cap").textContent = "Server not reachable."; }
    setButtons(false); running = false;
    if (q.has("loop")) {  // keep replaying in sequence (used by the side-by-side wall)
      await sleep(2500);
      idx = (idx + 1) % order.length;
      run(order[idx]);
    }
  }
  build();
  document.querySelectorAll("button").forEach(b => b.onclick = () => run(b.dataset.n));
  if (q.get("auto")) { idx = Math.max(0, order.indexOf(q.get("auto"))); run(q.get("auto")); }
}

/** Big end-of-run banner. kind: "ok" | "warn" | "bad". */
function showResult(kind, title, sub) {
  const r = $("result");
  r.className = "result " + kind;
  r.innerHTML = `<b>${title}</b><span>${sub}</span>`;
  r.hidden = false;
}

function endCaption(data, caught) {
  $("cap").textContent = data.outcome === "contained" ? caught : "Harmless. The AI just kept watching.";
}
