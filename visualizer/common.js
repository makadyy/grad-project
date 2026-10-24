// Small helpers for the LabyrinthAI overview page.
const NS = "http://www.w3.org/2000/svg";
const $ = id => document.getElementById(id);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
let svg;

function el(tag, attrs = {}, parent = svg, text) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text !== undefined) e.textContent = text;
  parent.appendChild(e);
  return e;
}

// 0..1 danger level from the Maze state the real code computed.
function threat(s) {
  return Math.min(1, ((s.state.exposure + s.state.alert + s.state.progress + s.state.intel * 0.5) / 8.5) * 1.15);
}
const threatColor = t => (t > .66 ? css("--bad") : t > .33 ? css("--gold") : css("--ok"));

/** Big end-of-run banner. kind: "ok" | "warn" | "bad". */
function showResult(kind, title, sub) {
  const r = $("result");
  r.className = "result " + kind;
  r.innerHTML = `<b>${title}</b><span>${sub}</span>`;
  r.hidden = false;
}

/** mount({ viewBox, buttons: [{name,label}], build(), play(data, name) }) draws the page and wires the buttons. */
function mount({ viewBox, buttons, build, play }) {
  $("app").innerHTML = `
    <div class="top"><b>LabyrinthAI</b></div>
    <div class="scene"><svg id="svg" viewBox="${viewBox}" role="img" aria-label="LabyrinthAI animation"></svg></div>
    <div class="result" id="result" hidden></div>
    <div class="bar">
      <div class="caption" id="cap">Pick a visitor →</div>
      <div class="controls">${buttons.map((b, i) => `<button data-n="${b.name}" class="${i ? "alt" : ""}">${b.label}</button>`).join("")}</div>
    </div>`;
  svg = $("svg");
  let running = false;
  const setButtons = off => document.querySelectorAll("button").forEach(b => b.disabled = off);
  async function run(name) {
    if (running) return;
    running = true; setButtons(true);
    $("result").hidden = true;
    build();
    $("cap").textContent = "…";
    try {
      await play(await (await fetch("/api/run?scenario=" + name)).json(), name);
    } catch (e) { $("cap").textContent = "Server not reachable."; }
    setButtons(false); running = false;
  }
  build();
  document.querySelectorAll("button").forEach(b => b.onclick = () => run(b.dataset.n));
  const auto = new URLSearchParams(location.search).get("auto");   // e.g. /?auto=skilled starts a run on load
  if (auto) run(auto);
}
