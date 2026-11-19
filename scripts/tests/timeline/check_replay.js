// The replay plays from the start to the end of the payload, and leaves the counters, the feed and
// the clock where the payload says the history ends.
//
//     node check_replay.js <payload.json> <_timeline.js>
"use strict";
const assert = require("assert");
const { loadTimeline, assertClose } = require("./stub_dom");

const [payloadPath, scriptPath] = process.argv.slice(2);
const timeline = loadTimeline(payloadPath, scriptPath);
const { data, ids } = timeline;

timeline.runTimers();                                        // the autoplay
assert.strictEqual(ids["tl-play"].textContent, "❚❚ Pause", "the replay starts playing on its own");
let frames = 0;
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

console.log(`ok - played ${frames} frames over ${data.duration}s; ${inFlight} in flight, ${delivered} delivered, ${dropped} dropped`);
