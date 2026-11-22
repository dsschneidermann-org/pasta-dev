"""The dev server's state that has to outlive a hot reload: the live browser sockets and the
last reload failure.

This module is deliberately kept OUT of the hot-reload set: `src/hmr_server.py` never
re-imports it. It holds live browser WebSocket connections as in-process state
(`ws_reloader.active`, the timeline tabs' `ws_events.active` and the activity timeline tabs'
`ws_activity.active`); if it were re-executed on every source change, that state would be dropped
and browser auto-refresh and the live timelines would silently stop working. It is imported by both the reloaded `src.server` (routes, in-place
updates on data changes, event streaming, refusal gates) and the stable `src.hmr_server` (full
reloads on file changes, reload outcomes), so a single instance survives reloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket


class ReloaderConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active.remove(websocket)

    async def reload(self) -> None:
        """Make every open tab reload itself: the source changed under it."""
        await self._send('{"reload": 1}')

    async def update(self) -> None:
        """Make every open tab fetch its page again and morph it in place: the data changed."""
        await self._send('{"update": 1}')

    async def _send(self, message: str) -> None:
        dead: list[WebSocket] = []
        for conn in self.active:
            try:
                await conn.send_text(message)
            except Exception:
                dead.append(conn)
        for conn in dead:
            self.active.remove(conn)


# Process-wide singleton. Must survive hot reloads, so it lives in this
# (reload-excluded) module rather than in the reloaded server module.
ws_reloader = ReloaderConnectionManager()


@dataclass
class EventStream:
    """One timeline tab: the workspace it watches and how many of that workspace's log events it has."""
    websocket: WebSocket
    workspace_id: str
    seen: int


class EventsConnectionManager:
    def __init__(self):
        self.active: list[EventStream] = []

    async def connect(self, websocket: WebSocket, workspace_id: str, seen: int):
        await websocket.accept()
        self.active.append(EventStream(websocket, workspace_id, seen))

    def disconnect(self, websocket: WebSocket):
        # Idempotent: a stream already dropped by a failed send is simply gone.
        self.active = [stream for stream in self.active if stream.websocket is not websocket]

    def watching(self, workspace_id: str) -> bool:
        return any(stream.workspace_id == workspace_id for stream in self.active)

    async def publish(self, workspace_id: str, events: list[dict[str, str]], timeline: dict[str, Any]):
        """Send each tab watching the workspace the events it has not seen, with the timeline."""
        dead: list[EventStream] = []
        for stream in list(self.active):
            if stream.workspace_id != workspace_id or stream.seen >= len(events):
                continue
            # Counted before the send is awaited, so an overlapping publish never repeats an event.
            unseen, stream.seen = events[stream.seen:], len(events)
            try:
                await stream.websocket.send_json({"events": unseen, "timeline": timeline})
            except Exception:
                dead.append(stream)
        for stream in dead:
            self.disconnect(stream.websocket)


# Process-wide singleton. Must survive hot reloads, so it lives in this (reload-excluded) module.
ws_events = EventsConnectionManager()


@dataclass
class ActivityStream:
    """One activity timeline tab: the workspace it watches and the page it shows, None for the whole workspace."""
    websocket: WebSocket
    workspace_id: str
    page_id: str | None


class ActivityConnectionManager:
    def __init__(self):
        self.active: list[ActivityStream] = []

    async def connect(self, websocket: WebSocket, workspace_id: str, page_id: str | None):
        await websocket.accept()
        self.active.append(ActivityStream(websocket, workspace_id, page_id))

    def disconnect(self, websocket: WebSocket):
        # Idempotent: a stream already dropped by a failed send is simply gone.
        self.active = [stream for stream in self.active if stream.websocket is not websocket]

    def watching(self, workspace_id: str) -> bool:
        return any(stream.workspace_id == workspace_id for stream in self.active)

    def scopes(self, workspace_id: str) -> list[str | None]:
        """Each page watched in the workspace once, None for the whole workspace, in connect order."""
        return list(dict.fromkeys(stream.page_id for stream in self.active if stream.workspace_id == workspace_id))

    async def publish(self, workspace_id: str, page_id: str | None, timeline: dict[str, Any]):
        """Send the rebuilt activity timeline to each tab showing that page of the workspace."""
        dead: list[ActivityStream] = []
        for stream in list(self.active):
            if stream.workspace_id != workspace_id or stream.page_id != page_id:
                continue
            try:
                await stream.websocket.send_json({"timeline": timeline})
            except Exception:
                dead.append(stream)
        for stream in dead:
            self.disconnect(stream.websocket)


# Process-wide singleton. Must survive hot reloads, so it lives in this (reload-excluded) module.
ws_activity = ActivityConnectionManager()


# Kept here so the gates of a rolled-back build still see it.
_reload_failure: str | None = None


def set_reload_failure(summary: str | None) -> None:
    """Record why the last reload failed, or clear it once a reload succeeds."""
    global _reload_failure
    _reload_failure = summary


def reload_failure() -> str | None:
    """Why the last reload failed, while no reload has succeeded since; otherwise None."""
    return _reload_failure
