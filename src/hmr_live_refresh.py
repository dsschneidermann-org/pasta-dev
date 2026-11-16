"""The dev server's state that has to outlive a hot reload: the live browser sockets and the
last reload failure.

This module is deliberately kept OUT of the hot-reload set: `src/hmr_server.py` never
re-imports it. It holds live browser WebSocket connections as in-process state
(`ws_reloader.active`); if it were re-executed on every source change, that state would be
dropped and browser auto-refresh would silently stop working. It is imported by both the
reloaded `src.server` (routes, mutation refreshes, refusal gates) and the stable
`src.hmr_server` (file-change refreshes, reload outcomes), so a single instance survives reloads.
"""

from __future__ import annotations

from fastapi import WebSocket


class ReloaderConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active.remove(websocket)

    async def refresh(self):
        dead: list[WebSocket] = []
        for conn in self.active:
            try:
                await conn.send_text('{"refresh": 1}')
            except Exception:
                dead.append(conn)
        for conn in dead:
            self.active.remove(conn)


# Process-wide singleton. Must survive hot reloads, so it lives in this
# (reload-excluded) module rather than in the reloaded server module.
ws_reloader = ReloaderConnectionManager()


# Why the last hot reload failed, until one succeeds. Both refusal gates read it, and they may be
# the gates of the build a failed reload rolled back to, so it lives here rather than in either.
_reload_failure: str | None = None


def set_reload_failure(summary: str | None) -> None:
    """Record why the last reload failed, or clear it once a reload succeeds."""
    global _reload_failure
    _reload_failure = summary


def reload_failure() -> str | None:
    """Why the last reload failed, while no reload has succeeded since; otherwise None."""
    return _reload_failure
