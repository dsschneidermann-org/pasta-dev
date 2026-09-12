# Introspection & doc generation

## Summary

**Kind:** subsystem

The pure projection of page-type declarations into consumable schemas — JSON for the
`describePageType` / `describeMutations` tools, and Sphinx Markdown with state diagrams for the
documentation site.

## Purpose

A page type is only useful to a client that can discover its shape. This subsystem exists to
answer "what can I author here, and what may I do next" without an instance (`describe_page_type`)
and for one specific page (`describe_mutations`), which is what lets an agent work against a page
type it has never seen.

The doc-generation half exists so the published documentation **cannot drift from the code**. Every
page in the docsite is derived from the same declarations the server enforces: if a status gains a
transition, the generated state doc gains it too, with no one to remember to update it.

Delete this component and two things break: an MCP client loses schema discovery and has to
hard-code command shapes (which `instructions()` explicitly tells agents not to do), and the
docsite becomes hand-maintained prose about a machine-enforced system.

**Entirely pure.** `docsgen` reads the registry and returns strings, performing no I/O at all —
the `scripts/gen_page_type_docs.py` driver writes what it returns into
`docsite/page-types/`. That split is why doc generation is unit-testable.

## Usage

**Introspection** (`src/describe.py`), called by the transport:

- `describe_page_type(page_type)` → tag, name, description, `describe_fsm(...)`, and every
  section with its fields — the type-level schema, no instance needed.
- `describe_mutations(page, page_type, ignore_requirements=False)` → every command with its arg
  schema and `available` (whether it is legal *right now*).
- `command_arg_schema(command)` → a JSON Schema object for one command's arguments.
- `describe_fsm(page_type)` → initial, states, transitions with `agency`, and `statusGuidance`.

**Doc generation** (`src/docsgen.py`), called by the script driver:

- `all_state_docs(registry=None)` → every `<tag>-<state>` doc across the registry; defaults to
  `registered_pagetypes()`.
- `state_docs(page_type)` → one Markdown doc per reachable state of one type.
- `render_states_index(registry=None)` → the generated `states.md` toctree.
- `reachable_states(fsm)` → each reachable state mapped to the shortest event path that reaches
  it.
- `page_machine_qualname(tag)` → the importable dotted path the diagram directive imports.

**Machine bindings** (`src/statecharts.py`, `src/testcharts.py`) — each serves the already-built
status machines under stable, importable names: `statecharts` resolves them lazily through a
module-level `__getattr__`, `testcharts` binds them eagerly as module constants.

Order matters in one place: `state_docs` captures `describe_page_type` **once** per type, then
`describe_mutations` **per state** on a seeded page. Regenerating is
`just` → `scripts/gen_page_type_docs.py` → `sphinx-build`.

## Data model

No persistent state and no owned types — this subsystem's entire output is dicts and strings
derived from declarations.

The one constructed value worth naming is `_seed_page(page_type, state)`: a content-less `Page`
with id `<tag>:doc`, pinned at `state`, with `initial_sections(page_type)`. It exists only to give
`describe_mutations` something to answer about, and is never persisted.

`describe_fsm` returns `statusGuidance` as a **dict**, with a comment explaining why that is safe
here: it is a projection, unlike `FSMSpec.status_guidance`, which must stay a tuple to keep the
spec hashable.

`command_arg_schema` injects `statusRevisionToken` as every command's first argument and marks it
required — the schema-level expression of the store's optimistic-concurrency rule. The store reads
and strips it before the pure core sees the remaining arguments.

## Details

**Guardless machines are what make the FSM walk trivial**, and this is the clearest payoff of a
decision made in component 06. Because required-content preconditions and status locks live in
`commands.py` rather than in the machine, the `statemachine-diagram` directive can replay *any*
`:events:` path on a content-less page, and `reachable_states` can be a plain breadth-first walk
with no content simulation. `reachable_states` returns the **shortest** path to each state
precisely so the generated `:events:` option stays short.

**`ignore_requirements=True` exists for this subsystem alone.** Doc generation sets it so
content-gated transitions still enumerate at each state — a doc should list the transitions a
status *has*, not only those a content-less page could fire today. The live `describeMutations`
tool leaves it `False`, and the flag is not exposed through it. It skips only the required-content
preconditions: FSM topology, the `legal_in` status lock, and the terminal-status authoring lock
all still apply.

**The binding modules exist to give a machine an importable address.** A page type builds its
status machine when it is declared, which makes the class an anonymous attribute of a spec.
Sphinx's diagram directive needs a dotted path, so `statecharts.py` serves each production
machine under a stable name, and `page_machine_qualname` derives the path from the page type —
then *checks* the binding really exists, which is what stops a type whose binding was never added
from going silently undocumented.

