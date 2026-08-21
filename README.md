# pasta MCP server


`pasta-project` (Python 3.14, `uv`) is a **implementation of the pasta MCP server** - a structured wiki over MCP where each page is a typed page-type instance with a status FSM, authored via validated commands. Stack: **FastMCP** for serving, **python-statemachine** for page status FSMs, **plain JSON files** for storage (one file per workspace, per-workspace lock, atomic temp-file+os.replace writes; copy→edit→batch→overwrite).

**Architecture = pure core + stateful shell.** Pure (no I/O, unit-tested): `src/{model,pagetypes,fsm,commands,serialize,describe}.py`. Shell (integration-tested): `src/{store,server}.py`.


## Run

```bash
uv sync                 # install deps (Python 3.14)
uv run pytest           # run the test suite
```

The data directory defaults to `./.pasta-data`; override with `PASTA_DATA_DIR`.
