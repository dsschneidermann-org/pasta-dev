// A minimal DOM for running the timeline renderer under Node: just the element methods it calls,
// recording what it creates and sets so a check can inspect the drawing and drive playback.
"use strict";
const fs = require("fs");

// The elements timeline.html gives the renderer by id.
const PAGE_IDS = ["tl-stage", "tl-minimap", "tl-scrub", "tl-play", "tl-clock", "tl-counts", "tl-feed",
  "tl-live", "tl-empty"];

function makeElement(tag, created) {
  const element = {
    tag, attrs: {}, children: [], dataset: {}, textContent: "", value: "", listeners: {},
    style: { setProperty() {} },
    classList: {
      set: new Set(),
      add(name) { this.set.add(name); },
      remove(name) { this.set.delete(name); },
      toggle(name, on) { if (on) this.set.add(name); else this.set.delete(name); },
    },
    setAttribute(key, value) {
      if (value === undefined || (typeof value === "number" && !Number.isFinite(value))) {
        throw new Error(`${tag} given ${key}=${value}`);
      }
      this.attrs[key] = value;
    },
    appendChild(child) { this.children.push(child); return child; },
    append(...children) { this.children.push(...children); },
    replaceChildren(...children) { this.children = children; },
    addEventListener(type, listener) { this.listeners[type] = listener; },
    getBoundingClientRect() { return { width: 1000 }; },
    closest() { return null; },
    setPointerCapture(pointerId) { this.captured = pointerId; },
    releasePointerCapture(pointerId) { if (this.captured === pointerId) this.captured = null; },
    hasPointerCapture(pointerId) { return this.captured === pointerId; },
  };
  created.push(element);
  return element;
}

// Runs the renderer at `scriptPath` on the payload at `payloadPath` (or `options.payloadText`), up
// to the point the page has loaded: drawn, resting at its end, its events socket open. The page
// says it was rendered from `options.eventCount` log events (3 by default), and the viewer prefers
// reduced motion when `options.reducedMotion` is set.
function loadTimeline(payloadPath, scriptPath, options = {}) {
  const created = [];
  const ids = {};
  for (const id of PAGE_IDS) ids[id] = makeElement(id, created);
  ids["tl-play"].textContent = "Play";                       // as timeline.html renders the button
  const payloadText = options.payloadText ?? fs.readFileSync(payloadPath, "utf8");
  ids["timeline-data"] = Object.assign(makeElement("script", created), {
    textContent: payloadText, dataset: { workspace: "ws:check", events: String(options.eventCount ?? 3) },
  });

  let onReady = null;
  const frames = [];
  const timers = [];
  const sockets = [];
  global.document = {
    getElementById: (id) => ids[id] ?? null,
    createElementNS: (_namespace, tag) => makeElement(tag, created),
    createElement: (tag) => makeElement(tag, created),
    addEventListener(type, listener) { if (type === "DOMContentLoaded") onReady = listener; },
  };
  global.window = { matchMedia: () => ({ matches: Boolean(options.reducedMotion) }), addEventListener() {} };
  global.requestAnimationFrame = (callback) => frames.push(callback);
  global.cancelAnimationFrame = () => { frames.length = 0; };
  global.setTimeout = (callback) => timers.push(callback);
  // Records each socket the renderer opens; a check delivers messages through `push`.
  global.WebSocket = class {
    constructor(url) {
      this.url = url;
      this.closed = false;
      sockets.push(this);
    }
    close() { this.closed = true; }
  };

  (0, eval)(fs.readFileSync(scriptPath, "utf8"));           // global scope, as an inline <script>
  if (onReady === null) throw new Error("the renderer did not wait for DOMContentLoaded");
  onReady();

  let now = 0;
  const stage = ids["tl-stage"];
  const hasClass = (element, name) => String(element.attrs?.class ?? "").split(" ").includes(name);
  // What a redraw left on the stage, without the elements it replaced.
  function onStage(name, node = stage) {
    return (node.children ?? []).flatMap((child) => [...(hasClass(child, name) ? [child] : []), ...onStage(name, child)]);
  }
  return {
    data: JSON.parse(payloadText),
    ids,
    created,
    sockets,
    classed: (name) => created.filter((element) => hasClass(element, name)),
    onStage,
    playhead: () => parseFloat(ids["tl-scrub"].value),
    pendingFrames: () => frames.length,
    pendingTimers: () => timers.length,
    runTimers() { timers.splice(0).forEach((callback) => callback()); },
    // Delivers a server message on the latest socket, as the browser would.
    push(message) { sockets.at(-1).onmessage({ data: JSON.stringify(message) }); },
    closeSocket() { sockets.at(-1).onclose({ reason: "check" }); },
    runFrames(count) {
      for (let i = 0; i < count && frames.length; i++) frames.shift()((now += 16.7));
    },
    scrubTo(p) {
      ids["tl-scrub"].value = String(p);
      ids["tl-scrub"].listeners.input();
    },
    pointer(type, clientX) {
      stage.listeners[type]({ pointerId: 7, button: 0, clientX });
    },
    // Whether the stage swallowed the click that would follow a pointer release.
    clickSwallowed() {
      let prevented = false;
      stage.listeners.click({ preventDefault() { prevented = true; }, stopPropagation() {} });
      return prevented;
    },
  };
}

function assertClose(actual, expected, message) {
  if (Math.abs(actual - expected) > 1e-9) throw new Error(`${message}: ${actual} is not ${expected}`);
}

module.exports = { loadTimeline, assertClose };
