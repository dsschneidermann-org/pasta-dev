// The map's marks: every line in a grey copy and a clipped coloured copy, a checkmark in both copies
// of each delivered end, status changes filled, links free of queries, a status label for every
// station, and the label of a line's latest station - whatever its kind, a page's creation included -
// announced as the playhead passes it, while every station passed is highlighted.
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

// A line's hover title and its feed link's title name its whole page-hierarchy path; the link reads its title.
const hoverTitles = created.filter((element) => element.tag === "title").map((element) => element.textContent);
assert.deepStrictEqual(hoverTitles, data.lines.map((line) => line.path.join(" › ")), "a line's hover title is its path");
const feedLinks = links.filter((link) => link.attrs.href === undefined);
assert.ok(feedLinks.length > 0, "the feed lists the latest stations");
feedLinks.forEach((link) => {
  const line = data.lines.find((candidate) => link.href === `/ws:check/page/${candidate.id}`);
  assert.strictEqual(link.title, line.path.join(" › "), "a feed link's title is its line's path");
  assert.strictEqual(link.textContent, line.title, "a feed link reads its line's title");
});

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
      const expected = number === latest && p - stop.p < SPEAK;
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

// Every kind of station behaves the same as the playhead passes it: highlighted, and announced as
// its line's latest - a creation with the status it was created in, an (un)archiving by its kind.
const KINDS = [["created", "draft", "draft"], ["status", "open", "open"], ["archived", "open", "archived"],
  ["unarchived", "open", "unarchived"]];
const kindStops = KINDS.map(([kind, status], index) => ({ p: 1 + 3 * index, at: data.start + 3 * index, kind, status }));
const kindLine = { id: "bug-report:kinds", type: "bug-report", title: "Label check", path: ["Bug Reports", "Label check"],
  lane: 0, p0: 1, p1: 10, end: "open", stops: kindStops };
const kindPayload = { start: data.start, end: data.start + 9, duration: 10, baseRate: data.baseRate,
  segments: [[data.start, data.start + 9, 1, 10]], lanes: 1, lines: [kindLine],
  feed: kindStops.map((stop, index) => ({ p: stop.p, line: 0, stop: index })) };
const kinds = loadTimeline(payloadPath, scriptPath, { payloadText: JSON.stringify(kindPayload) });
const kindLabels = kinds.classed("tl-label");
const kindMarks = kinds.classed("tl-stop").slice(KINDS.length);   // the clipped copy, drawn after the grey one
KINDS.forEach(([kind, , text], index) => {
  kinds.scrubTo(kindStops[index].p + 0.1);
  assert.strictEqual(kindLabels[index].textContent, text, `a ${kind} station is labelled ${text}`);
  assert.deepStrictEqual(kindLabels.map((label) => label.classList.set.has("speaking")),
    KINDS.map((_kind, other) => other === index), `passing a ${kind} station announces it alone`);
  assert.ok(kindMarks[index].classList.set.has("fresh"), `passing a ${kind} station highlights it`);
});

console.log(`ok - ${data.lines.length} lines in two copies, ${delivered} checked ends, ${transitions} filled `
  + `status changes, ${labels.length} labels, up to ${mostSpeaking} announced at once, `
  + (close ? `close transitions on ${close.line.id} scrubbed` : "no close transitions to scrub")
  + `, and a creation, status change, archiving and unarchiving each highlighted and announced alike`);
