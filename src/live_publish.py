"""Publishing a live view: a background round per workspace that brings the view's open tabs up to
date. A round reads the view's items and sends a rebuilt payload only to the tabs not yet drawn from
them, so a tab rendered from the current items is sent nothing, and no caller waits for a round."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from .live_sockets import LiveConnectionManager, Scope

logger = logging.getLogger("uvicorn.error")


class LivePublisher[Items]:
    def __init__(self, name: str, manager: LiveConnectionManager,
                 read: Callable[[str], tuple[str, Items]],
                 build: Callable[[str, Items, list[Scope]], dict[Scope, dict[str, Any]]]) -> None:
        self._name: str = name     # labels a failed round in the log
        self._manager: LiveConnectionManager = manager
        # (the items' digest, the items); blocking, so it runs in a thread
        self._read: Callable[[str], tuple[str, Items]] = read
        # one payload per scope from the items; blocking, so it runs in a thread
        self._build: Callable[[str, Items, list[Scope]], dict[Scope, dict[str, Any]]] = build
        self.tasks: set[asyncio.Task[None]] = set()   # strong references until each task finishes
        self._running: set[str] = set()
        self._stale: set[str] = set()

    def schedule(self, workspace_id: str) -> None:
        """Bring the tabs watching the workspace up to date without waiting. An ask while a round runs
        makes it go round once more."""
        if not self._manager.watching(workspace_id):
            return
        if workspace_id in self._running:
            self._stale.add(workspace_id)
            return
        self._running.add(workspace_id)
        task = asyncio.get_running_loop().create_task(self._run(workspace_id))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _run(self, workspace_id: str) -> None:
        """A round follows a call that has already returned, so a failure is logged, never raised."""
        try:
            while True:
                self._stale.discard(workspace_id)
                if not self._manager.watching(workspace_id):
                    return
                digest, items = await asyncio.to_thread(self._read, workspace_id)
                scopes = self._manager.stale_scopes(workspace_id, digest)
                if scopes:
                    payloads = await asyncio.to_thread(self._build, workspace_id, items, scopes)
                    for scope in scopes:
                        await self._manager.publish(workspace_id, scope, digest, payloads[scope])
                if workspace_id not in self._stale:
                    return
        except Exception:
            logger.warning("[%s] could not publish the %s live update", self._name, workspace_id, exc_info=True)
        finally:
            self._running.discard(workspace_id)
