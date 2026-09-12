# pasta architecture

Ten architecture nodes covering `src/`, one per component. Each page follows the shape of
pasta's own `architecture` page type — Summary (with a `kind`), Purpose, Usage, Data model,
Details, Code references, Dependencies, Invariants, Sync — so a page can be transcribed into
a workspace page without reshaping it.

Everything here describes the code **as it exists** at commit `a35b133`. Aspirational design
belongs in a feature brief, not here.

## The component map

| # | Component | Kind | Files | Symbols |
|---|---|---|---|---|
| 01 | [MCP & HTTP transport](01-mcp-http-transport.md) | layer | `src/server.py`, `src/templates/` | 53 |
| 02 | [Workspace store](02-workspace-store.md) | subsystem | `src/store.py`, `rwlock.py`, `serialize.py`, `ids.py` | 107 |
| 03 | [Mutation engine](03-mutation-engine.md) | module | `src/commands.py` | 50 |
| 04 | [Domain model](04-domain-model.md) | module | `src/model.py`, `src/errors.py` | 30 |
| 05 | [Page-type system](05-page-type-system.md) | subsystem | `src/pagetypes/**`, `src/testtypes.py` | 294 |
| 06 | [FSM evaluation](06-fsm-evaluation.md) | module | `src/fsm.py` | 9 |
| 07 | [Rendering](07-rendering.md) | subsystem | `src/render.py`, `src/render_html.py` | 80 |
| 08 | [Introspection & doc generation](08-introspection-docsgen.md) | subsystem | `src/describe.py`, `docsgen.py`, `statecharts.py`, `testcharts.py` | 46 |
| 09 | [Dev server & HMR](09-dev-server-hmr.md) | subsystem | `src/hmr_server.py`, `hmr_live_refresh.py`, `_hmr_debug.py` | 44 |
| 10 | [Lifecycle & cleanup](10-lifecycle-cleanup.md) | module | `src/cleanup.py` | 40 |

See [COMPARISON.md](COMPARISON.md) for how these pages relate to the 10 hand-authored
`architecture` pages in the pasta workspace (`ws:mrteq0c5-238cf6`) — the differing decompositions,
nine confirmed drift defects in the workspace set, gaps on both sides, and a recommendation on
which approach to keep as primary.

## The layer stack

`check` over the graph reports **zero circular file imports** (0 cycles, 0 components), so the
component graph below is a DAG and can be read top-to-bottom. An arrow means *depends on*.

```
             main.py
            /       \
   hmr_server (09)   server (01) ──────► describe/docsgen (08)
            \       /      │
             \     /       ▼
              ▼   ▼    render, render_html (07)
            store (02) ───────────► cleanup (10)
                 │
                 ▼
           commands (03) ──────► fsm (06)
                 │                 │
                 ▼                 ▼
           model, errors (04)  pagetypes (05)
```

Two edges are worth naming because they run against the intuitive direction:

- **store → cleanup**, never the reverse. `cleanup` classifies purely and owns no transaction;
  the store performs the writes the classification implies.
- **pagetypes/core/pagetype → fsm**. A page type *builds* its state machines during its own
  declaration, so the page-type layer depends on the FSM module rather than the other way round.

## How the components were derived from the graph

The GitNexus index carries Leiden communities, but they are not usable as documentation units
straight out of the graph, for two measurable reasons:

1. **Fragmentation.** 45 distinct communities touch `src/`. Most hold a single file's symbols
   (`Cluster_14`, `Cluster_15`, `Cluster_16` are all `commands.py`; `Cluster_3`, `Cluster_35`–
   `Cluster_39` are all `hmr_server.py`), and the heuristic labels are generic — `Cluster_76`,
   `Cluster_81` — because the labeller found no dominant vocabulary.
2. **Label capture by tests.** Any community containing test symbols is labelled `Tests`, and
   the 717-symbol `Tests` community is by far the largest. The single biggest community touching
   `src/` (114 symbols) is labelled `Tests` while actually spanning `model.py` + `commands.py`.

So the ten components above were derived by aggregating communities rather than adopting them:

- **Merge communities with identical or near-identical file membership.** The three `commands.py`
  clusters became one component; the seven `hmr_server.py`/`hmr_live_refresh.py` clusters became
  one; the `ids.py` pair (`Cluster_40`, `Cluster_41`) folded into the store.
- **Cut along the `IMPORTS` DAG.** Where one community spanned two files that sit on opposite
  sides of an import edge, the edge won and the community was split — the 114-symbol community
  spanning `model.py` and `commands.py` became components 04 and 03.
- **Keep each component to a one-line job.** The `architecture` page type's own rule: if the
  summary needs an "and", it is two nodes.

Each component page records the communities it was built from, so the aggregation is auditable
against a re-index.

Two aggregations are load-bearing findings rather than bookkeeping, and each is called out on the
relevant page:

- **`server.py` and `store.py` are co-clustered six times over** (`Cluster_1`, `Cluster_74`,
  `Cluster_75`, `Cluster_77`, `Cluster_79`, `Cluster_81`). Each of those clusters pairs an MCP tool
  with the store method behind it — the graph's way of saying the transport holds no logic of its
  own. 35 `CALLS` edges run `server.py → store.py`, the heaviest file-pair in the repo.
- **`pagetype.py` and `fsm.py` share `Cluster_33`** (cohesion 83%), which is the machine-building
  coupling described above showing up as community structure.

## Regenerating the evidence

```bash
# refresh the index (from the repo root)
node .gitnexus/run.cjs analyze --index-only

# the queries these pages were written from
node .gitnexus/run.cjs impact "Store" --direction upstream --repo .
```

Community membership, the import DAG, and the call-volume table came from `cypher` queries over
the `CodeRelation` table; the per-symbol facts came from `context`, and the write-path chain from
`trace`. Every code reference below was confirmed by opening the file at `a35b133`.
