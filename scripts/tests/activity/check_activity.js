// Checks for src/templates/_activity.js, the activity timeline's renderer, under Node against a stub
// DOM and synthetic payloads - no browser, server or data dir. From the repository root:
//   node scripts/tests/activity/check_activity.js src/templates/_activity.js
// Prints PASS or FAIL per check and exits 1 if any failed.
"use strict";
const fs = require("fs");
const assert = require("assert");

const IDS = ["ac-stage", "ac-minimap", "ac-scrub", "ac-play", "ac-clock", "ac-feed", "ac-live", "ac-empty",
  "ac-feed-toggle", "ac-body", "ac-open", "ac-close"];
const RATE = 20;

// A 12-hour locale and a fixed zone, so a renderer that leaves the hour cycle to the locale shows AM/PM here.
process.env.TZ = "UTC";
for (const name of ["toLocaleString", "toLocaleTimeString", "toLocaleDateString"]) {
  const original = Date.prototype[name];
  Date.prototype[name] = function (locale, options) { return original.call(this, locale ?? "en-US", options); };
}

// Just the element methods the renderer calls, recording what it creates and sets.
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
    focus() { created.focused = element; },
  };
  created.push(element);
  return element;
}

// One line of calls at the epoch seconds in `times`, all within one active stretch, laid out as the Python side would.
function payload(times) {
  const t0 = times[0], t1 = times.at(-1), duration = (t1 - t0) / RATE;
  const marks = times.map((at, index) => ({ p: (at - t0) / RATE, at, kind: "call",
    tool: index % 2 ? "getPage" : "mutatePageBatch", write: index % 2 === 0, bytes: 2048 }));
  return { start: t0, end: t1, duration, baseRate: RATE, segments: [[t0, t1, 0, duration]], lanes: 1,
    lines: [{ id: "feature-brief:p", title: "Page", colour: "feature-brief", path: ["Features", "Feature", "Page"],
      href: "/ws:check/page/feature-brief:p", lane: 0, p0: 0, p1: duration, marks }],
    feed: marks.map((mark, index) => ({ p: mark.p, line: 0, mark: index })) };
}
const EMPTY = { start: 990, end: 990, duration: 0, baseRate: RATE, segments: [], lanes: 0, lines: [], feed: [] };
const BEFORE = payload([1000, 1010, 1020, 1030]);   // ends at 1.5 s, which is 1030 s
const SLID = payload([1010, 1020, 1030, 1040]);     // the window slid past 1000 s and a call landed at 1040 s

function load(script, data, options = {}) {
  const created = [], ids = {}, documentListeners = {}, frames = [], timers = [], sockets = [];
  for (const id of IDS) ids[id] = makeElement(id, created);
  ids["ac-play"].textContent = "Play";                         // as _activity.html serves them
  ids["ac-feed"].hidden = true;
  ids["ac-feed-toggle"].textContent = "▸";
  ids["ac-body"].hidden = true;
  ids["activity-data"] = Object.assign(makeElement("script", created), {
    textContent: JSON.stringify(data), dataset: { workspace: "ws:check", page: options.page ?? "feature-brief:p",
      digest: options.digest ?? "rendered" } });
  global.document = {
    getElementById: (id) => ids[id] ?? null,
    createElementNS: (_namespace, tag) => makeElement(tag, created),
    createElement: (tag) => makeElement(tag, created),
    addEventListener(type, listener) { documentListeners[type] = listener; },
  };
  global.window = { matchMedia: () => ({ matches: Boolean(options.reducedMotion) }), addEventListener() {} };
  global.requestAnimationFrame = (callback) => frames.push(callback);
  global.cancelAnimationFrame = () => { frames.length = 0; };
  global.setTimeout = (callback) => timers.push(callback);
  global.WebSocket = class { constructor(url) { this.url = url; sockets.push(this); } close() {} };
  (0, eval)(fs.readFileSync(script, "utf8"));        // global scope, as an inline <script>
  assert.ok(documentListeners.DOMContentLoaded, "the renderer waits for DOMContentLoaded");
  documentListeners.DOMContentLoaded();
  let now = 0;
  return {
    ids, created, sockets, documentListeners,
    playhead: () => parseFloat(ids["ac-scrub"].value),
    playing: () => frames.length > 0,
    button: () => ids["ac-play"].textContent,
    push(message) { sockets.at(-1).onmessage({ data: JSON.stringify(message) }); },
    runFrames(count) { for (let i = 0; i < count && frames.length; i++) frames.shift()((now += 16.7)); },
    runTimers() { timers.splice(0).forEach((callback) => callback()); },
    scrubTo(p) { ids["ac-scrub"].value = String(p); ids["ac-scrub"].listeners.input(); },
    classed: (name) => created.filter((element) => String(element.attrs?.class ?? "").split(" ").includes(name)),
  };
}

function close(actual, expected, message) {
  assert.ok(Math.abs(actual - expected) < 1e-9, `${message}: ${actual} is not ${expected}`);
}

