// Draws and replays the activity timeline: the last day of a page's (and every page beneath it) or a
// workspace's activity, the workspace timeline zoomed in. Every layout decision arrives in the payload;
// this script only draws each payload it is given - the page's, then every live one its activity
// socket streams - and moves the playhead. It runs in one closure, so it adds no global names.
(function () {
  if (window.__activity_loaded) return;
  window.__activity_loaded = true;

  function main() {
    const dataNode = document.getElementById("activity-data");
    if (!dataNode) return;
    let data = JSON.parse(dataNode.textContent);
    const workspaceId = dataNode.dataset.workspace;
    const pageId = dataNode.dataset.page;

    const PX = 120;          // pixels per playback second
    const LANE_H = 18;
    const AXIS_H = 34;
    const X0 = 16;           // left margin, so the first mark is not cut in half
    const HEAD = 0.7;        // how far across the stage the playhead rides
    const SPEAK = 1.5;       // playback seconds a mark's label stays up after it is passed
    const MAX_STEP = 0.1;    // most playback seconds one frame advances, so a stalled frame never skips the replay ahead
    const FEED_SIZE = 6;
    const TICK_GAP = 72;     // fewest pixels between two minute ticks
    const SVG = "http://www.w3.org/2000/svg";

    const stage = document.getElementById("ac-stage");
    const minimap = document.getElementById("ac-minimap");
    const slider = document.getElementById("ac-scrub");
    const playButton = document.getElementById("ac-play");
    const clock = document.getElementById("ac-clock");
    const feedList = document.getElementById("ac-feed");
    const live = document.getElementById("ac-live");
    const empty = document.getElementById("ac-empty");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let segments = [];
    const x = (p) => X0 + p * PX;
    const y = (lane) => AXIS_H + lane * LANE_H + LANE_H / 2;

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

    // --- the labels a mark carries ---
    function size(bytes) {
      if (bytes < 1024) return `${bytes} B`;
      if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
      return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    }

    function markLabel(mark) {
      if (mark.kind === "call") return `${mark.tool} ${size(mark.bytes)}`;
      if (mark.kind === "link" || mark.kind === "ref") return `→ ${mark.title}`;
      if (mark.kind === "archived" || mark.kind === "unarchived") return mark.kind;
      return mark.status;
    }

    function feedText(mark) {
      switch (mark.kind) {
        case "created": return `created · ${mark.status}`;
        case "status": return mark.status;
        case "archived": case "unarchived": return mark.kind;
        case "call": return `${mark.tool} · ${size(mark.bytes)} ${mark.write ? "sent" : "returned"}`;
        case "link": return `link → ${mark.title}`;
        default: return `ref → ${mark.title}`;
      }
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
      const clip = el("clipPath", { id: "ac-clip" }, el("defs", {}, stage));
      clipRect = el("rect", { x: -X0, y: 0, width: 0, height }, clip);
      world = el("g", {}, stage);
      const axis = el("g", {}, world);
      const linesGroup = el("g", {}, world);
      playhead = el("line", { class: "ac-playhead", y1: 0, y2: height }, world);
      drawAxis(axis, height);

      lineNodes = data.lines.map((line) => {
        const group = el("g", { class: "ac-line" }, el("a", { href: line.href }, linesGroup));
        group.style.setProperty("--c", `var(--line-${line.colour})`);
        el("title", {}, group).textContent = line.path.join(" › ");
        const lineY = y(line.lane);
        // Ahead of the playhead only the grey copy shows; the coloured copy is revealed as it passes.
        drawShapes(line, lineY, el("g", { class: "ac-ghost" }, group));
        drawShapes(line, lineY, el("g", { "clip-path": "url(#ac-clip)" }, group));
        // Labels sit outside the clip, so one reaching past the playhead is not cut off.
        const labelGroup = el("g", {}, group);
        const labels = line.marks.map((mark) => {
          const labelX = x(mark.p) + 3;
          const labelY = lineY - 7;
          const label = el("text", {
            class: "ac-label", x: labelX, y: labelY, transform: `rotate(-40 ${labelX} ${labelY})`,
          }, labelGroup);
          label.textContent = markLabel(mark);
          return label;
        });
        return { labels, speaking: line.marks.map(() => false) };
      });

      slider.max = data.duration;
      passed = -1;                // the feed is rebuilt on the next frame
      live.hidden = !data.lines.length;
      empty.hidden = Boolean(data.lines.length);
    }

    // A tick at each whole minute far enough from the last, and the length of each squeezed gap.
    function drawAxis(axis, height) {
      const minute = new Date(data.start * 1000);
      minute.setSeconds(60, 0);
      let lastTickX = -Infinity;
      for (; minute.getTime() / 1000 <= data.end; minute.setMinutes(minute.getMinutes() + 1)) {
        const tickX = x(playbackAt(minute.getTime() / 1000));
        if (tickX - lastTickX < TICK_GAP) continue;
        lastTickX = tickX;
        const tick = el("g", { class: "ac-tick" }, axis);
        el("line", { x1: tickX, x2: tickX, y1: 16, y2: height }, tick);
        el("text", { x: tickX + 3, y: 12 }, tick).textContent =
          minute.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
      }
      for (const s of segments) {
        const seconds = s.t1 - s.t0;
        const squeezed = s.p1 - s.p0 < seconds / data.baseRate * 0.99;
        if (seconds < 60 || !squeezed) continue;
        el("text", { x: x((s.p0 + s.p1) / 2), y: 28, "text-anchor": "middle" }, el("g", { class: "ac-gap" }, axis))
          .textContent = seconds < 3600 ? `${Math.round(seconds / 60)} min` : `${Math.round(seconds / 3600)} h`;
      }
    }

    // A line's track and marks; drawn once in grey and once in colour.
    function drawShapes(line, lineY, parent) {
      el("line", { class: "ac-track", x1: x(line.p0), x2: x(line.p1), y1: lineY, y2: lineY }, parent);
      for (const mark of line.marks) {
        const cx = x(mark.p);
        if (mark.kind === "call") {
          const half = mark.write ? 6 : 4;
          el("line", {
            class: mark.write ? "ac-call ac-write" : "ac-call", x1: cx, x2: cx, y1: lineY - half, y2: lineY + half,
          }, parent);
        } else if (mark.kind === "link" || mark.kind === "ref") {
          el("path", {
            class: mark.kind === "link" ? "ac-link" : "ac-ref",
            d: `M${cx} ${lineY - 3.5} L${cx + 3.5} ${lineY} L${cx} ${lineY + 3.5} L${cx - 3.5} ${lineY} Z`,
          }, parent);
        } else {
          el("circle", { class: mark.kind === "status" ? "ac-stop ac-transition" : "ac-stop", cx, cy: lineY, r: 3.5 }, parent);
        }
      }
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
          class: "ac-mini", x1, x2: Math.max(x1 + 1, line.p1 * miniScale), y1: laneY(line.lane), y2: laneY(line.lane),
        }, minimap);
        node.style.setProperty("--c", `var(--line-${line.colour})`);
      }
      windowRect = el("rect", { class: "ac-window", y: 1, height: miniHeight - 2, rx: 3 }, minimap);
    }

    // --- the feed of the latest marks passed ---
    function feedItem(entry) {
      const line = data.lines[entry.line];
      const mark = line.marks[entry.mark];
      const item = document.createElement("li");
      const time = document.createElement("time");
      time.dateTime = new Date(mark.at * 1000).toISOString();
      time.textContent = new Date(mark.at * 1000).toLocaleTimeString(undefined, {
        hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
      });
      const dot = document.createElement("span");
      dot.className = "ac-dot";
      dot.style.setProperty("--c", `var(--line-${line.colour})`);
      const what = document.createElement("span");
      what.className = "ac-what";
      what.textContent = feedText(mark);
      if (mark.kind === "link") what.title = mark.role;
      const link = document.createElement("a");
      link.href = line.href;
      link.title = line.path.join(" › ");
      link.textContent = line.title;
      item.append(time, dot, what, link);
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
        weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit",
        hourCycle: "h23",
      });

      // A line announces only its latest mark passed, and never a page's creation, so a burst of
      // calls does not stack its labels.
      data.lines.forEach((line, index) => {
        const node = lineNodes[index];
        const latest = line.marks.findLastIndex((mark) => mark.p <= p);
        line.marks.forEach((mark, number) => {
          const speaking = number === latest && mark.kind !== "created" && p - mark.p < SPEAK;
          if (speaking !== node.speaking[number]) {
            node.speaking[number] = speaking;
            node.labels[number].classList.toggle("speaking", speaking);
          }
        });
      });

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

    window.addEventListener("resize", layout);

    // A live payload keeps the viewer at the same wall time, since a window that slid moves every
    // mark, and plays on to the new end only from rest at the old one - the Replay state. A paused
    // viewer is looking at something, so they are left where they are; one who prefers reduced motion
    // is taken to the new end at rest.
    function show(timeline) {
      const resting = !playing && !press?.dragging && p >= data.duration;
      const at = timeAt(p);              // under the old payload's clock
      data = timeline;
      draw();
      p = Math.min(playbackAt(at), data.duration);
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

    // --- live activity: each recorded call, with the timeline rebuilt to include it ---
    function connect() {
      const query = pageId ? `?page=${encodeURIComponent(pageId)}` : "";
      const socket = new WebSocket(`/ws/activity/${workspaceId}${query}`);

      socket.onmessage = function(event) {
        const message = JSON.parse(event.data);
        if (message.timeline) show(message.timeline);      // anything else is the heartbeat
      };

      socket.onclose = function(e) {
        console.log("Activity socket is closed. Reconnect will be attempted in 1 second.", e.reason);
        setTimeout(function() {
          connect();
        }, 1000);
      };

      socket.onerror = function(err) {
        socket.close();
      };
    }

    // The page opens at rest at the end of the last day, in the Replay state.
    draw();
    p = data.duration;
    layout();
    updateButton();
    connect();
  }

  // The page shell keeps <body> hidden until its theme script has run, and the stage can only be
  // measured once it is shown, so start after the whole document has been parsed.
  document.addEventListener("DOMContentLoaded", main);
})();
