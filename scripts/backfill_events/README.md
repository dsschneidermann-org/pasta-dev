# Event log backfill (archived)

The one-off code that wrote pasta's own history into `ws_mrteq0c5-238cf6.events.jsonl` before the
store began logging events itself. It has done its job and is kept here for reference only: the
files are stored as they were written, with their original imports, and are not set up to run.

| File | Was |
|---|---|
| `backfill.py` | `src/backfill.py` - dated each page's creation and latest status from the backups, its pull request, or the first commit's feature list |
| `backfill_timeline.py` | `scripts/backfill_timeline.py` - gathered those inputs and rewrote the log |
| `id_time.py` | `id_time` from `src/ids.py` - read a page's creation instant out of its id |
| `pull_requests.json` | `scripts/timeline_backfill/pull_requests.json` - the pasta-dev pull requests, as read from GitHub |
| `test_backfill.py`, `test_ids.py` | their tests, from `tests/` |
