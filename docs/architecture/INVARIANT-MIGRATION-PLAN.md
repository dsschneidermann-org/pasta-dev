# Plan: move rationale out of Invariants into Details

Acts on recommendation #4 of [COMPARISON.md](COMPARISON.md): the ten `architecture` pages in
`ws:mrteq0c5-238cf6` carry their rationale, mechanism walk-throughs and decision history inside
`invariants`, while `details` sits almost empty. The `architecture` page type asks an invariant to
be "one property that must always hold … written as a checkable assertion about state or behaviour
rather than an aspiration, and paired with what breaks when it is violated" — so the content is
excellent and filed in the wrong field.

**This is a migration, not a rewrite.** The author's prose moves verbatim; only connective tissue
and the sharpened assertion lines are new.

## Measured starting state

| Page | Invariants | Words in invariants | Details blocks | Sync |
|---|---:|---:|---:|---|
| Pasta Project Overview | 6 | 409 | 0 | `4302713` ✗ |
| Page types & FSM implementation | 28 | 4,733 | 0 | `a35b133` ✓ |
| Reads & navigation | 18 | 1,834 | 0 | `a9f8689` ✗ |
| Search & introspection | 8 | 740 | 0 | `7689a5c` ✓ |
| Authoring & mutation | 17 | 2,627 | 0 | `a6a3196` ✗ |
| Self-direction | 10 | 808 | 0 | `a6a3196` ✗ |
| Archiving | 6 | 283 | 0 | `d335abe` ✗ |
| Web UI, HMR & live reload | 14 | 937 | 3 | `1489cf5` ✗ |
| Page-type documentation generation | 11 | 948 | 3 | `a35b133` ✓ |
| Scheduled workspace cleanup | 9 | 447 | 7 | `d335abe` ✗ |
| **Total** | **127** | **13,766** | **13** | 3 of 10 reachable |

✗ marks a sync commit that is not an ancestor of HEAD (orphaned by the history re-cut), so
`git diff <sync>..HEAD` cannot be used to check that page for drift.

## The triage rule

Every invariant is read sentence by sentence and each sentence lands in exactly one of four
buckets:

- **A — assertion.** A property that can be checked and broken. Stays in `invariants`, reduced to
  the claim plus what breaks when violated. Target: one to three sentences.
- **B — mechanism.** How the code achieves it, which symbol does what, the walk-through. Moves to
  `details`.
- **C — rationale / history.** Why this and not the alternative; what rule this replaced; what was
  tried and rejected; notes about tests that do or do not pin it. Moves to `details`.
- **D — false.** Contradicted by the code at `a35b133`. Corrected if the underlying property still
  holds in another form, dropped if it does not. Every D is recorded in the page's Details with
  what the code actually does, so the correction is visible rather than silent.

A long invariant typically splits A + B + C, producing one sharpened invariant and one or two
Details paragraphs.

## Case-by-case truth evaluation

An invariant is only migrated once its claim has been checked against the source at `a35b133`.
Nine defects are already confirmed in COMPARISON.md (D1–D9) and are fixed as part of this pass:

| Ref | Page(s) | Correction to apply |
|---|---|---|
| D1, D2 | Overview; Reads & navigation | `_write_file` uses `os.replace` (twice, the second after a 0.1s retry), not `Path.copy` + unlink. The "destination is briefly incomplete" reasoning goes with it — but the readers-writer lock is still real and still wanted, so the invariant keeps the lock and loses the copy mechanism. |
| D3 | Authoring & mutation | Drop `mutatePage`; a single mutation is a one-command batch. |
| D4 | Reads & navigation; Archiving | `tree` takes `workspaceId` only. Archived subtrees are *always* hidden; "by default" and `includeArchived=true` are gone. Reach an archived page via `getPage`, or the web `?archived=true` view. |
| D5 | Authoring & mutation; Self-direction | The setter validators are called from `validate_page_type`, not `PageType.__post_init__`. The property (a type cannot declare two do-eligible setters for one field) still holds — it is enforced at registry validation, i.e. at load, not at construction. |
| D6 | Scheduled workspace cleanup | `Store._lock_for` is now `_transaction_lock_for` (writers) plus `_rw_lock_for` (per file operation). |
| D7 | Scheduled workspace cleanup | `scheduler_enabled()` is `PASTA_CLEANUP != "0"` with no transport branch; `start_scheduler` is called only from `server.app_lifespan` and `hmr_server.reloader_lifespan`, neither of which runs under `--stdio`. So `PASTA_CLEANUP=1` cannot force-enable the sweep on stdio. |
| D8 | Authoring & mutation | Code reference: `set_title_cmd` is in `core/commands.py`, not `core/args.py`. |
| D9 | Search & introspection | `body_args` is a field on `BlockKindSpec`, read as `block.body_args`, not a method call. |

Beyond these, each remaining invariant gets a targeted check of the symbols it names before it is
rewritten. Anything that cannot be confirmed is left in `invariants` untouched and flagged in the
report rather than silently reworded — a migration must not become an unreviewed edit.

## Extract-and-combine mechanics

Rewriting from memory would lose the prose. So:

1. **Extract.** `tmp/extract.py` reads the live workspace JSON
   (`C:/Repos/pasta/.pasta-data/ws_mrteq0c5-238cf6.json`) and writes one
   `tmp/extract/<page-slug>.txt` per page holding, verbatim: the existing details blocks with their
   ids, and every invariant numbered with its element id and word count. The element ids are what
   `removeInvariant` needs.
