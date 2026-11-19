// The map's marks: every line in a grey copy and a clipped coloured copy, a checkmark in both copies
// of each delivered end, status changes filled, links free of queries, a status label for every
// station, and the label of a line's latest transition - never of a page's creation - announced as
// the playhead passes it.
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

// A status change is a filled station; a creation or an (un)archiving stays hollow.
const deliveredEnd = (line, number) => line.end === "delivered" && number === line.stops.length - 1;
const marks = data.lines.flatMap((line) => line.stops.filter((_stop, number) => !deliveredEnd(line, number)));
const transitions = marks.filter((stop) => stop.kind === "status").length;
const filled = timeline.classed("tl-transition");
assert.strictEqual(filled.length, 2 * transitions, "both copies of every status change are filled");
assert.ok(filled.every((mark) => mark.attrs.class.split(" ").includes("tl-stop")), "a filled station is still a station");
const hollow = timeline.classed("tl-stop").filter((mark) => !/\btl-(transition|delivered)\b/.test(mark.attrs.class));
assert.strictEqual(hollow.length, 2 * (marks.length - transitions), "creations and (un)archivings stay hollow");

// Every line links to its page, and no link - a line's or a feed item's - carries a query.
const links = created.filter((element) => element.tag === "a");
const lineLinks = links.filter((link) => link.attrs.href !== undefined).map((link) => link.attrs.href);
assert.deepStrictEqual(lineLinks, data.lines.map((line) => `/ws:check/page/${line.id}`), "a line links to its page");
links.forEach((link) => assert.ok(!(link.attrs.href ?? link.href).includes("?"), "a link carries no query"));

// Labels are created line by line, station by station, so the nth label belongs to the nth station.
const labels = timeline.classed("tl-label");
assert.strictEqual(labels.length, stations.length, "one label per station");
labels.forEach((label, index) => {
  const { stop } = stations[index];
  const expected = stop.kind === "archived" || stop.kind === "unarchived" ? stop.kind : stop.status;
  assert.strictEqual(label.textContent, expected, "a label names its station's status");
});

// A line announces only its latest passed station, for SPEAK playback seconds after passing it.
const SPEAK = 1.5;
const latestPassed = (line, p) => line.stops.reduce((latest, stop, number) => (stop.p <= p ? number : latest), -1);
const speakingNow = () => labels.map((label) => label.classList.set.has("speaking"));
function assertSpeaking(p) {
  let index = 0;
  const speaking = speakingNow();
  for (const line of data.lines) {
    const latest = latestPassed(line, p);
    line.stops.forEach((stop, number) => {
      const expected = number > 0 && number === latest && p - stop.p < SPEAK;
      assert.strictEqual(speaking[index++], expected,
        `at ${p}, station ${number} of ${line.id} ${expected ? "speaks" : "is silent"}`);
    });
  }
}

timeline.ids["tl-play"].listeners.click();                   // the page opens at its end: Replay
let mostSpeaking = 0;
let frames = 0;
while (timeline.pendingFrames() && frames < 100000) {
  timeline.runFrames(1);
  frames++;
  labels.forEach((label, index) => {
    if (!label.classList.set.has("speaking")) return;
    assert.notStrictEqual(stations[index].number, 0, "a page's creation is never announced");
  });
  assertSpeaking(timeline.playhead());
  mostSpeaking = Math.max(mostSpeaking, speakingNow().filter(Boolean).length);
}
assert.ok(mostSpeaking > 0, "transitions are announced during playback");

// Two transitions of one line closer than SPEAK: past the second only it speaks, and scrubbing back
// between them brings the first one's label back.
let close = null;
let offset = 0;
for (const line of data.lines) {
  for (let number = 2; number < line.stops.length && !close; number++) {
    const [before, stop, after] = [line.stops[number - 1], line.stops[number], line.stops[number + 1]];
    if (stop.p > before.p && stop.p - before.p < SPEAK && !(after && after.p === stop.p)) {
      close = { first: offset + number - 1, second: offset + number, line, number };
    }
  }
  offset += line.stops.length;
}
if (close) {
  const { line, number } = close;
  const between = (line.stops[number - 1].p + line.stops[number].p) / 2;
  timeline.scrubTo(line.stops[number].p);
  assertSpeaking(timeline.playhead());
  assert.ok(speakingNow()[close.second] && !speakingNow()[close.first], "past both, only the latest speaks");
  timeline.scrubTo(between);
  assertSpeaking(timeline.playhead());
  assert.ok(speakingNow()[close.first] && !speakingNow()[close.second], "scrubbed back, the earlier speaks again");
}

console.log(`ok - ${data.lines.length} lines in two copies, ${delivered} checked ends, ${transitions} filled `
  + `status changes, ${labels.length} labels, up to ${mostSpeaking} announced at once, `
  + (close ? `close transitions on ${close.line.id} scrubbed` : "no close transitions to scrub"));
