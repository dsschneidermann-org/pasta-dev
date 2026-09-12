# Workspace docs vs. `docs/architecture/`: differences, gaps, and which approach is better

Two sets of architecture documentation now describe pasta:

- **Workspace set** — 10 `architecture` pages in the pasta workspace `ws:mrteq0c5-238cf6`, all in
  status `current`, hand-authored over the project's life.
- **Repo set** — the 10 pages in this directory, derived from the GitNexus graph in one session and
  reconciled against `a35b133`.

This file compares them. Every claim of drift below was confirmed by opening the code at
`a35b133`; claims I could not confirm are marked as such.

---

## 1. The decompositions differ, and they cut in different directions

The workspace set is organised by **capability** — what the system does for a user. The repo set is
organised by **code structure** — what the modules are. Neither is a refinement of the other; they
cross.

| Workspace page | `kind` | Nearest repo page(s) |
|---|---|---|
| Pasta Project Overview | service | `README.md` + spans 01, 02, 04 |
| Page types & FSM implementation | subsystem | 05 Page-type system + 06 FSM evaluation |
| Authoring & mutation | component | 03 Mutation engine + 02 Workspace store |
| Reads & navigation | component | 07 Rendering + parts of 01, 02 |
| Search & introspection | component | 08 Introspection + `Store.search` in 02 |
| Self-direction | component | `next_actions` in 02 + `field_setter_edges` in 03 |
| Archiving | component | **no dedicated page** — scattered across 02, 04 |
| Web UI, HMR & live reload | subsystem | 09 Dev server & HMR + templates in 01 |
| Page-type documentation generation | subsystem | 08 Introspection & doc generation |
| Scheduled workspace cleanup | component | 10 Lifecycle & cleanup |

Three structural consequences:

1. **Capability pages split one module across several pages.** `store.py` is documented in
   Authoring & mutation, Reads & navigation, Self-direction, Archiving, and Scheduled cleanup — five
   pages, none of which describes `Store` as a thing with 56 methods, two lock tiers, and one
   transaction shape.
2. **Module pages split one capability across several pages.** Archiving's rules — orthogonal to
   FSM status, cascades to pinned children, starts a deletion clock, hides whole subtrees — are
   real and user-visible, and the repo set never assembles them in one place.
3. **Only the capability set names the workflow semantics.** "Self-direction" is not a module. It
   is the behaviour that makes pasta what it is, and it emerges from `next_actions` +
   `field_setter_edges` + the FSM + `agency`. A module decomposition structurally cannot have a
   page for it.

---

## 2. Verified drift in the workspace set

Five pages carry claims that the code at `a35b133` contradicts. Each was checked by reading the
named source.