2. **Triage in place.** Each extract file gains a `tmp/plan/<page-slug>.md` beside it, in which
   every `INV[n]` is marked `A` / `B` / `C` / `D` and the target Details paragraph is assembled
   **by pasting the source sentences**, grouped under a header.
3. **Combine under headers.** `details` accepts only `paragraph` and `code` blocks — there is no
   heading kind — so a Details section is a run of paragraphs, each opening with a bold inline run
   acting as its header (the field's own description notes that emphasis is structured inline runs,
   not markdown syntax). Related sentences from several invariants combine under one header instead
   of becoming one paragraph each.
4. **Cross-reference.** Each Details paragraph names the invariant it explains, in words ("the
   invariant that …"), because inline runs can reference a *page* but not an invariant element.
   The surviving invariant carries no back-pointer: it has to stand alone as a checkable claim.

## Write mechanics per page

`current` is a terminal status: `nextActions` on one of these pages offers `author` alone, so every
authoring command is locked until the page transitions back. A transition regenerates the revision
token and so must be the last command in its batch. Each page therefore takes three batches:

1. `author` — alone, since a transition ends a batch. Pages created before the revision feature
   carry a null token, so the first call omits `statusRevisionToken` entirely (an absent key reads
   as `None` and matches). The response echoes the new token.
2. The authoring batch, every command carrying that token: `addDetails` for the new blocks,
   `removeInvariant` for each migrated element, `addInvariant` for each sharpened replacement.
   Ordering note: add the Details blocks *before* removing invariants, so an aborted batch never
   leaves a page with the prose deleted and nothing in its place.
3. `recordSync` with `a35b133`, then `markCurrent` last.

If a batch is rejected nothing commits and the page stays in `authoring` — recoverable by re-running
batch 2 with the token the error reports.

## Order of work

Smallest first, to validate the mechanics on a page whose whole invariant set fits on one screen,
then by descending drift risk, with the 4,733-word page last:

1. **Archiving** (6) — pilot; carries D4.
2. **Pasta Project Overview** (6) — carries D1, the worst single defect.
3. **Scheduled workspace cleanup** (9) — carries D6, D7; already has 7 details blocks to extend.
4. **Self-direction** (10) — carries D5.
5. **Search & introspection** (8) — carries D9.
6. **Page-type documentation generation** (11) — sync already current.
7. **Web UI, HMR & live reload** (14).
8. **Reads & navigation** (18) — carries D2, D4.
9. **Authoring & mutation** (17) — carries D3, D5, D8.
10. **Page types & FSM implementation** (28, 4,733 words) — last, and worth splitting its Details
    into topic groups (declaration & construction, the FSM contract, the test-registry swap, the
    core layering, the retired machine cache) rather than one paragraph per source invariant.

## Result

All ten pages migrated. Measured after the pass:

| Page | Invariants | Invariant words | Details blocks |
|---|---|---|---|
| Pasta Project Overview | 6 → 5 | 409 → 235 | 0 → 5 |
| Page types & FSM implementation | 28 → 20 | 4,733 → 923 | 0 → 15 |
| Reads & navigation | 18 → 17 | 1,834 → 780 | 0 → 14 |
| Search & introspection | 8 → 8 | 740 → 350 | 0 → 5 |
| Authoring & mutation | 17 → 16 | 2,627 → 712 | 0 → 12 |
| Self-direction | 10 → 11 | 808 → 502 | 0 → 5 |
| Archiving | 6 → 6 | 283 → 234 | 0 → 4 |
| Web UI, HMR & live reload | 14 → 14 | 937 → 752 | 3 → 7 |
| Page-type documentation generation | 11 → 11 | 948 → 506 | 3 → 9 |
| Scheduled workspace cleanup | 9 → 9 | 447 → 447 | 7 → 8 |
| **Total** | **127 → 117** | **13,766 → 5,441** | **13 → 84** |

Total prose across both fields went from roughly 14,400 words to 16,262 — it grew rather than
shrank, which is the check that nothing was lost: every migrated sentence landed in a Details
paragraph, and the increase is the connective tissue plus the eleven correction notes.

Notes on individual pages:

- **Scheduled workspace cleanup** kept all nine invariants unchanged in length. Case by case they
  were already assertion-plus-breakage, so the only work was correcting D6 and D7 and extending
  Details. That is the intended outcome of "evaluate case by case" rather than a missed page.
- **Self-direction** gained an invariant (10 → 11) because one 174-word entry carried two
  independent rules — what enters `do`, and the one-setter-per-field guarantee — which split into
  two assertions.
- **Page types & FSM implementation** shrank hardest (4,733 → 923). Its Details were grouped by
  theme rather than one paragraph per source invariant, since several invariants restated the same
  machine-per-spec and tuple-not-mapping material.
- Two defects beyond the original nine were found during the pass and corrected: **D10** (the
  Overview described MCP tools as sync functions; all 24 are `async def`) and **D11** (Authoring &
  mutation's concurrency argument rested on that same premise).
- Stale claims also lived in `usage` and `dataModel` prose, not only in invariants — `mutatePage`,
  `tree(includeArchived)`, and the `Path.copy` description. Those fields were corrected surgically,
  preserving every surrounding sentence verbatim. A scan for the eleven defect signatures across
  every prose, block and invariant field on all ten pages now comes back clean.

## Done means

- Every page's `invariants` reads as a checklist: each entry a claim plus its breakage, none longer
  than about three sentences.
- No prose was lost — every B and C sentence appears in some Details paragraph.
- Every page's `sync.commit` is `a35b133`, a commit reachable from HEAD.
- The nine known defects are corrected, and each correction is visible in Details.
- Each page ends in status `current`.
