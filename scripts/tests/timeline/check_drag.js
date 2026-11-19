// Dragging: the chart moves with the pointer like a map, clamped to the replay; a press only counts
// as a drag past 4 px and then swallows its closing click; and any drag - on the chart or on the
// minimap scrubber - pauses the player until Play is pressed.
//
//     node check_drag.js <payload.json> <_timeline.js>
"use strict";
const assert = require("assert");
const { loadTimeline, assertClose } = require("./stub_dom");

const [payloadPath, scriptPath] = process.argv.slice(2);
const timeline = loadTimeline(payloadPath, scriptPath);
const { data, ids } = timeline;
const stage = ids["tl-stage"];
const button = ids["tl-play"];
const PX = 120;                                              // the renderer's pixels per playback second

// Moving through time, while paused.
timeline.scrubTo(10);
timeline.pointer("pointerdown", 500);
assert.strictEqual(stage.captured ?? null, null, "a bare press leaves its click to the line under it");
timeline.pointer("pointermove", 500 - 2 * PX);
assertClose(timeline.playhead(), 12, "dragging left goes forward");
assert.strictEqual(stage.captured, 7, "a drag captures the pointer");
timeline.pointer("pointermove", 500 + 2 * PX);
assertClose(timeline.playhead(), 8, "dragging right goes back");
timeline.pointer("pointermove", 500 + 1e6);
assertClose(timeline.playhead(), 0, "a drag stops at the start");
timeline.pointer("pointermove", 500 - 1e6);
assertClose(timeline.playhead(), data.duration, "a drag stops at the end");
timeline.pointer("pointermove", 500);
timeline.pointer("pointerup", 500);
assertClose(timeline.playhead(), 10, "the playhead stays where the drag let go");
assert.strictEqual(timeline.clickSwallowed(), true, "the click closing a drag is swallowed");
assert.strictEqual(timeline.clickSwallowed(), false, "only that one click is swallowed");

// A press under the threshold is a click, not a drag: it does not pause.
button.listeners.click();
assert.strictEqual(button.textContent, "❚❚ Pause");
timeline.runFrames(3);
timeline.pointer("pointerdown", 500);
timeline.pointer("pointermove", 503);
timeline.pointer("pointerup", 503);
assert.strictEqual(button.textContent, "❚❚ Pause", "a press under 4 px does not pause");
assert.strictEqual(timeline.clickSwallowed(), false, "a press under 4 px still clicks through");
const beforeFrames = timeline.playhead();
timeline.runFrames(3);
assert.ok(timeline.playhead() > beforeFrames, "still playing after a plain press");

// A chart drag pauses, and the replay stays where it was taken.
timeline.pointer("pointerdown", 500);
const pressedAt = timeline.playhead();
timeline.pointer("pointermove", 500 - PX);
assert.strictEqual(button.textContent, "Play", "a chart drag pauses the player");
assertClose(timeline.playhead(), pressedAt + 1, "the drag moved the playhead");
timeline.runFrames(30);
assertClose(timeline.playhead(), pressedAt + 1, "paused while pressed");
timeline.pointer("pointerup", 500 - PX);
timeline.clickSwallowed();
timeline.runFrames(30);
assertClose(timeline.playhead(), pressedAt + 1, "still paused after release");

// A scrubber drag pauses too.
button.listeners.click();
timeline.runFrames(3);
timeline.scrubTo(40);
assert.strictEqual(button.textContent, "Play", "a scrubber drag pauses the player");
timeline.runFrames(30);
assertClose(timeline.playhead(), 40, "paused where the scrubber put it");

// Play carries on from there.
button.listeners.click();
timeline.runFrames(10);
assert.ok(timeline.playhead() > 40, "Play resumes from where the drag left the playhead");

console.log("ok - drags move, clamp and swallow one click; chart and scrubber drags pause; Play resumes");
