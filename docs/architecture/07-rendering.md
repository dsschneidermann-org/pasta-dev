# Rendering

## Summary

**Kind:** subsystem

Two pure projections of a page: `render.py` produces the Markdown that MCP clients read, and
`render_html.py` produces the structured HTML the browser view shows — both generic over page
types, both performing no I/O.

## Purpose

A page is stored as `sections[sectionKey][fieldKey]` values plus a page-type declaration. On its
own that is unreadable. This subsystem exists to turn the pair into something a human or an agent
can read, driven entirely by the declaration — so a new page type gets a correct rendering with no
renderer change.

It also exists to keep that work *pure*. Both renderers take model objects and page types in and
return strings out, which is what lets the store expose `render_markdown` / `render_html` as thin
wrappers and lets the whole rendering surface be tested without a filesystem.

`render.py` carries a third job that belongs nowhere else: `page_text` is the flat text projection
that `Store.search` matches against, so search and display agree on what a page's content *is*.

There are deliberately **two** renderers rather than one with a mode flag. The Markdown renderer
is a returned contract — MCP clients receive its output — and stays as it is. The HTML renderer
exists because a list element carrying several fields reads badly as one flattened bullet; on the
web each element gets its own titled block with labelled rows.

## Usage

**Markdown** (`src/render.py`):

- `render_page(page, page_type, level=1, ref_context=None)` — a title heading, then *every*
  declared section and field, then `References` and `Child pages`.
- `render_tree(workspace, show_archived=False)` and `render_workspace_links(...)` — the workspace
  tree; the latter is what the HTML nav and index use.
- `build_ref_context(workspace, show_archived, escape_plain_text)` — build the workspace view the
  renderer needs to turn page ids into titled links. Call this first on the store-driven path.
- `render_blocks(blocks, ref_context=None)` — the blocks grammar → Markdown (4 callers).
- `page_text(page, page_type)` — the flat projection for search.
- `escape_markdown(text)` — escape a plain-text leaf. **Web path only.**
- `checkbox_state(status, element_fsm)` — public so every renderer answers the checkbox question
  identically and then spells it its own way.

**HTML** (`src/render_html.py`):

- `render_page_html(page, page_type, ref_context=None)` — header, contents strip, every section
  and field, then references and children.
- `element_view(element, index, field_spec)` — decompose one stored element for display; the
  single home of the title, row, and checkbox rules.
- `md2html = Wenmode(github)` — the Markdown→HTML converter, also imported directly by
  `src/server.py` for the index and nav strips.

Both are reached in practice through `Store.render_markdown` / `Store.render_html`, which load the
workspace, build the `RefContext`, and call in. A direct call with `ref_context=None` is supported
and degrades gracefully: refs and child links fall back to bare ids.

## Data model

Owns no persistent state. Two transient view types:

- **`RefContext`** (`render.py`) — the workspace view needed to turn page ids into titled,
  annotated links: `titles`, `types`, and `statuses` for *every* page id (archived included),
  `archived_ids` as the archived subset, `workspace_id`, plus two render-mode flags —
  `show_archived` (carried into generated links as `?archived=true`, so following one keeps the
  archived view) and `escape_plain_text`.
- **`ElementView`** (`render_html.py`) — one list element decomposed before any HTML exists:
  `element_id`, `index`, `title`, `check`, and its rows. A row value of `None` means the field is
  declared but empty.

Everything both renderers produce is derived and recomputed per call. Nothing is cached, so no
invalidation problem exists.

`escape_plain_text` is the one piece of genuinely mode-dependent behaviour, and the asymmetry is
intentional: the web path runs a whole-document Markdown→HTML pass, so a plain-text leaf
containing `**` or a leading `-` must be escaped to render verbatim; the MCP path returns Markdown
unescaped, because its consumer *wants* Markdown.

## Details

Both renderers render the page's **shape**, not just its content. Every declared section and field
appears, and an empty field (or empty list) renders the italic `*None.*` fallback — `_NONE_HTML`
on the web side. That is what makes an unfilled page self-describing: an agent can see what is
missing without a `describePageType` round trip.

`toc` is the one type-specific branch in either renderer, and both carry it for the same stated
reason: a toc carries no subject matter and — being the only type with no authoring commands,
hence no `addLink` — can never hold an outgoing link, so its `References` list is always empty. It
therefore renders as its title, meta line, and bare child list, with no section headings: *that
child list is the table of contents.* This is worth flagging as the subsystem's only concession to
a specific tag; everything else is derived from the declaration.

