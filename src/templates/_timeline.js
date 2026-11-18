// Draws and replays the timeline payload (src/timeline.py). Every layout decision - lanes, playback
// positions, the playback clock, the order stations are narrated in - arrives in the payload; this
// script only draws it once and moves the playhead.
function main() {
  const dataNode = document.getElementById("timeline-data");
  if (!dataNode) return;
  const data = JSON.parse(dataNode.textContent);
  const workspaceId = dataNode.dataset.workspace;

  const PX = 120;          // pixels per playback second
  const LANE_H = 18;
  const AXIS_H = 34;
  const X0 = 16;           // left margin, so the first station is not cut in half
  const HEAD = 0.7;        // how far across the stage the playhead rides
  const FRESH = 0.6;       // playback seconds a station stays highlighted after the playhead passes
  const FEED_SIZE = 6;
  const SVG = "http://www.w3.org/2000/svg";

  const stage = document.getElementById("tl-stage");
  const minimap = document.getElementById("tl-minimap");
  const slider = document.getElementById("tl-scrub");
  const playButton = document.getElementById("tl-play");
  const clock = document.getElementById("tl-clock");
  const rateLabel = document.getElementById("tl-rate");
  const counts = document.getElementById("tl-counts");
  const feedList = document.getElementById("tl-feed");

  const segments = data.segments.map(([t0, t1, p0, p1]) => ({ t0, t1, p0, p1 }));
  const height = AXIS_H + data.lanes * LANE_H + LANE_H / 2;
  const x = (p) => X0 + p * PX;
  const y = (lane) => AXIS_H + lane * LANE_H + LANE_H / 2;
  const pagePath = (pageId) => `/${workspaceId}/page/${pageId}?archived=true`;

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

  function daysPerSecond(p) {
    if (!segments.length) return data.baseRate / 86400;
    const s = segmentAt(p, "p0");
    return (s.t1 - s.t0) / (s.p1 - s.p0) / 86400;
  }

  function rateText(days) {
    if (Math.abs(days - 0.25) < 0.01) return "¼ day per second";
    if (days < 1) return `${days.toFixed(2)} day per second`;
    return `${days < 10 ? days.toFixed(1) : Math.round(days)} days per second »`;
  }

  // --- the stage, drawn once and then only clipped and panned ---
  stage.setAttribute("height", height);
  const clip = el("clipPath", { id: "tl-clip" }, el("defs", {}, stage));
  const clipRect = el("rect", { x: -X0, y: 0, width: 0, height }, clip);
  const world = el("g", {}, stage);
  const axis = el("g", {}, world);
  const linesGroup = el("g", { "clip-path": "url(#tl-clip)" }, world);
  const playhead = el("line", { class: "tl-playhead", y1: 0, y2: height }, world);

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

  const lineNodes = data.lines.map((line) => {
    const group = el("g", { class: "tl-line" }, el("a", { href: pagePath(line.id) }, linesGroup));
    group.style.setProperty("--c", `var(--line-${line.type})`);
    el("title", {}, group).textContent = line.title;
    const lineY = y(line.lane);
    el("line", { class: "tl-track", x1: x(line.p0), x2: x(line.p1), y1: lineY, y2: lineY }, group);
    const stops = line.stops.map((stop, index) => {
      const delivers = line.end === "delivered" && index === line.stops.length - 1;
      return el("circle", {
        class: delivers ? "tl-stop tl-delivered" : "tl-stop", cx: x(stop.p), cy: lineY, r: delivers ? 5 : 3.5,
      }, group);
    });
    if (line.end === "dropped") {
      el("line", { class: "tl-dropped", x1: x(line.p1), x2: x(line.p1), y1: lineY - 6, y2: lineY + 6 }, group);
    }
    return { group, stops, past: false, fresh: line.stops.map(() => false) };
  });

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

  function feedItem(entry) {
    const line = data.lines[entry.line];
    const stop = line.stops[entry.stop];
    const item = document.createElement("li");
    const time = document.createElement("time");
    time.dateTime = new Date(stop.at * 1000).toISOString();
    time.textContent = new Date(stop.at * 1000).toLocaleString(undefined, {
      day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
    });
    const dot = document.createElement("span");
    dot.className = "tl-dot";
    dot.style.setProperty("--c", `var(--line-${line.type})`);
    const status = document.createElement("span");
    status.className = "tl-status";
    status.textContent = stationLabel(stop);
    const link = document.createElement("a");
    link.href = pagePath(line.id);
    link.title = line.title;
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
    });
    rateLabel.textContent = rateText(daysPerSecond(p));

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
      const past = line.end !== "open" && line.p1 + FRESH < p;
      if (past !== node.past) {
        node.past = past;
        node.group.classList.toggle("past", past);
      }
      line.stops.forEach((stop, number) => {
        const fresh = stop.p <= p && p - stop.p < FRESH;
        if (fresh !== node.fresh[number]) {
          node.fresh[number] = fresh;
          node.stops[number].classList.toggle("fresh", fresh);
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
    playButton.textContent = playing ? "❚❚ Pause" : p >= data.duration ? "↺ Replay" : "▶ Play";
  }

  function tick(now) {
    if (lastNow !== null) p = Math.min(data.duration, p + (now - lastNow) / 1000);
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
    p = parseFloat(slider.value);
    lastNow = null;
    frame();
    updateButton();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== " " || event.target.closest("button, a, textarea, select, input:not([type=range])")) return;
    event.preventDefault();
    setPlaying(!playing);
  });
  window.addEventListener("resize", layout);

  layout();
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    p = data.duration;      // show the whole map at rest; the scrubber still replays it
    frame();
    updateButton();
  } else {
    setTimeout(() => setPlaying(true), 600);
  }
}

// The page shell keeps <body> hidden until its theme script has run, and the stage can only be
// measured once it is shown, so start after the whole document has been parsed.
if (!window.__timeline_loaded) {
  window.__timeline_loaded = true;
  document.addEventListener("DOMContentLoaded", main);
}
