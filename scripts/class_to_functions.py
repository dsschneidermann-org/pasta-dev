#!/usr/bin/env python3
"""One-shot migration: rewrite call sites for the methods lifted out of pagetypes/core.

Seven public methods moved off their frozen dataclasses to module-level functions whose
first parameter is the former ``self`` (now annotated with the class). This rewrites every
call site ``recv.METHOD(args)`` into the free-function form:

  * ``field_spec`` / ``command`` (on ``PageType``) -> ``pagetype.METHOD(recv, args)``
    They are module-qualified because the bare names collide with pervasive local variables
    (``field_spec = ...``; a ``command`` string arg in store.py). ``pagetype`` is never a local,
    so the qualifier never shadows. Inside pagetype.py itself the call stays bare.
  * ``body_args`` / ``element_blocks_spec`` / ``block_element_fields`` /
    ``title_element_field`` / ``guidance_for`` -> ``METHOD(recv, args)`` (imported by name;
    none of these names is used as a local variable anywhere).

The receiver span and argument span come from the AST (exact source offsets), so a chained
receiver like ``get_page_type("x").fsm`` is carried across intact. Imports are added by hand,
not here. Idempotent: an already-qualified ``pagetype.field_spec(...)`` is skipped.

Usage: ``python scripts/class_to_functions.py <file.py> ...`` (rewrites in place).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

QUALIFY = {"field_spec": "pagetype", "command": "pagetype"}
BARE = {"body_args", "element_blocks_spec", "block_element_fields",
        "title_element_field", "guidance_for"}
TARGETS = set(QUALIFY) | BARE


def _line_offsets(text: str) -> list[int]:
    """Absolute character offset of the start of each 1-indexed line."""
    offsets, total = [0], 0
    for line in text.splitlines(keepends=True):
        total += len(line)
        offsets.append(total)
    return offsets


def _pos(offsets: list[int], lineno: int, col: int) -> int:
    return offsets[lineno - 1] + col


def rewrite(path: Path, defining_module: str) -> int:
    src = path.read_text(encoding="utf-8")
    offsets = _line_offsets(src)
    edits: list[tuple[int, int, str]] = []
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in TARGETS:
            continue
        method, recv = func.attr, func.value
        # Idempotency: leave a call already written as `pagetype.field_spec(...)` alone.
        if isinstance(recv, ast.Name) and recv.id == "pagetype" and method in QUALIFY:
            continue
        call_start = _pos(offsets, node.lineno, node.col_offset)
        call_end = _pos(offsets, node.end_lineno, node.end_col_offset)
        recv_end = _pos(offsets, recv.end_lineno, recv.end_col_offset)
        recv_src = src[_pos(offsets, recv.lineno, recv.col_offset):recv_end]
        open_paren = src.index("(", recv_end)  # the call's '(' follows `.METHOD`
        args_src = src[open_paren + 1:call_end - 1].strip()
        prefix = (f"{QUALIFY[method]}." if method in QUALIFY
                  and defining_module != QUALIFY[method] else "")
        joined = recv_src if not args_src else f"{recv_src}, {args_src}"
        edits.append((call_start, call_end, f"{prefix}{method}({joined})"))
    edits.sort()
    for (_, a_end, _), (b_start, _, _) in zip(edits, edits[1:]):
        if a_end > b_start:
            raise SystemExit(f"{path}: overlapping target calls; aborting")
    for start, end, replacement in reversed(edits):
        src = src[:start] + replacement + src[end:]
    if edits:
        path.write_text(src, encoding="utf-8")
    return len(edits)


def main(argv: list[str]) -> None:
    total = 0
    for arg in argv:
        path = Path(arg)
        count = rewrite(path, defining_module=path.stem)
        print(f"{path}: {count} call site(s) rewritten")
        total += count
    print(f"total: {total}")


if __name__ == "__main__":
    main(sys.argv[1:])
