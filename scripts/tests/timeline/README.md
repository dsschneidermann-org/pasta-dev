# Timeline renderer checks

Checks for `src/templates/_timeline.js`, the script that draws and plays the workspace timeline
(`/ws:<id>/timeline`). They run the real renderer under Node against a stub DOM and a real replay,
so its drawing and playback can be verified without a browser.

They sit beside the Python tests rather than inside them: the timeline's layout - the playback
clock, lines, lanes and feed order - is tested in `tests/test_timeline.py`, and the served page in
`tests/test_web.py`. These cover what only the browser script does.

## What you need

- `uv`, as for the rest of the project.
- Node.js on `PATH` (checked with Node 24).
- A data dir holding a workspace whose event log (`ws_<id>.events.jsonl`) has timeline events.

## Running them

From the repository root:

```bash
uv run python scripts/tests/timeline/run_checks.py
```

This builds the timeline payload for pasta's workspace from `./.pasta-data` - exactly what the
timeline view would serve now - runs each check against it, prints `PASS` or `FAIL` per check
(with the check's output, and the assertion that broke on a failure), and exits 1 if any check
failed.

| Option | Default | Use |
|---|---|---|
| `--data-dir DIR` | `$PASTA_DATA_DIR`, else `.pasta-data` | Where the workspace and its event log live. Must exist. |
| `--workspace WS_ID` | `ws:mrteq0c5-238cf6` | Which workspace to replay. |
| `--payload FILE` | built from the data dir | Check against a saved payload instead. |
| `--script FILE` | `src/templates/_timeline.js` | Check another copy of the renderer, e.g. an older version. |

To see a check catch a regression, run it against an older renderer - any commit from before the
behaviour you want to see caught:

```bash
git show <older commit>:src/templates/_timeline.js > /tmp/old_timeline.js
uv run python scripts/tests/timeline/run_checks.py --script /tmp/old_timeline.js
# e.g. a renderer that kept playing while dragged fails check_drag.js and the runner exits 1
```

A single check can also be run directly, given a payload file:

```bash
node scripts/tests/timeline/check_drag.js payload.json src/templates/_timeline.js
```

## What each check covers

| Check | Covers |
|---|---|
| `check_replay.js` | Autoplay starts, the replay runs to its end and offers Replay, the final counters (in flight / delivered / dropped) match the payload's line ends, the feed shows the latest six stations, and the clock reads the payload's start and end when scrubbed there. |
| `check_marks.js` | Every line is drawn as a grey copy and a clipped coloured copy, both copies of each delivered end carry a checkmark, status changes are filled while creations and (un)archivings stay hollow, each line links to its page with no query, every station has a label naming its status, and during playback and scrubbing a line announces only its latest transition, for 1.5 playback seconds, while a page's creation never is. |
| `check_drag.js` | Dragging the chart moves time like a map (left is forward, 120 px per playback second), stops at both ends, counts as a drag only past 4 px, and swallows exactly the click that ends it; a plain press still clicks through; a drag on the chart or the minimap scrubber pauses the player, and Play resumes from there. |

`stub_dom.js` holds the stub DOM and the loader the checks share.

## What they do not cover

The stub DOM records what the renderer asks for; it does not lay out, paint or hit-test. Styling,
theme colours, overlapping labels and how a real browser routes pointer events are not checked here -
look at the page in a browser for those.