| # | Page | Claim | Reality at `a35b133` |
|---|---|---|---|
| D1 | Pasta Project Overview | "The swap is a temp-file write followed by `Path.copy` + unlink (`src/store.py::_write_file`, changed for Windows), **NOT** `os.replace`, so the destination is briefly incomplete while the copy runs." | `_write_file` writes a pid+thread-unique temp file and calls `os.replace` (twice — the second after a 0.1s sleep, retrying a transient Windows permission error). No `.copy(` or `unlink` appears anywhere in `store.py`. |
| D2 | Reads & navigation | Same, restated as an invariant: "the swap itself is `Path.copy`, not an atomic `os.replace`." | As D1. |
| D3 | Authoring & mutation | `mutatePage(workspaceId, pageId, command, args?)` documented in Usage, with its response shape in Data model. | No such tool. `server.py` defines `mutatePageBatch` only; single mutation is a one-command batch. |
| D4 | Reads & navigation, Archiving | `tree(workspaceId, includeArchived?)`; "pass `tree(includeArchived=true)` to see them". | The tool is `tree(workspaceId)`. Its own docstring says archived subtrees "are **always** hidden - there is no flag to include them". |
| D5 | Authoring & mutation, Self-direction | "`PageType.__post_init__` calls `validate_pagetype_setter_descriptions(self)` and then `validate_pagetype_field_setters(self)`" / "enforced at declaration time by … `validate_pagetype_field_setters`, which `PageType.__post_init__` calls". | `__post_init__` runs `_resolve_block_vocabularies`, `_status_transitions`, `_build_machines` — and no validators. Both functions are called only from `validate_page_type` in `core/validation.py`. |
| D6 | Scheduled workspace cleanup | "the whole per-workspace pass runs inside one `Store._lock_for(workspace_id)`" (Details diagram + an invariant + a dependency note). | No `_lock_for` exists. It is `_transaction_lock_for` (writers) and `_rw_lock_for` (per-file), a split the page predates. |
| D7 | Scheduled workspace cleanup | "`PASTA_CLEANUP=1` force-enables it on any transport including `--stdio`. Unset means on for the HTTP server and off for `--stdio`." | `scheduler_enabled()` is `os.environ.get("PASTA_CLEANUP", "1") != "0"` — no transport branch. The stdio behaviour is incidental: `start_scheduler` is called only from `server.app_lifespan` and `hmr_server.reloader_lifespan`, and `mcp.run(transport="stdio")` runs neither, so `PASTA_CLEANUP=1` cannot force-enable it under stdio. |
| D8 | Authoring & mutation | Code reference: `src/pagetypes/core/args.py; symbol: set_title_cmd`. | `set_title_cmd` is in `core/commands.py`. (Its own Invariants section names the right module, so the reference row is the stale part.) |
| D9 | Search & introspection | "the SAME `BlockKindSpec.body_args()` the validator reads" | `body_args` is a dataclass **field** on `BlockKindSpec`, read as `block.body_args`. Minor: the capability is intact, the call syntax is stale. |
| D10 | Pasta Project Overview | "each MCP tool is a thin sync function (resolve inputs -> run a store transaction -> return a JSON-able dict)" | All 24 `@mcp.tool` functions are `async def`; none is sync. |
| D11 | Authoring & mutation | "because the single (stdio or HTTP) server runs sync tools on FastMCP worker threads, that lock fully serializes conflicting read-modify-write cycles" | Follows from D10: the threading-model premise does not hold. The serialization itself is intact, but it rests on the per-workspace transaction lock rather than on tools running on worker threads. |

D10 and D11 were found while migrating the invariants (see
[INVARIANT-MIGRATION-PLAN.md](INVARIANT-MIGRATION-PLAN.md)), not in the original comparison.

**Two of these are internal contradictions, not just staleness** — the workspace set disagrees with
itself, and in both cases the newer page is right:

- **D1/D2 vs. Authoring & mutation**, which states "The atomic `os.replace` prevents torn files
  regardless of locking." Three pages, two mechanisms, one codebase.
- **D5 vs. Page types & FSM implementation** (synced at `a35b133`), which correctly says
  `__post_init__` "no longer validates - constructing a malformed page type does not raise".

A third near-contradiction: Search & introspection says block-vocabulary "resolution raises at
import instead of leaving one unresolved", while Page types & FSM says resolution "is best-effort
and never raises" and the defect "surfaces only when a validator runs". The code is best-effort, so
the older page is the wrong one.

### The sync mechanism has been silently defeated

The `sync.commit` field exists so "a later reader can diff from it to find exactly what has
drifted". For half the set, that is no longer possible:

| Page | Sync commit | Ancestor of HEAD? |
|---|---|---|
| Page types & FSM implementation | `a35b133` | **yes — is HEAD** |
| Page-type documentation generation | `a35b133` | **yes — is HEAD** |
| Search & introspection | `7689a5c` | yes (3 behind) |
| Pasta Project Overview | `4302713` | **no** |
| Authoring & mutation | `a6a3196` | **no** |
| Self-direction | `a6a3196` | **no** |
| Reads & navigation | `a9f8689` | **no** |
| Archiving | `d335abe` | **no** |
| Scheduled workspace cleanup | `d335abe` | **no** |
| Web UI, HMR & live reload | `1489cf5` | **no** |

`git merge-base --is-ancestor` fails for all six. The objects still exist locally but are
unreachable from the branch — the history was re-cut (`463cf4f "Initial version cut"`, 8 commits
total), orphaning them. So `git diff <sync>..HEAD` cannot be run for those pages, and would not
survive a `gc` or a fresh clone. **The drift is not merely unrecorded; the tool for finding it is
broken for 6 of 10 pages.** Every confirmed defect above sits on one of those six.

