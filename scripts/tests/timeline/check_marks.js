// The map's marks: every line in a grey copy and a clipped coloured copy, a checkmark in both copies
// of each delivered end, a status label for every station, and the labels of transitions - never of
// a page's creation - announced as the playhead passes them.
//
//     node check_marks.js <payload.json> <_timeline.js>
"use strict";
const assert = require("assert");
const { loadTimeline } = require("./stub_dom");

const [payloadPath, scriptPath] = process.argv.slice(2);
const timeline = loadTimeline(payloadPath, scriptPath);
const { data, created } = timeline;

const delivered = data.lines.filter((line) => line.end === "delivered").length;
const stations = data.lines.flatMap((line) => line.stops.map((stop, number) => ({ stop, number })));
assert.strictEqual(timeline.classed("tl-ghost").length, data.lines.length, "one grey copy per line");
assert.strictEqual(created.filter((element) => element.attrs["clip-path"] === "url(#tl-clip)").length,
  data.lines.length, "one clipped coloured copy per line");
assert.strictEqual(timeline.classed("tl-check").length, 2 * delivered, "a check in both copies of every delivered end");

// Labels are created line by line, station by station, so the nth label belongs to the nth station.
const labels = timeline.classed("tl-label");
assert.strictEqual(labels.length, stations.length, "one label per station");
labels.forEach((label, index) => {
  const { stop } = stations[index];
  const expected = stop.kind === "archived" || stop.kind === "unarchived" ? stop.kind : stop.status;
  assert.strictEqual(label.textContent, expected, "a label names its station's status");
});

timeline.runTimers();
let mostSpeaking = 0;
let frames = 0;
while (timeline.pendingFrames() && frames < 100000) {
  timeline.runFrames(1);
  frames++;
  labels.forEach((label, index) => {
    if (!label.classList.set.has("speaking")) return;
    assert.notStrictEqual(stations[index].number, 0, "a page's creation is never announced");
  });
  mostSpeaking = Math.max(mostSpeaking, labels.filter((label) => label.classList.set.has("speaking")).length);
}
assert.ok(mostSpeaking > 0, "transitions are announced during playback");

console.log(`ok - ${data.lines.length} lines in two copies, ${delivered} checked ends, ${labels.length} labels, `
  + `up to ${mostSpeaking} announced at once`);
