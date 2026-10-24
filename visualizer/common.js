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

/** mount({ viewBox, build(), play(data) }) - draws the page chrome and wires the buttons. */
function mount({ viewBox = "0 0 960 440", build, play }) {
  const q = new URLSearchParams(location.search);
  if (q.has("embed")) document.body.classList.add("embed");
  const app = $("app");
  app.innerHTML = `
    <div class="top"><b>LabyrinthAI</b><a href="/">← all versions</a></div>
    <div class="scene"><svg id="svg" viewBox="${viewBox}" role="img" aria-label="LabyrinthAI animation"></svg></div>
    <div class="bar">
      <div class="caption" id="cap">Pick an attacker →</div>
      <div class="controls"><button id="b-skilled">Skilled attacker</button><button id="b-novice" class="alt">Beginner</button></div>
    </div>`;
  svg = $("svg");
  let running = false;
  async function run(name) {
    if (running) return;
    running = true; setButtons(true);
    build();
    $("cap").textContent = "…";
    try {
      const data = await (await fetch("/api/run?scenario=" + name)).json();
      await play(data);
    } catch (e) { $("cap").textContent = "Server not reachable."; }
    setButtons(false); running = false;
  }
  build();
  $("b-skilled").onclick = () => run("skilled");
  $("b-novice").onclick = () => run("novice");
  if (q.get("auto")) run(q.get("auto"));
}

function endCaption(data, caught) {
  $("cap").textContent = data.outcome === "contained" ? caught : "Harmless. The AI just kept watching.";
}
