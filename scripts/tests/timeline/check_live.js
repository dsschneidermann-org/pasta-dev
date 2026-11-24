// Live updates: the page opens its events socket with the digest of the items it was drawn from,
// ignores heartbeats, and redraws each live payload. A viewer resting at the end in the Replay state is
// played on to the new end - or taken there at rest if they prefer reduced motion - while a viewer
// paused in the history, or dragging, is left where they are. A payload that ends earlier brings a
// viewer past its end back to it. A stalled frame skips no playback. It reconnects with the digest of
// the last payload it drew, and an empty page brings up the map on its first payload.
//
//     node check_live.js <payload.json> <_timeline.js>
"use strict";
const assert = require("assert");
const fs = require("fs");
const { loadTimeline, assertClose } = require("./stub_dom");

const [payloadPath, scriptPath] = process.argv.slice(2);
const data = JSON.parse(fs.readFileSync(payloadPath, "utf8"));
const PX = 120;                                              // the renderer's pixels per playback second

// The replay as the server would rebuild it after one more write: a simple change created a second
// of playback after the old end, in a lane of its own.
function grown(payload) {
  const p0 = payload.duration + 1;
  const end = payload.end + 3 * 3600;
  const duration = p0 + 0.5;
  return {
    ...payload,
    end,
    duration,
    segments: [...payload.segments, [payload.end, end, payload.duration, duration]],
    lanes: payload.lanes + 1,
    lines: [...payload.lines, {
      id: "simple-change:live", type: "simple-change", title: "A live change", path: ["Features", "A live change"],
      lane: payload.lanes,
      p0, p1: duration, end: "open", stops: [{ p: p0, at: payload.end + 2 * 3600, kind: "status", status: "draft" }],
    }],
    feed: [...payload.feed, { p: p0, line: payload.lines.length, stop: 0 }],
  };
}
const extended = grown(data);
const live = { timeline: extended, digest: "grown" };

function playToEnd(timeline) {
  let frames = 0;
  while (timeline.pendingFrames() && frames < 100000) {
    timeline.runFrames(1);
    frames++;
  }
}

// From rest at the end: a heartbeat changes nothing; a live payload is drawn and played into.
let timeline = loadTimeline(payloadPath, scriptPath, { digest: "d40" });
let { ids } = timeline;
assert.deepStrictEqual(timeline.sockets.map((socket) => socket.url), ["/ws/events/ws:check?digest=d40"],
  "the socket hands back the digest the page was drawn from");
timeline.push({ heartbeat: 1 });
assert.strictEqual(timeline.pendingFrames(), 0, "a heartbeat starts nothing");
assert.strictEqual(timeline.onStage("tl-ghost").length, data.lines.length, "a heartbeat redraws nothing");

timeline.push(live);
assert.strictEqual(timeline.onStage("tl-ghost").length, extended.lines.length, "the new line is drawn");
assert.strictEqual(ids["tl-scrub"].max, extended.duration, "the scrubber reaches the new end");
assert.strictEqual(ids["tl-play"].textContent, "❚❚ Pause", "a live update at rest starts playback");
timeline.runFrames(1);
assertClose(timeline.playhead(), data.duration, "playback carries on from the old end, not from the start");
playToEnd(timeline);
assertClose(timeline.playhead(), extended.duration, "and stops at the new end");
assert.strictEqual(ids["tl-play"].textContent, "↺ Replay", "back in the Replay state");

timeline.closeSocket();
timeline.runTimers();                                        // the 1 s reconnect
assert.strictEqual(timeline.sockets.at(-1).url, "/ws/events/ws:check?digest=grown",
  "a reconnect hands back the digest of the last payload drawn");

// Paused mid-history: the viewer is looking at something, so a live update redraws and leaves them there.
timeline = loadTimeline(payloadPath, scriptPath);
({ ids } = timeline);
timeline.scrubTo(10);
timeline.push(live);
assert.strictEqual(timeline.onStage("tl-ghost").length, extended.lines.length, "redrawn mid-history");
assert.strictEqual(timeline.pendingFrames(), 0, "a paused timeline stays paused");
assertClose(timeline.playhead(), 10, "where the viewer paused it");
assert.strictEqual(ids["tl-play"].textContent, "Play");