---

## 3. Where the workspace set is better

This is the larger list, and it is not close.

**1. Rationale, which cannot be recovered from code.** The repo set explains *what is* and *what
breaks*; the workspace set also explains *why this and not that*. Scheduled cleanup records that
FastAPI `BackgroundTasks` runs once after a response, that FastMCP's background tasks implement
SEP-1686/SEP-2663 and are triggered by a tool call rather than a clock, and that APScheduler and
Celery were rejected as new dependencies — so a plain asyncio task owned by a lifespan is the
mechanism. No amount of graph analysis recovers that paragraph.

**2. Rejected alternatives, recorded as rejected.** Authoring & mutation explains why
`mutatePageBatch` arguments stay literal JSON with no positional back-reference to an earlier
command's created id: it "would force every consumer to learn a reserved key before it could write
a step, would silently repoint the moment a batch was reordered, and would invent four new ways to
be wrong". That is a fence with a sign on it.

**3. Decision history — what each rule replaced.** Reads & navigation records that the declared
element-heading rule replaced a heuristic promoting the first declared field when its value was
"non-empty, newline-free and at most 80 characters", under which "siblings of one list rendered
differently and a value sitting near the bound flipped shape when a word was added". Authoring &
mutation records that the guidance-placement rule replaced one where two pages "disagreed and the
response emitted both readings at once". The repo set has no memory of any of this.

**4. Cross-page reasoning the module view cannot see.** Page types & FSM explains that reparenting
the pinned plan children under `feature-spec` would make the brief's `ship` guard "PASS VACUOUSLY -
a guard that quietly stops guarding", and that sibling ordering is therefore expressed as a status
on the parent, with the invariant that "the spec's `required_statuses` minus the plans' is exactly
`{spec}`". It even records that this is *not* pinned by a test, because production page types are
off-limits in tests, "so this declaration and this page are the record". That is documentation doing
work no test and no graph can do.

**5. Depth on the domain semantics.** The blocks/inline-run grammar (plain/marked/linked/code/
page-ref runs, `INLINE_RUNS` / `INLINE_RUN_LISTS` / `INLINE_RUN_GRID`), the `id:` search prefix and
why a bare colon query is not id resolution, `is_field_setter`'s exact membership and why an
element-scoped add-block is excluded from `do`, the three instruction channels and why all three
ride inside `next` — the repo set is thin or silent on all of it.

**6. It is authored by the people making the decisions,** so it captures intent at the moment of
change. The repo set can only ever describe the result.

---

## 4. Where the repo set is better

**1. Currency, uniformly.** One reconciliation pass, one commit, every page stamped `a35b133`, and
every one of its 147 code references confirmed to resolve to a real definition in the named file by
a script. The workspace set has 2 pages at HEAD, 6 whose sync commit is unreachable, and at least
two wrong reference rows (D8, D9).

**2. A module map, which the workspace set does not contain.** Nothing in the workspace set tells a
reader what `rwlock.py`, `ids.py`, `serialize.py`, `model.py`, or `errors.py` *is* as a unit, or
states the file-level import DAG, or records that there are zero import cycles. A newcomer asked to
find where something lives has no index.

**3. The dependency graph is actually populated.** The `architecture` type provides
`dependencies` (target/role/note) and **8 of 10 workspace pages leave it `*None.*`** — only
Scheduled cleanup and Page-type doc generation use it. So the workspace's page graph is mostly
unlinked despite the field existing for exactly this. Every repo page carries its edges.

**4. Measured facts.** Caller counts (`_guard_tool` 23, `load_workspace` 21, `get_page_type` 16),
the heaviest file pair (`server.py → store.py`, 35 `CALLS`), community structure and cohesion,
per-file symbol counts. These make "thin transport layer" checkable rather than asserted, and they
tell you where an edit is risky.

**5. Invariants that are actually invariants.** The page type asks for "a checkable assertion about
state or behaviour rather than an aspiration", and **Details is empty on 7 of 10 workspace pages**
while their Invariants sections run to 200–700 words each, absorbing rationale, history, and
narrative. Page types & FSM has a single "invariant" of roughly 700 words covering test fixtures,
registry swapping, parametrization counts, and a `conftest.py` ordering note. That is excellent
content in the wrong field — and it means the invariants cannot be read as a checklist, which is
what makes an invariant useful when you are about to change something. The workspace set violates
its own type's authoring guidance here; the repo set does not.