const checks = {
  "opens at rest at the end in Replay, its socket scoped to its page"(script) {
    const page = load(script, BEFORE);
    close(page.playhead(), 1.5, "the playhead rests at the end");
    assert.ok(!page.playing() && page.button().includes("Replay"));
    assert.strictEqual(page.sockets[0].url, "/ws/activity/ws:check?page=feature-brief%3Ap&digest=rendered");
    assert.strictEqual(load(script, BEFORE, { page: "" }).sockets[0].url, "/ws/activity/ws:check?digest=rendered");
  },
  "draws every call, read or write, as the same thick tick, labelled, and never scales a passed mark"(script) {
    const page = load(script, BEFORE);
    const ticks = page.classed("ac-call");
    assert.ok(ticks.length >= 8 && ticks.every((tick) => tick.attrs.y2 - tick.attrs.y1 === 12));
    assert.strictEqual(page.classed("ac-write").length, 0);
    assert.ok(page.classed("ac-label").some((label) => label.textContent === "mutatePageBatch 2.0 KB"));
    page.ids["ac-play"].listeners.click();           // Replay from the start
    page.runFrames(200);
    assert.ok(!page.created.some((element) => element.classList.set.has("fresh")));
  },
  "hovering a line or its feed link names its whole path"(script) {
    const page = load(script, BEFORE);
    const path = "Features › Feature › Page";
    assert.ok(page.created.some((element) => element.tag === "title" && element.textContent === path));
    assert.ok(page.created.some((element) => element.tag === "a" && element.title === path));
  },
  "shows every time in 24-hour form"(script) {
    const page = load(script, payload([54000, 54010, 54020, 54030]));   // 15:00:00 to 15:00:30 UTC
    const clock = page.ids["ac-clock"].textContent;
    const times = page.created.filter((element) => element.tag === "time").map((element) => element.textContent);
    assert.ok(clock.includes("15:00:30"), clock);
    assert.ok(times.some((text) => text.includes("15:00")), times.join(" | "));
    assert.ok([clock, ...times].every((text) => !/AM|PM/i.test(text)), [clock, ...times].join(" | "));
  },
  "the legend's symbol shows and hides the latest changes"(script) {
    const page = load(script, BEFORE);
    const toggle = page.ids["ac-feed-toggle"];
    const feed = page.ids["ac-feed"];
    assert.ok(feed.hidden);
    toggle.listeners.click();
    assert.ok(!feed.hidden && toggle.attrs["aria-expanded"] === "true" && toggle.textContent === "▾");
    toggle.listeners.click();
    assert.ok(feed.hidden && toggle.attrs["aria-expanded"] === "false" && toggle.textContent === "▸");
  },
  "the activity opens from its link, laid out again, and closes from its symbol"(script) {
    const page = load(script, BEFORE);
    const body = page.ids["ac-body"], open = page.ids["ac-open"], close = page.ids["ac-close"];
    const minimap = page.ids["ac-minimap"];
    assert.ok(body.hidden && !open.hidden);
    minimap.getBoundingClientRect = () => ({ width: 600 });      // the size it has once shown
    open.listeners.click();
    assert.ok(!body.hidden && open.hidden && open.attrs["aria-expanded"] === "true");
    assert.strictEqual(minimap.attrs.viewBox, "0 0 600 48", "the stage is laid out again once shown");
    assert.strictEqual(page.created.focused, close);
    close.listeners.click();
    assert.ok(body.hidden && !open.hidden && open.attrs["aria-expanded"] === "false");
    assert.strictEqual(page.created.focused, open);
  },
  "a heartbeat changes nothing"(script) {
    const page = load(script, BEFORE);
    page.push({ heartbeat: 1 });
    close(page.playhead(), 1.5, "the playhead stays");
    assert.ok(!page.playing());
  },
  "a live payload is played into from the moment the viewer rested at"(script) {
    const page = load(script, BEFORE);
    page.push({ timeline: SLID, digest: "slid" });
    close(page.playhead(), 1.0, "1030 s sits at 1.0 s on the slid clock");
    assert.ok(page.playing(), "time moves ahead to the new mark");
    page.runFrames(200);
    close(page.playhead(), 1.5, "it stops at the new end");
    assert.ok(page.button().includes("Replay"));
  },
  "with reduced motion a live payload is jumped to at rest"(script) {
    const page = load(script, BEFORE, { reducedMotion: true });
    page.push({ timeline: SLID, digest: "slid" });
    close(page.playhead(), 1.5, "at the new end");
    assert.ok(!page.playing());
  },
  "a paused viewer keeps the moment they were looking at"(script) {
    const page = load(script, BEFORE);
    page.scrubTo(0.75);                               // 1015 s
    page.push({ timeline: SLID, digest: "slid" });
    close(page.playhead(), 0.25, "1015 s sits at 0.25 s on the slid clock");
    assert.ok(!page.playing());
  },
  "an empty timeline brings up the map on its first payload and plays it"(script) {
    const page = load(script, EMPTY);
    assert.ok(page.ids["ac-live"].hidden && !page.ids["ac-empty"].hidden);
    page.push({ timeline: BEFORE, digest: "before" });
    assert.ok(!page.ids["ac-live"].hidden && page.ids["ac-empty"].hidden);
    close(page.playhead(), 0, "it starts from the first mark");
    assert.ok(page.playing());
  },
  "takes no Space shortcut, declares no global main, and reconnects a second after a close with the latest digest"(script) {
    const page = load(script, BEFORE);
    assert.ok(!("keydown" in page.documentListeners));
    assert.strictEqual(typeof global.main, "undefined");
    page.push({ timeline: SLID, digest: "slid" });
    page.sockets[0].onclose({ reason: "check" });
    page.runTimers();
    assert.strictEqual(page.sockets.length, 2);
    assert.strictEqual(page.sockets[1].url, "/ws/activity/ws:check?page=feature-brief%3Ap&digest=slid");
  },
};

const script = process.argv[2] ?? "src/templates/_activity.js";
let failed = 0;
for (const [name, check] of Object.entries(checks)) {
  try {
    check(script);
    console.log(`PASS ${name}`);
  } catch (error) {
    failed++;
    console.log(`FAIL ${name}\n  ${error.message}`);
  }
}
process.exit(failed ? 1 : 0);