// A stalled frame after a live redraw - the browser painting the rebuilt map - skips no playback.
timeline = loadTimeline(payloadPath, scriptPath);
timeline.push(live);
timeline.runFrames(1);                                       // the first frame only starts the clock
timeline.stall(500);
timeline.runFrames(1);
const advanced = timeline.playhead() - data.duration;
assert.ok(advanced <= 0.1 + 1e-9, `a stalled frame advances at most 0.1 s, not ${advanced}`);
assert.ok(timeline.playhead() < extended.duration, "so playback still has its way to go");
playToEnd(timeline);
assertClose(timeline.playhead(), extended.duration, "and runs on to the new end");

// While a drag is held, a live update redraws but leaves the playhead to the pointer.
timeline = loadTimeline(payloadPath, scriptPath);
({ ids } = timeline);
timeline.scrubTo(10);
timeline.pointer("pointerdown", 500);
timeline.pointer("pointermove", 500 - PX);
timeline.push(live);
assert.strictEqual(timeline.onStage("tl-ghost").length, extended.lines.length, "redrawn mid-drag");
assert.strictEqual(timeline.pendingFrames(), 0, "but not played");
assert.strictEqual(ids["tl-play"].textContent, "Play");
timeline.pointer("pointermove", 500 - 2 * PX);
assertClose(timeline.playhead(), 12, "the drag carries on over the new map");
timeline.pointer("pointerup", 500 - 2 * PX);

// Reduced motion: a live update jumps to the new end at rest.
timeline = loadTimeline(payloadPath, scriptPath, { reducedMotion: true });
({ ids } = timeline);
assert.strictEqual(ids["tl-play"].textContent, "↺ Replay", "reduced motion opens at rest too");
timeline.push(live);
assertClose(timeline.playhead(), extended.duration, "reduced motion jumps to the new end");
assert.strictEqual(timeline.pendingFrames(), 0, "without playing");
assert.strictEqual(ids["tl-play"].textContent, "↺ Replay");

// Archiving the page behind the latest stations ends the replay earlier: a viewer resting past the
// new end is brought back to it, still at rest.
timeline = loadTimeline(payloadPath, scriptPath, { payloadText: JSON.stringify(extended) });
({ ids } = timeline);
timeline.push({ timeline: data, digest: "shorter" });
assertClose(timeline.playhead(), data.duration, "a shorter replay brings the playhead back to its end");
assert.strictEqual(timeline.pendingFrames(), 0, "without playing");
assert.strictEqual(ids["tl-play"].textContent, "↺ Replay");

// An empty page brings the map up on its first payload and plays it from the start.
const empty = { start: data.start, end: data.start, duration: 0, baseRate: data.baseRate,
  segments: [], lanes: 0, lines: [], feed: [] };
timeline = loadTimeline(payloadPath, scriptPath, { payloadText: JSON.stringify(empty), digest: "empty" });
({ ids } = timeline);
assert.strictEqual(timeline.sockets[0].url, "/ws/events/ws:check?digest=empty");
assert.deepStrictEqual([ids["tl-live"].hidden, ids["tl-empty"].hidden], [true, false], "an empty page says so");
timeline.push({ timeline: data, digest: "first" });
assert.deepStrictEqual([ids["tl-live"].hidden, ids["tl-empty"].hidden], [false, true], "the first payload brings up the map");
assert.strictEqual(timeline.onStage("tl-ghost").length, data.lines.length);
timeline.runFrames(1);
assertClose(timeline.playhead(), 0, "and plays it from the start");
playToEnd(timeline);
assertClose(timeline.playhead(), data.duration);

console.log(`ok - handed back its digest, ignored heartbeats, grew ${data.lines.length} lines to `
  + `${extended.lines.length} playing on from Replay, held still paused and mid-drag, jumped with reduced `
  + "motion, came back to a shorter replay's end, capped a stalled frame, reconnected with the latest "
  + "digest, and brought up an empty page");