---

## 5. Gaps in the repo set, specifically

Worth fixing regardless of which approach wins:

1. **No Archiving page.** The rules exist in the code and are scattered across repo pages 02 and 04.
2. **The typed reference graph (`link`/`unlink`) is under-documented** — listed as store methods,
   but the directed-edge model, the validation rules (both endpoints exist, source non-archived,
   target may be archived, no self-link, no duplicate `(to, role)`), and `addLink` as a universal
   page command are not explained.
3. **The blocks/inline-run grammar is named but not taught.**
4. **No rationale or rejected-alternatives content anywhere.**
5. **The two-tier test strategy is missing** — why the pure/shell split is what the test tiers key
   off.
6. **Web UI specifics are missing** — the `Page | Model` doc overlay, `_view_toggle.js`, and the
   rule that all structured-render styling is scoped under `.pasta-page` and takes every colour from
   a water.css custom property (a literal colour there reads correctly in one theme only).

---

## 6. Which approach is better

**For this project, the capability decomposition is the better primary structure, and the repo set's
discipline is what it needs bolted on.**

The reasoning is about what each structure can *hold*, and what is recoverable if lost:

- The module structure is **cheaply recoverable**. I rebuilt it from the graph in a single session
  with no prior knowledge of the codebase. Import edges, caller counts, and communities are all
  derivable on demand, and `impact` answers the blast-radius question better than any prose page.
- The rationale is **not recoverable at all**. Why `ChildStateGuard` sees only direct children and
  what breaks if you reparent to work around it; why batch arguments stay literal JSON; why the
  element heading rule is declared rather than inferred. Lose those pages and the knowledge is
  gone — it exists nowhere else, and some of it is explicitly not pinned by tests.
- **The hard part of pasta cuts across modules.** Self-direction, the authoring loop, and the
  archiving/expiry lifecycle each span the store, the command engine, the FSM, and the page-type
  declarations. A module page can describe its slice; only a capability page can state the rule.

So: keep the ten capability pages as the primary documentation. Their content is better and their
boundaries match how the system is used, reasoned about, and changed — features land as
capabilities, not as modules.

What to take from the repo set:

1. ~~**Fix the confirmed defects**~~ — **done.** All eleven (D1–D11) are corrected in the
   workspace pages, each with a "Corrections at `a35b133`" paragraph in Details recording what the
   code actually does, so the correction is visible rather than silent.
2. ~~**Re-stamp every page's sync commit to a reachable one.**~~ — **done.** All ten now read
   `a35b133`. Still worth automating: consider asserting sync-commit reachability in
   `scripts/validate_workspace.py`, since nothing prevents the next history re-cut from orphaning
   them again.
3. **Verify code references mechanically.** A script over `codeReferences` resolving each
   file+symbol would have caught D8 and D9 for free. This is the single highest-value addition —
   the type already stores the pointers in a structured form. *(Still open; D8 was fixed by hand.)*
4. ~~**Move rationale out of Invariants into Details.**~~ — **done.** See
   [INVARIANT-MIGRATION-PLAN.md](INVARIANT-MIGRATION-PLAN.md) for the method and the
   before/after numbers: 127 invariants / 13,766 words of invariant prose became 117 / 5,441, and
   the Details sections went from 13 blocks to 84.
5. **Populate `dependencies`** on the eight pages that leave it empty. *(Still open.)*
6. **Add the missing module map** as one page — not ten. A single "Code layout" architecture page
   naming each module, the layering, and the zero-cycles property covers the newcomer-orientation
   gap without duplicating the capability pages. `docs/architecture/README.md` is a usable draft of
   it. *(Still open.)*

Keep this repo directory as a dated, verified snapshot and as the source for items 3 and 6. It is
the better *map*; the workspace set is the better *documentation*. Do not maintain both as primary —
two sets drifting against each other is exactly the failure the workspace set already demonstrates
internally, three times over.

---

*Written against `a35b133`. Workspace read at `ws:mrteq0c5-238cf6`, all 10 architecture pages in
status `current`.*
