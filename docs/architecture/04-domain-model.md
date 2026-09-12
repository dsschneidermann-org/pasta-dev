# Domain model

## Summary

**Kind:** module

The two dataclasses every other component passes around — `Workspace` and `Page` — plus the error
hierarchy those components raise, with no behaviour beyond copying and page lookup.

## Purpose

This is pasta's shared vocabulary. It exists to be the one definition of what a page *is* that the
store, the mutation engine, both renderers, the cleanup sweep, and the transport can all agree on
without importing each other.

Its most consequential design choice is what it deliberately does **not** contain: the shape of a
page's sections. Field values are plain JSON-able Python (`str`, `None`, `list[dict]`), and which
sections and fields a page has is defined by its page type, not here. That keeps this module tiny,
makes serialization a near-identity mapping, and means adding a page type requires no change to
the model at all.

The error hierarchy earns its place in the same module because it is the other half of the shared
vocabulary: it lets the pure core signal *why* something failed in terms the transport can
translate without knowing any domain detail — `_guard_tool` catches exactly `PastaError`.

Delete this component and every other component needs its own page representation plus a
conversion at each boundary.

## Usage

Both dataclasses are constructed directly, not through factories:

- **`Page(...)`** — built by `commands.create_page` (never by hand elsewhere) and by
  `serialize.page_from_dict` on load.
- **`Workspace(...)`** — built by `Store.create_workspace` and `serialize.workspace_from_dict`.
- **`workspace.get_page(page_id)`** — the lookup every caller uses; returns `None` rather than
  raising, so the caller chooses the error. 13 `CALLS` edges reach it from the store.
- **`page.copy()`** — called by the pure command path before any edit, so the input is never
  mutated.

The errors are raised by the pure core (`commands`, `fsm`, `serialize`) and by the storage shell
(`store`), and caught in exactly one place per surface: `_guard_tool` for MCP, `_guard_http` for
HTTP. `IllegalCommandError` additionally carries `legal`, the command names that *are* currently
available, so a caller can recover without a second round trip.

## Data model

**`Page`** — the unit of authoring:

| Field | Meaning | Written by |
|---|---|---|
| `id` | `<tag>:<token>`, e.g. `architecture:mqtcfkx1-a3f9` | `ids` factory at creation |
| `type` | page-type tag | creation only |
| `title` | display title | `setTitle` / `renamePage` |
| `status` | current FSM state *value* | transitions |
| `parent_id` | parent page, or `None` | reparent |
| `child_ids` | ordered children — **the structure the tree renders from** | create / reparent / reorder |
| `sections` | `sections[sectionKey][fieldKey] = value` | page-type commands |
| `archived` | hidden from default tree views; the page cannot be mutated | archive / unarchive |
| `links` | outgoing typed edges, `[{"to": pageId, "role": str}]` | `addLink` / `unlink` |
| `expires_at` | UTC ISO-8601 deletion deadline, or `None` | **the cleanup sweep only** |
| `status_revision_token` | optimistic-concurrency stamp on the status | **the store only** |

**`Workspace`** — `id`, `name`, `status` (`"active"` / `"archived"`), `root_page_ids`,
`pages: dict[str, Page]`, `created_at`, `updated_at`, and `guidance_config` (the
workspace-configurable guidance texts, set at runtime per workspace).

Everything here is persisted — this *is* the on-disk shape, via the near-identity mapping in
`serialize`. Nothing is derived or cached. Lifetime is the workspace file's; in memory, a
`Workspace` lives only for the duration of one store call.

Mutation paths are strictly partitioned, which is the point of the last two rows above: page-type
commands write `sections`, `title`, `status`, and `links`; the store writes
`status_revision_token`, `child_ids`, `parent_id`, and `archived`; the sweep writes `expires_at`.

The error hierarchy, all rooted at `PastaError` (the base for every *expected*, non-bug failure):

| Error | Raised when |
|---|---|
| `NotFoundError` | a workspace, page, or element id does not resolve |
| `ValidationError` | command arguments are missing, of the wrong type, or not an enum member |
| `IllegalCommandError` | the command is not legal for this page now (carries `legal`) |
| `ConflictError` | a structural rule was violated — a reparent that would cycle, a stale-read anchor |
| `ProductionTypeInTestError` | a test touched a production page type while in test mode |

