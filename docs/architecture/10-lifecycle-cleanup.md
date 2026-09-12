# Lifecycle & cleanup

## Summary

**Kind:** module

The recurring workspace sweep: hourly it classifies every page as findable, hidden, or unfiled,
stamps a uniform expiry on the orphans, and deletes — backup first — the subtrees whose expiry has
passed.

## Purpose

Pages accumulate. Archiving one hides it and everything beneath it; a reparent can leave a page
filed nowhere. Without a sweep those pages stay in the workspace file forever, invisible but
loaded on every read. This module exists to give them a bounded, *reversible-for-a-while*
lifetime: an orphan is stamped with a deadline several days out, and until that deadline passes,
making the page findable again simply clears the stamp.

It exists as a separate module — rather than as store methods — because the interesting part is
pure. `reachability`, `classify`, and `delete_subtree` take a `Workspace` and return decisions or
mutate an in-memory copy; they unit-test with no filesystem. The store owns the transaction.

The dependency direction is deliberate and stated in the source: **the dependency runs
`store → cleanup`. This module never imports store.** `run_once` takes `store` loosely typed
(`Any`) precisely to keep that import out.

Delete this component and workspaces grow without bound, and archiving becomes a permanent
soft-delete with no eventual reclamation.

## Usage

**Pure classification** — callable on any `Workspace`:

- `reachability(workspace)` → `Reachability(findable, hidden, unfiled)`
- `classify(workspace, now)` → `Sweep(stamp, clear, prune)`
- `delete_subtree(workspace, root_id)` → the ids removed, mutating the workspace in place
- `expiry_for(now)`, `seconds_until_next_run(now)`

**The pass** — `run_once(store, now=None)` iterates `store.list_workspaces()` and calls
`store.cleanup_workspace(workspace_id, now)` for each, returning a `SweepReport` per workspace.
Blocking; the scheduler runs it in a thread.

**The timer** — `start_scheduler(store)` and `await stop_scheduler()`. `start_scheduler` is
**idempotent**, which matters because two different lifespans call it:
`server.app_lifespan` under plain ASGI hosting, and `hmr_server.reloader_lifespan` under the dev
server (only the latter runs there). `scheduler_enabled()` returns `False` when `PASTA_CLEANUP=0`;
any other value or unset enables it.

The store side is `Store.cleanup_workspace`, which takes the transaction lock, runs `classify`,
writes a backup if anything is to be pruned, applies the stamps and deletions, and saves.

## Data model

Three frozen result types, all transient:

- **`Reachability`** — `findable` (reached from `root_page_ids` via `child_ids` with nothing
  archived on the path), `hidden` (reached, but some page on the path — possibly itself — is
  archived), `unfiled` (never reached by the walk at all).
- **`Sweep`** — `stamp` (page id → expiry to write; only pages carrying none), `clear` (ids
  findable again — drop the stamp), `prune` (maximal subtree-root ids whose expiry is at or before
  now).
- **`SweepReport`** — `workspace_id`, `stamped`, `cleared`, `pruned` (every id removed, subtrees
  expanded), `backup` (path written, or `None` when nothing was pruned), `error` (set means
  **nothing was written**).

The only persisted field this component touches is `Page.expires_at` — a UTC ISO-8601 instant,
written and cleared **only** by this sweep, never by a page-type command. Backups are written by
`Store.write_backup` under `backups/<workspace>/<timestamp>.json`.

Module-level mutable state: `_task`, the single live sweep task, module-level so
`start_scheduler` can be idempotent across the two lifespans.

The tuning constants: `CLEANUP_MINUTE = 5` (the sweep fires at :05 past every hour),
`GRACE_DAYS = 5`, `EXPIRY_HOUR_UTC = 12`, `MAX_SLEEP_SECONDS = 30`,
`SWEEP_PERIOD_SECONDS = 3600`.

## Details

**Expiry is uniform, not per-page.** `expiry_for` returns 12:00 UTC on the date `GRACE_DAYS`
after now, so every page stamped on the same day shares one deadline — which means real grace
ranges from 4 days 12 hours to 5 days 12 hours. That is a deliberate trade: a predictable,
inspectable deadline over a precise per-page one.

**A stamped page is never re-stamped.** Stated plainly in `classify`'s docstring as the reason:
if it were, the deadline would move every hour and nothing would ever expire. Conversely, a page
that has become findable again gets its stamp cleared.

**`prune` names only maximal subtree roots:**

```python
expired = {page_id for page_id in targets
           if (stamped := workspace.pages[page_id].expires_at) is not None
           and datetime.fromisoformat(stamped) <= now}
covered = {child for page_id in expired for child in _descendants(workspace, page_id) - {page_id}}
return Sweep(stamp=stamp, clear=clear, prune=sorted(expired - covered))
```

So a nested expired page is removed once, with its parent, rather than being named separately.