The two binding modules differ in mechanism, and the asymmetry is load-bearing.
`statecharts.__getattr__` resolves **per call** against the live `REGISTRY`, matching
`f"{page_type.fsm.name}Machine"` and raising `AttributeError` otherwise — deliberately not a
snapshot taken at import, so an HMR reload of the page types cannot leave a stale class bound
here. `testcharts.py` instead binds its six fixtures eagerly as module constants
(`TestFieldsMachine = machine_class(_page_fsm("test-fields"))`, …), which is safe because the
fixtures are only loaded inside a test run that already flipped test mode on before collection.

`testcharts.py` is the fixture counterpart, and `_bindings_module()` chooses between them at call
time:

```python
if is_test_mode():
    from . import testcharts
    return testcharts
from . import statecharts
```

The local import is deliberate — it keeps the test fixtures out of a live server's import graph.
Only *page-status* machines are bound: an element machine is reached through the field that
declares it and needs no importable address.

`statecharts.py` reads `REGISTRY` directly rather than `registered_pagetypes()`, because the
documentation site publishes the production types regardless of which registry is in play — one of
the few justified direct reads of the map.

On the graph: `docsgen.py` holds `Cluster_24` (6 symbols, 83% cohesion) and depends on both
`describe.py` (2 `CALLS`) and `_registry.py` (4 `CALLS`); `statecharts.py` and `testcharts.py`
resolve to a single `__getattr__` symbol each, which is why they barely register in the community
structure despite being load-bearing for the docsite.

## Code references

| File | Symbol | Kind |
|---|---|---|
| `src/describe.py` | `describe_page_type` | function |
| `src/describe.py` | `describe_mutations` | function |
| `src/describe.py` | `describe_fsm` | function |
| `src/describe.py` | `command_arg_schema` | function |
| `src/describe.py` | `_block_schema` | function |
| `src/docsgen.py` | `all_state_docs` | function |
| `src/docsgen.py` | `state_docs` | function |
| `src/docsgen.py` | `reachable_states` | function |
| `src/docsgen.py` | `page_machine_qualname` | function |
| `src/docsgen.py` | `_bindings_module` | function |
| `src/docsgen.py` | `_seed_page` | function |
| `src/docsgen.py` | `render_states_index` | function |
| `src/statecharts.py` | `__getattr__` | function |
| `src/testcharts.py` | `_page_fsm` | function |
| `src/testcharts.py` | `TestFieldsMachine` | constant |
| `scripts/gen_page_type_docs.py` | *(the I/O driver)* | file |

## Dependencies

| Target | Role | Note |
|---|---|---|
| [Page-type system](05-page-type-system.md) | depends-on | reads the registry and every spec; `docsgen` calls `registered_pagetypes` (4 edges) |
| [Mutation engine](03-mutation-engine.md) | calls | `legal_commands` supplies the `available` flag and the per-state command surface |
| [FSM evaluation](06-fsm-evaluation.md) | calls | `machine_class` is what the binding modules serve |
| [Domain model](04-domain-model.md) | depends-on | constructs the seeded `Page` for per-state capture |
| [MCP & HTTP transport](01-mcp-http-transport.md) | exposes | backs the `describePageType` and `describeMutations` tools |

## Invariants

1. **`docsgen` performs no I/O.** It returns strings; `scripts/gen_page_type_docs.py` writes them.
   Violated, doc generation needs a filesystem fixture to test and can no longer run as a pure
   projection.
2. **Every reachable state of every registered page type gets a doc.** `all_state_docs` iterates
   the registry and `reachable_states` the FSM. Violated, a state exists in the machine that the
   docsite never describes, and the drift the subsystem prevents reappears.
3. **Every page type being documented has a bound, importable machine.**
   `page_machine_qualname` verifies the binding rather than assuming it. Violated, the Sphinx
   diagram directive fails to import the class, and a type whose binding was forgotten goes
   silently undocumented.
4. **`ignore_requirements` never reaches the live tool.** `describeMutations` leaves it `False`.
   Violated, a client is told a content-gated transition is `available` when `mutatePageBatch`
   would reject it.
5. **Every command's schema requires `statusRevisionToken`.** Injected unconditionally by
   `command_arg_schema`. Violated, a client builds a call without the concurrency stamp and every
   write fails at the store with a conflict it had no way to anticipate.
6. **The seeded page is never persisted.** It exists only as a `describe_mutations` argument.
   Violated, doc generation writes `<tag>:doc` pages into a real workspace.
7. **Test fixtures stay out of a live server's import graph.** `_bindings_module` imports
   locally, under a `is_test_mode()` branch. Violated, `src/testtypes.py` is imported in
   production, and the test-mode isolation boundary is no longer structural.

## Sync

Reconciled against commit `a35b133`.
