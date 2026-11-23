// Draws and replays the timeline payload. Every layout decision - lanes, playback positions, the
// playback clock, the order stations are narrated in - arrives in the payload; this script only
// draws each payload it is given - the page's, then every live one its events socket streams -
// and moves the playhead.
function main() {
  const dataNode = document.getElementById("timeline-data");
  if (!dataNode) return;
  let data = JSON.parse(dataNode.textContent);
  const workspaceId = dataNode.dataset.workspace;

  const PX = 120;          // pixels per playback second
  const LANE_H = 18;
  const AXIS_H = 34;
  const X0 = 16;           // left margin, so the first station is not cut in half
  const HEAD = 0.7;        // how far across the stage the playhead rides
  const FRESH = 0.6;       // playback seconds a station stays highlighted after the playhead passes
  const SPEAK = 1.5;       // playback seconds a station's label stays up after it is passed
  const MAX_STEP = 0.1;    // most playback seconds one frame advances, so a stalled frame never skips the replay ahead
  const FEED_SIZE = 6;
  const SVG = "http://www.w3.org/2000/svg";

  const stage = document.getElementById("tl-stage");
  const minimap = document.getElementById("tl-minimap");
  const slider = document.getElementById("tl-scrub");
  const playButton = document.getElementById("tl-play");
  const clock = document.getElementById("tl-clock");
  const counts = document.getElementById("tl-counts");
  const feedList = document.getElementById("tl-feed");
  const live = document.getElementById("tl-live");
  const empty = document.getElementById("tl-empty");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  let segments = [];
  const x = (p) => X0 + p * PX;
  const y = (lane) => AXIS_H + lane * LANE_H + LANE_H / 2;
  const pagePath = (pageId) => `/${workspaceId}/page/${pageId}`;

  function el(name, attrs, parent) {
    const node = document.createElementNS(SVG, name);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    if (parent) parent.appendChild(node);
    return node;
  }

  // --- the playback clock: the payload's segments, read in either direction ---
  function segmentAt(value, startKey) {
    let low = 0;
    let high = segments.length - 1;
    while (low < high) {
      const mid = (low + high + 1) >> 1;
      if (segments[mid][startKey] <= value) low = mid; else high = mid - 1;
    }
    return segments[low];
  }

  function timeAt(p) {
    if (!segments.length) return data.start;
    const s = segmentAt(p, "p0");
    const u = Math.min(1, Math.max(0, (p - s.p0) / (s.p1 - s.p0)));
    return s.t0 + u * (s.t1 - s.t0);
  }

  function playbackAt(t) {
    if (!segments.length) return 0;
    const s = segmentAt(t, "t0");
    const u = Math.min(1, Math.max(0, (t - s.t0) / (s.t1 - s.t0)));
    return s.p0 + u * (s.p1 - s.p0);
  }

  // --- the stage, drawn per payload and between payloads only clipped and panned ---
  let clipRect = null;
  let world = null;
  let playhead = null;
  let lineNodes = [];

  function draw() {
    segments = data.segments.map(([t0, t1, p0, p1]) => ({ t0, t1, p0, p1 }));
    const height = AXIS_H + data.lanes * LANE_H + LANE_H / 2;
    stage.replaceChildren();
    stage.setAttribute("height", height);
    const clip = el("clipPath", { id: "tl-clip" }, el("defs", {}, stage));
    clipRect = el("rect", { x: -X0, y: 0, width: 0, height }, clip);
    world = el("g", {}, stage);
    const axis = el("g", {}, world);
    const linesGroup = el("g", {}, world);
    playhead = el("line", { class: "tl-playhead", y1: 0, y2: height }, world);

    const firstDay = new Date(data.start * 1000);
    firstDay.setHours(24, 0, 0, 0);
    let lastTickX = -Infinity;
    for (const day = firstDay; day.getTime() / 1000 <= data.end; day.setDate(day.getDate() + 1)) {
      const tickX = x(playbackAt(day.getTime() / 1000));
      if (tickX - lastTickX < 72) continue;
      lastTickX = tickX;
      const tick = el("g", { class: "tl-tick" }, axis);
      el("line", { x1: tickX, x2: tickX, y1: 16, y2: height }, tick);
      el("text", { x: tickX + 3, y: 12 }, tick).textContent =
        day.toLocaleDateString(undefined, { day: "numeric", month: "short" });
    }
    for (const s of segments) {
      const days = (s.t1 - s.t0) / 86400;
      const squeezed = s.p1 - s.p0 < (s.t1 - s.t0) / data.baseRate * 0.99;
      if (days < 1 || !squeezed) continue;
      el("text", { x: x((s.p0 + s.p1) / 2), y: 28, "text-anchor": "middle" }, el("g", { class: "tl-gap" }, axis))
        .textContent = `${Math.round(days)} d`;
    }

    lineNodes = data.lines.map((line) => {
      const group = el("g", { class: "tl-line" }, el("a", { href: pagePath(line.id) }, linesGroup));
      group.style.setProperty("--c", `var(--line-${line.type})`);
      el("title", {}, group).textContent = line.path.join(" › ");
      const lineY = y(line.lane);
      // Ahead of the playhead only the grey copy shows; the coloured copy is revealed as it passes.
      drawShapes(line, lineY, el("g", { class: "tl-ghost" }, group));
      const stops = drawShapes(line, lineY, el("g", { "clip-path": "url(#tl-clip)" }, group));
      // Station names sit outside the clip, so one reaching past the playhead is not cut off.
      const labelGroup = el("g", {}, group);
      const labels = line.stops.map((stop) => {
        const labelX = x(stop.p) + 3;
        const labelY = lineY - 7;
        const label = el("text", {
          class: "tl-label", x: labelX, y: labelY, transform: `rotate(-40 ${labelX} ${labelY})`,
        }, labelGroup);
        label.textContent = statusLabel(stop);
        return label;
      });
      const unset = () => line.stops.map(() => false);
      return { group, stops, labels, past: false, fresh: unset(), speaking: unset() };
    });

    slider.max = data.duration;
    passed = -1;                // the feed is rebuilt on the next frame
    live.hidden = !data.lines.length;
    empty.hidden = Boolean(data.lines.length);
  }

  // A line's track, stations and end mark; drawn once in grey and once in colour.
  function drawShapes(line, lineY, parent) {
    el("line", { class: "tl-track", x1: x(line.p0), x2: x(line.p1), y1: lineY, y2: lineY }, parent);
    const stops = line.stops.map((stop, index) => {
      const cx = x(stop.p);
      if (line.end === "delivered" && index === line.stops.length - 1) {
        const mark = el("circle", { class: "tl-stop tl-delivered", cx, cy: lineY, r: 6 }, parent);
        el("path", {
          class: "tl-check", d: `M${cx - 2.8} ${lineY + 0.2} L${cx - 0.8} ${lineY + 2.2} L${cx + 2.8} ${lineY - 1.8}`,
        }, parent);
        return mark;
      }
      const className = stop.kind === "status" ? "tl-stop tl-transition" : "tl-stop";
      return el("circle", { class: className, cx, cy: lineY, r: 3.5 }, parent);
    });
    if (line.end === "dropped") {
      el("line", { class: "tl-dropped", x1: x(line.p1), x2: x(line.p1), y1: lineY - 6, y2: lineY + 6 }, parent);
    }
    return stops;
  }

  // --- the minimap under the scrubber: every line at once, and the window the stage shows ---
  let windowRect = null;
  let miniScale = 0;
  function drawMinimap() {
    minimap.replaceChildren();
    const width = minimap.getBoundingClientRect().width;
    const miniHeight = 48;
    minimap.setAttribute("viewBox", `0 0 ${width} ${miniHeight}`);
    miniScale = data.duration > 0 ? width / data.duration : 0;
    const laneY = (lane) => 6 + (data.lanes > 1 ? lane / (data.lanes - 1) : 0.5) * (miniHeight - 12);
    for (const line of data.lines) {
      const x1 = line.p0 * miniScale;
      const node = el("line", {
        class: "tl-mini", x1, x2: Math.max(x1 + 1, line.p1 * miniScale), y1: laneY(line.lane), y2: laneY(line.lane),
      }, minimap);
      node.style.setProperty("--c", `var(--line-${line.type})`);
    }
    windowRect = el("rect", { class: "tl-window", y: 1, height: miniHeight - 2, rx: 3 }, minimap);
  }

  // --- the counters and the feed of the latest stations ---
  const inFlightCount = document.createElement("b");
  const deliveredCount = document.createElement("b");
  const droppedCount = document.createElement("b");
  counts.append(inFlightCount, " in flight · ", deliveredCount, " delivered · ", droppedCount, " dropped");

  function stationLabel(stop) {
    return stop.kind === "status" ? stop.status : stop.kind;
  }

  function statusLabel(stop) {
    return stop.kind === "archived" || stop.kind === "unarchived" ? stop.kind : stop.status;
  }

  function feedItem(entry) {
    const line = data.lines[entry.line];
    const stop = line.stops[entry.stop];
    const item = document.createElement("li");
    const time = document.createElement("time");
    time.dateTime = new Date(stop.at * 1000).toISOString();
    time.textContent = new Date(stop.at * 1000).toLocaleString(undefined, {
      day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
    });
    const dot = document.createElement("span");
    dot.className = "tl-dot";
    dot.style.setProperty("--c", `var(--line-${line.type})`);
    const status = document.createElement("span");
    status.className = "tl-status";
    status.textContent = stationLabel(stop);
    const link = document.createElement("a");
    link.href = pagePath(line.id);
    link.title = line.path.join(" › ");
    link.textContent = line.title;
    item.append(time, dot, status, link);
    return item;
  }

  function passedCount(p) {
    let low = 0;
    let high = data.feed.length;
    while (low < high) {
      const mid = (low + high) >> 1;
      if (data.feed[mid].p <= p) low = mid + 1; else high = mid;
    }
    return low;
  }

  // --- one frame: everything below is a function of the playhead alone, so scrubbing is free ---
  let p = 0;
  let stageWidth = 0;
  let passed = -1;

  function frame() {
    const headX = x(p);
    const camera = Math.max(0, headX - HEAD * stageWidth);
    world.setAttribute("transform", `translate(${-camera},0)`);
    clipRect.setAttribute("width", headX + X0);
    playhead.setAttribute("x1", headX);
    playhead.setAttribute("x2", headX);

    const now = new Date(timeAt(p) * 1000);
    clock.dateTime = now.toISOString();
    clock.textContent = now.toLocaleString(undefined, {
      weekday: "short", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
      hourCycle: "h23",
    });

    let inFlight = 0;
    let delivered = 0;
    let dropped = 0;
    data.lines.forEach((line, index) => {
      const node = lineNodes[index];
      const ended = line.end !== "open" && line.p1 <= p;
      if (line.p0 <= p) {
        if (!ended) inFlight++;
        else if (line.end === "delivered") delivered++;
        else dropped++;
      }
      const past = line.end !== "open" && line.p1 + SPEAK < p;
      if (past !== node.past) {
        node.past = past;
        node.group.classList.toggle("past", past);
      }
      // Only the latest station passed is announced, so a burst of transitions does not stack labels.
      const latest = line.stops.findLastIndex((stop) => stop.p <= p);
      line.stops.forEach((stop, number) => {
        const since = p - stop.p;
        const fresh = since >= 0 && since < FRESH;
        if (fresh !== node.fresh[number]) {
          node.fresh[number] = fresh;
          node.stops[number].classList.toggle("fresh", fresh);
        }
        const speaking = number === latest && since < SPEAK;
        if (speaking !== node.speaking[number]) {
          node.speaking[number] = speaking;
          node.labels[number].classList.toggle("speaking", speaking);
        }
      });
    });
    inFlightCount.textContent = inFlight;
    deliveredCount.textContent = delivered;
    droppedCount.textContent = dropped;

    if (windowRect) {
      windowRect.setAttribute("x", Math.max(0, (camera - X0) / PX) * miniScale);
      windowRect.setAttribute("width", stageWidth / PX * miniScale);
    }
    slider.value = p;

    const count = passedCount(p);
    if (count !== passed) {
      passed = count;
      feedList.replaceChildren(...data.feed.slice(Math.max(0, count - FEED_SIZE), count).reverse().map(feedItem));
    }
  }

  // --- playback ---
  let playing = false;
  let lastNow = null;
  let frameRequest = 0;

  function updateButton() {
    playButton.textContent = playing ? "❚❚ Pause" : p >= data.duration ? "↺ Replay" : "Play";
  }

  function tick(now) {
    if (lastNow !== null) p = Math.min(data.duration, p + Math.min(MAX_STEP, (now - lastNow) / 1000));
    lastNow = now;
    frame();
    if (p >= data.duration) {
      setPlaying(false);
      return;
    }
    frameRequest = requestAnimationFrame(tick);
  }

  function setPlaying(value) {
    cancelAnimationFrame(frameRequest);
    if (value && p >= data.duration) p = 0;
    playing = value;
    lastNow = null;
    updateButton();
    if (playing) frameRequest = requestAnimationFrame(tick);
  }

  function layout() {
    stageWidth = stage.getBoundingClientRect().width;
    drawMinimap();
    frame();
  }

  playButton.addEventListener("click", () => setPlaying(!playing));
  slider.addEventListener("input", () => {
    setPlaying(false);
    p = parseFloat(slider.value);
    frame();
    updateButton();
  });
  // Dragging the stage moves the playhead with the pointer, like dragging a map, and pauses the
  // replay - as dragging the scrubber does - so it stays where the viewer took it.
  const DRAG_THRESHOLD = 4;   // pixels a press must move before it counts as a drag
  let press = null;
  let swallowClick = false;
  stage.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    press = { pointerId: event.pointerId, x: event.clientX, p, dragging: false };
    swallowClick = false;
  });
  stage.addEventListener("pointermove", (event) => {
    if (!press || event.pointerId !== press.pointerId) return;
    const dx = event.clientX - press.x;
    if (!press.dragging) {
      if (Math.abs(dx) < DRAG_THRESHOLD) return;
      // Captured only once it is a drag, so a plain click still reaches the line's link.
      press.dragging = true;
      setPlaying(false);
      stage.setPointerCapture(event.pointerId);
      stage.classList.add("dragging");
    }
    p = Math.min(data.duration, Math.max(0, press.p - dx / PX));
    frame();
    updateButton();
  });
  function release(event) {
    if (!press || event.pointerId !== press.pointerId) return;
    swallowClick = press.dragging;
    press = null;
    stage.classList.remove("dragging");
    if (stage.hasPointerCapture(event.pointerId)) stage.releasePointerCapture(event.pointerId);
  }
  stage.addEventListener("pointerup", release);
  stage.addEventListener("pointercancel", release);
  stage.addEventListener("click", (event) => {
    if (!swallowClick) return;
    swallowClick = false;
    event.preventDefault();
    event.stopPropagation();
  }, true);

  document.addEventListener("keydown", (event) => {
    if (event.key !== " " || event.target.closest("button, a, textarea, select, input:not([type=range])")) return;
    event.preventDefault();
    setPlaying(!playing);
  });
  window.addEventListener("resize", layout);

  // A live payload: redraw it, and play on to its new end if the viewer was resting at the old one.
  // A paused viewer is looking at something, so they are left where they are. A viewer who prefers
  // reduced motion is taken to the new end at rest. A payload can also end earlier than the last one,
  // and a viewer past its end is brought back to it.
  function show(timeline) {
    const resting = !playing && !press?.dragging && p >= data.duration;   // the Replay state
    data = timeline;
    p = Math.min(p, data.duration);
    draw();
    layout();
    if (!resting || p >= data.duration) return updateButton();
    if (reducedMotion) {
      p = data.duration;
      frame();
      updateButton();
    } else {
      setPlaying(true);
    }
  }

  // --- live updates: the timeline rebuilt whenever its log changes ---
  let digest = dataNode.dataset.digest;   // the items the drawing was built from; a reconnect hands back the latest

  function connect() {
    const socket = new WebSocket(`/ws/events/${workspaceId}?digest=${digest}`);

    socket.onmessage = function(event) {
      const message = JSON.parse(event.data);
      if (!message.timeline) return;    // the heartbeat
      digest = message.digest;
      show(message.timeline);
    };

    socket.onclose = function(e) {
      console.log("Events socket is closed. Reconnect will be attempted in 1 second.", e.reason);
      setTimeout(function() {
        connect();
      }, 1000);
    };

    socket.onerror = function(err) {
      socket.close();
    };
  }

  // The page opens at rest at the end of the history, in the Replay state; Replay plays it from the start.
  draw();
  p = data.duration;
  layout();
  updateButton();
  connect();
}

// The page shell keeps <body> hidden until its theme script has run, and the stage can only be
// measured once it is shown, so start after the whole document has been parsed.
if (!window.__timeline_loaded) {
  window.__timeline_loaded = true;
  document.addEventListener("DOMContentLoaded", main);
}
