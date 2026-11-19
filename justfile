
docs:
    rm -rf docsite/page-types
    uv run python scripts/gen_page_type_docs.py
    uv run sphinx-build -a docsite -b html docsite/_build/html

probe:
    uv run python scripts/mcp_probe.py

# Walk a real feature-brief through its whole lifecycle, printing each stage's `do` rollup,
# then archive it. Server must be running. Pass args through, e.g. `just brief-probe --keep`.
brief-probe *ARGS:
    uv run python scripts/feature_brief_probe.py {{ARGS}}

test:
    #!/bin/bash
    export PYTHONDONTWRITEBYTECODE=1
    uv run pytest

testincr:
    #!/bin/bash
    export PYTHONDONTWRITEBYTECODE=1
    uv run pytest --testmon

types:
    uv run basedpyright

validate:
    uv run python scripts/validate_workspace.py

# Copy pasta's own workspace and its event log into `.pasta-data/snapshot/` and commit the copies on
# the current branch. Only the copies are tracked, so a pull updates them and never the live files.
commit-workspace:
    #!/bin/bash
    set -e
    mkdir -p .pasta-data/snapshot
    cp .pasta-data/ws_mrteq0c5-238cf6.json .pasta-data/ws_mrteq0c5-238cf6.events.jsonl .pasta-data/snapshot/
    files=".pasta-data/snapshot/ws_mrteq0c5-238cf6.json .pasta-data/snapshot/ws_mrteq0c5-238cf6.events.jsonl"
    git add -f $files
    if git diff --cached --quiet -- $files; then
        echo "pasta's workspace is unchanged since its last commit."
        exit 0
    fi
    git commit -m "Snapshot pasta's workspace and its event log" -- $files

# Copy each workspace in the data dir's `snapshot/` back in when it has no live file of its own,
# with its event log unless a live one exists. A live file is never replaced.
_restore-workspace:
    #!/bin/bash
    set -e
    data="${PASTA_DATA_DIR:-.pasta-data}"
    for snapshot in "$data"/snapshot/ws_*.json; do
        [ -e "$snapshot" ] || continue
        name="$(basename "$snapshot" .json)"
        [ -e "$data/$name.json" ] && continue
        cp "$snapshot" "$data/$name.json"
        if [ -e "$data/snapshot/$name.events.jsonl" ] && [ ! -e "$data/$name.events.jsonl" ]; then
            cp "$data/snapshot/$name.events.jsonl" "$data/$name.events.jsonl"
        fi
        echo "Restored $name from $data/snapshot/"
    done

main: _restore-workspace
    uv run python main.py

sphinx:
    uv run sphinx-autobuild docsite -q -b html docsite/_build/html \
    --watch src --port 8081 \
    --pre-build 'uv run python scripts/gen_page_type_docs.py'

[parallel]
dev: main sphinx

sync-wiki:
    gitnexus analyze --index-only --force
    uv run python scripts/reset_stale_wiki.py
    gitnexus wiki
    cp -f .gitnexus/wiki/index.html ../pasta.dennis-s.dk/index.html