The checkbox rule is shared rather than duplicated. `checkbox_state` maps an element's FSM state
to `"done"` (the `checkmark_done` state), `"todo"` (the FSM's `initial`, i.e. unchecked), or
`None` — any other state, an FSM with no `checkmark_done`, or a list field with no element FSM at
all. Each renderer then spells that its own way: `[x]` / `[ ]` in Markdown, a styled check on the
web. The `RenderPage → Checkbox_state` process is one of the longest execution flows in the graph
(9 steps).

`element_view` concentrates the rules that make a list read consistently: the heading comes from
the field the *type* declares as its heading (`title` or `name`, per `TITLE_ELEMENT_FIELDS`) and
from no other field, so every element of one field renders with the same shape whatever its values
are — and a list whose type declares neither is headed by its ordinal alone. The heading field is
consumed by the heading and never repeated as a row; block-bearing fields are neither heading nor
plain row and get their own tuple.

`_page_link` resolves a page id wherever it appears — not only on a child or reference edge, but
also inside a list element field, where an id is stored as ordinary text. Resolving on the value
means a pasted page id becomes a titled `type · status` link in every position.

On the graph: `render.py` holds `Cluster_64` alone, and shares a 19-symbol community with
`render_html.py` (3 `CALLS` edges run `render_html.py → render.py` — the HTML renderer reuses the
Markdown one for block content inside element rows, via `md2html.render(markdown)`). `_escape` has
9 callers and `_plain` 7 — the leaf-level helpers, and the reason a change to escaping behaviour
is worth an `impact` run.

## Code references

| File | Symbol | Kind |
|---|---|---|
| `src/render.py` | `render_page` | function |
| `src/render.py` | `render_tree` | function |
| `src/render.py` | `render_workspace_links` | function |
| `src/render.py` | `render_blocks` | function |
| `src/render.py` | `build_ref_context` | function |
| `src/render.py` | `RefContext` | class |
| `src/render.py` | `page_text` | function |
| `src/render.py` | `escape_markdown` | function |
| `src/render.py` | `checkbox_state` | function |
| `src/render_html.py` | `render_page_html` | function |
| `src/render_html.py` | `element_view` | function |
| `src/render_html.py` | `ElementView` | class |
| `src/render_html.py` | `md2html` | constant |
| `src/render_html.py` | `_escape` | function |

## Dependencies

| Target | Role | Note |
|---|---|---|
| [Domain model](04-domain-model.md) | depends-on | reads `Page` / `Workspace`; never mutates either |
| [Page-type system](05-page-type-system.md) | depends-on | `FieldSpec`, `PageType`, the field-kind constants, `block_element_fields`; `render.py` also calls `get_page_type` for child annotations |
| `wenmode` | depends-on | `Wenmode(github)` is the Markdown→HTML pass behind `md2html` |
| [Workspace store](02-workspace-store.md) | exposes | `render_markdown` / `render_html` / `search` are thin wrappers over these functions |
| [MCP & HTTP transport](01-mcp-http-transport.md) | exposes | `escape_markdown`, `render_workspace_links`, and `md2html` are imported directly for the nav and index strips |

## Invariants

1. **Both renderers are pure.** Model objects and page types in, a string out; no I/O, no
   mutation of the page. Violated, rendering can fail or block on the environment, and the
   store's monopoly on effects is gone.
2. **Every declared section and field appears in the output, filled or not.** An empty one renders
   the `*None.*` fallback. Violated, an agent cannot see what remains to be authored from a render
   alone and must round-trip to `describePageType`.
3. **`escape_markdown` is applied on the web path and never on the MCP path.** Governed by
   `RefContext.escape_plain_text`. Violated in one direction, a plain-text value containing
   Markdown syntax renders as formatting in the browser; in the other, MCP clients receive
   double-escaped text.
4. **`checkbox_state` is the only place the checkbox question is answered.** Both renderers call
   it. Violated, Markdown and HTML disagree about whether an element is done — the same page reads
   differently depending on the surface.
5. **An element's heading comes from the declared heading field and no other.** Decided once in
   `element_view`. Violated, elements within a single list render with inconsistent shapes
   depending on which fields happen to be filled.
6. **A render with no `RefContext` still succeeds.** Refs and child links fall back to bare ids.
   Violated, `render_page` becomes unusable outside a loaded workspace, and the pure-function
   tests need a workspace fixture.
7. **`page_text` covers the same content the renderers display.** It is the projection
   `Store.search` matches on. Violated, search silently fails to find text that is plainly visible
   on the page.

## Sync

Reconciled against commit `a35b133`.