**The walk uses `child_ids` and ignores `parent_id`** — explicitly "so a stale pointer cannot cause
a deletion". It tracks a `shadowed` flag down the tree, which is how "hidden" becomes a property
of the *path*: an archived page's descendants keep `archived=False` yet cannot be found. Both the
walk and `_descendants` are cycle-guarded via a `seen` set, and a dangling child id is skipped
(the validator reports it) rather than treated as an error.

**`delete_subtree` deletes the whole subtree and unlinks the root**, because deleting the flagged
page alone would leave its children filed nowhere. It also strips links from surviving pages to
removed ones, so no dangling link survives the prune.

**One bad workspace cannot end the pass.** Each workspace is swept in its own `try`/`except` in
`run_once`, producing a `SweepReport` with `error` set; the timer survives. Only a workspace with
something to report is logged, through `logging.getLogger("uvicorn.error")` so sweep results land
beside uvicorn's own output.

**The loop wakes every 30 seconds rather than sleeping the full hour** to the tick, and sweeps
when the tick has just gone by. `seconds_until_next_run` is documented as never returning 0, so
the loop cannot spin.

**The module is hot-reloadable.** It registers an `on_dispose` hook that cancels the running task
before the reloader replaces it, and `hmr_server.cleanup_reload_effect` restarts it on the new
code — the pairing that keeps exactly one sweep task alive across a reload.

On the graph: `cleanup.py` holds a 23-symbol single-file community, and its 40 symbols are the
sixth-largest file in `src/`. The store calls into it 5 times; nothing calls back.

## Code references

| File | Symbol | Kind |
|---|---|---|
| `src/cleanup.py` | `reachability` | function |
| `src/cleanup.py` | `classify` | function |
| `src/cleanup.py` | `delete_subtree` | function |
| `src/cleanup.py` | `run_once` | function |
| `src/cleanup.py` | `expiry_for` | function |
| `src/cleanup.py` | `seconds_until_next_run` | function |
| `src/cleanup.py` | `start_scheduler` | function |
| `src/cleanup.py` | `stop_scheduler` | function |
| `src/cleanup.py` | `scheduler_enabled` | function |
| `src/cleanup.py` | `_stop_for_reload` | function |
| `src/cleanup.py` | `Reachability` | class |
| `src/cleanup.py` | `Sweep` | class |
| `src/cleanup.py` | `SweepReport` | class |
| `src/store.py` | `cleanup_workspace` | function |

## Dependencies

| Target | Role | Note |
|---|---|---|
| [Domain model](04-domain-model.md) | depends-on | reads `Workspace` / `Page`; sole writer of `expires_at` |
| `reactivity.hmr.hooks` | depends-on | `on_dispose` cancels the live task before a hot reload replaces the module |
| [Workspace store](02-workspace-store.md) | exposes | the store calls `classify` and owns the backup, the write, and the transaction; this module holds **no** store import |
| [MCP & HTTP transport](01-mcp-http-transport.md) | exposes | `app_lifespan` starts/stops the scheduler under plain ASGI hosting |
| [Dev server & HMR](09-dev-server-hmr.md) | exposes | `reloader_lifespan` owns the scheduler under the dev server and restarts it per reload |

## Invariants

1. **This module never imports the store.** `run_once` takes `store: Any`. Violated, the
   `store → cleanup` dependency becomes a cycle, and the pure classification can no longer be
   tested without the storage shell.
2. **Classification is pure; only the store writes.** `reachability` and `classify` return
   decisions. Violated, a deletion escapes the store's transaction lock and can race a concurrent
   authoring write.
3. **The reachability walk follows `child_ids` only.** `parent_id` is ignored. Violated, a stale
   parent pointer can classify a findable page as unfiled and eventually delete live content.
4. **A page already carrying an expiry is never re-stamped.** Guarded by
   `expires_at is None` in `classify`. Violated, every sweep pushes the deadline an hour out and
   nothing ever expires — the sweep runs forever with no effect.
5. **A page that is findable again has its stamp cleared.** The `clear` arm. Violated, a page
   recovered from archive is still deleted on its old deadline.
6. **Nothing is pruned without a backup written first.** `Store.cleanup_workspace` writes the
   backup before applying deletions; `SweepReport.backup` is `None` only when nothing was pruned.
   Violated, an incorrect classification becomes unrecoverable data loss.
7. **`prune` contains only maximal subtree roots.** Descendants of an expired page are subtracted.
   Violated, the same page is deleted twice in one pass, and the report's counts misstate what
   happened.
8. **A subtree is deleted whole, with the root unlinked and inbound links stripped.** Violated,
   surviving children are filed nowhere — recreating the orphan condition the sweep exists to
   resolve — and links dangle.
9. **One failing workspace does not end the pass or kill the timer.** Per-workspace
   `try`/`except`. Violated, a single corrupt file stops cleanup for every workspace, silently.
10. **Exactly one sweep task runs per process.** `_task` is module-level, `start_scheduler` is
    idempotent, and `on_dispose` cancels before a reload. Violated, two tasks sweep the same
    workspace concurrently and contend for its transaction lock.

## Sync

Reconciled against commit `a35b133`.
