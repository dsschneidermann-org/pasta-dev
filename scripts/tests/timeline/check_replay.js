// The page opens at rest at the end of the history, in the Replay state; Replay plays it from the
// start to the end of the payload, and leaves the counters, the feed and the clock where the
// payload says the history ends.
//
//     node check_replay.js <payload.json> <_timeline.js>
"use strict";
const assert = require("assert");
const { loadTimeline, assertClose } = require("./stub_dom");

const [payloadPath, scriptPath] = process.argv.slice(2);
const timeline = loadTimeline(payloadPath, scriptPath);
const { data, ids } = timeline;

assert.strictEqual(ids["tl-play"].textContent, "↺ Replay", "the page opens in the Replay state");
assertClose(timeline.playhead(), data.duration, "standing at the end of the history");
assert.strictEqual(timeline.pendingFrames() + timeline.pendingTimers(), 0, "nothing plays on its own");

ids["tl-play"].listeners.click();                            // Replay
assert.strictEqual(ids["tl-play"].textContent, "❚❚ Pause", "Replay starts playing");
timeline.runFrames(1);
assertClose(timeline.playhead(), 0, "Replay plays from the start");
let frames = 1;
while (timeline.pendingFrames() && frames < 100000) {
  timeline.runFrames(1);
  frames++;
}
assert.strictEqual(ids["tl-play"].textContent, "↺ Replay", "the replay stops at its end");
assertClose(timeline.playhead(), data.duration, "the playhead ends at the payload's duration");

const ending = (end) => data.lines.filter((line) => line.end === end).length;
const [inFlight, delivered, dropped] = ids["tl-counts"].children
  .filter((child) => typeof child !== "string")
  .map((child) => Number(child.textContent));
assert.deepStrictEqual([inFlight, delivered, dropped], [ending("open"), ending("delivered"), ending("dropped")],
  "the final counters match the payload's line ends");
assert.strictEqual(ids["tl-feed"].children.length, Math.min(6, data.feed.length), "the feed shows the latest six");

timeline.scrubTo(0);
assert.strictEqual(ids["tl-clock"].dateTime, new Date(data.start * 1000).toISOString(), "the clock starts at the start");
timeline.scrubTo(data.duration);
assert.strictEqual(ids["tl-clock"].dateTime, new Date(data.end * 1000).toISOString(), "the clock ends at the end");

console.log(`ok - opened at rest in Replay; played ${frames} frames over ${data.duration}s; `
  + `${inFlight} in flight, ${delivered} delivered, ${dropped} dropped`);