## Details

`Page.copy()` is a hand-written deep copy rather than `dataclasses.replace` or
`copy.deepcopy(self)`, and the distinction matters: `sections` gets a true `deepcopy`, `links`
gets fresh dicts, and `child_ids` a fresh list, so no nested structure is shared with the
original. This is what makes the mutation engine's no-mutate-input invariant hold for nested
content, not just top-level fields.

```python
def copy(self) -> "Page":
    """A deep copy - the pure command path edits a copy, never the input."""
    return Page(..., sections=copy.deepcopy(self.sections),
                links=[dict(link) for link in self.links], ...)
```

Two fields carry an explicit "written only by X" comment in the source, and both are
concurrency- or lifecycle-critical: `expires_at` (sweep only) and `status_revision_token` (store
only). `status_revision_token` is `None` on a page created before the feature existed, until its
first transition — so consumers must treat `None` as a legitimate current value rather than as
missing data.

`archived` deserves a note because two mechanisms interact: an archived page keeps
`archived=False` on the pages *beneath* it, so "hidden" is a property of the path, not the page.
The cleanup sweep's `reachability` walk is what resolves that, by tracking a `shadowed` flag down
the tree (see component 10).

`Workspace.status` is `"active" | "archived"` with archive-of-a-whole-workspace noted in the
source as deferred; `archive_workspace` / `unarchive_workspace` exist in the store and set this
field.

On the graph: `errors.py` forms its own community (`Cluster_2`, cohesion 100% — every symbol in it
relates to every other, which is what a pure type hierarchy looks like). `model.py` is
co-clustered with `commands.py` in the 114-symbol community labelled `Tests`; the two were split
along the `IMPORTS` edge into this component and component 03.

## Code references

| File | Symbol | Kind |
|---|---|---|
| `src/model.py` | `Page` | class |
| `src/model.py` | `Workspace` | class |
| `src/model.py` | `Page.copy` | function |
| `src/model.py` | `Workspace.get_page` | function |
| `src/errors.py` | `PastaError` | class |
| `src/errors.py` | `IllegalCommandError` | class |
| `src/errors.py` | `ConflictError` | class |
| `src/errors.py` | `ProductionTypeInTestError` | class |
| `src/errors.py` | `NotFoundError` | class |
| `src/errors.py` | `ValidationError` | class |

## Dependencies

| Target | Role | Note |
|---|---|---|
| *(none)* | — | imports only the standard library (`copy`, `dataclasses`, `typing`); the foundation of the DAG |

Every other component depends on this one. `errors.py` is imported by `commands`, `fsm`, `store`,
`server`, and four modules in the page-type layer; `model.py` by `store`, `commands`, `render`,
`render_html`, `serialize`, and `cleanup`.

## Invariants

1. **A page's section shape is never validated here.** This module accepts any JSON-able value;
   the page type defines the shape and `validation.py` enforces it. Violated, the model and the
   page-type declarations become two competing definitions of the same thing, and they will drift.
2. **`Page.copy()` shares no mutable structure with the original.** `sections` is deep-copied,
   `links` and `child_ids` rebuilt. Violated, an edit to a copied page's nested block list reaches
   back into the caller's page, and a rejected batch silently leaks changes.
3. **`sections` values stay JSON-able.** Only `str`, `None`, and `list[dict]` of JSON-able values.
   Violated, `workspace_to_dict` stops being a near-identity mapping and `json.dumps` fails at
   save time — after the command was accepted.
4. **`expires_at` is written only by the cleanup sweep; `status_revision_token` only by the
   store.** Violated, a page-type command can forge a deletion deadline or a concurrency stamp,
   making both the sweep and the conflict check unreliable.
5. **`child_ids` is the authoritative tree structure; `parent_id` is a convenience pointer.** The
   sweep's walk uses `child_ids` and ignores `parent_id` precisely so a stale pointer cannot cause
   a deletion. Violated — i.e. if a reader trusted `parent_id` — a stale pointer could hide or
   delete a reachable page.
6. **Every expected failure in pasta is a `PastaError` subclass.** Violated, `_guard_tool` does not
   catch it, and a domain-level problem surfaces to the agent as an unhandled server crash.

## Sync

Reconciled against commit `a35b133`.
