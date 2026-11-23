"""Unit tests for the live browser sockets (src.live_sockets): what the reloader tells every tab,
which tabs a timeline publish reaches, which events each is sent, and how a dead or closed tab
leaves."""

import ast
import asyncio
from pathlib import Path

from src.live_sockets import (ActivityConnectionManager, EventsConnectionManager, LiveConnectionManager,
                              ReloaderConnectionManager)

TIMELINE = {"duration": 1.0, "lines": []}


class FakeSocket:
    def __init__(self):
        self.accepted = False
        self.dead = False
        self.sent: list[dict] = []

    async def accept(self):
        self.accepted = True

    async def send_json(self, data):
        if self.dead:
            raise RuntimeError("the tab is gone")
        self.sent.append(data)


def _events(count: int) -> list[dict[str, str]]:
    return [{"at": f"2026-11-19T10:0{index}:00+00:00", "event": "created", "pageId": f"p{index}"}
            for index in range(count)]


def _connected(manager: EventsConnectionManager, workspace_id: str, seen: int) -> FakeSocket:
    socket = FakeSocket()
    asyncio.run(manager.connect(socket, workspace_id, seen))  # pyright: ignore[reportArgumentType]
    assert socket.accepted
    return socket


def test_publish_sends_each_tab_only_the_events_it_has_not_seen():
    manager = EventsConnectionManager()
    behind, current = _connected(manager, "ws:a", 1), _connected(manager, "ws:a", 3)
    events = _events(3)
    asyncio.run(manager.publish("ws:a", events, TIMELINE))
    assert behind.sent == [{"events": events[1:], "timeline": TIMELINE}]
    assert current.sent == []

    asyncio.run(manager.publish("ws:a", events, TIMELINE))     # nothing new since
    assert len(behind.sent) == 1


def test_publish_reaches_only_tabs_watching_that_workspace():
    manager = EventsConnectionManager()
    other = _connected(manager, "ws:b", 0)
    asyncio.run(manager.publish("ws:a", _events(2), TIMELINE))
    assert other.sent == []


def test_a_tab_whose_send_fails_is_dropped():
    manager = EventsConnectionManager()
    socket = _connected(manager, "ws:a", 0)
    socket.dead = True
    asyncio.run(manager.publish("ws:a", _events(1), TIMELINE))
    assert manager.active == []
    assert not manager.watching("ws:a")


def test_disconnect_removes_a_tab_and_is_idempotent():
    manager = EventsConnectionManager()
    socket = _connected(manager, "ws:a", 0)
    assert manager.watching("ws:a") and not manager.watching("ws:b")
    manager.disconnect(socket)  # pyright: ignore[reportArgumentType]
    manager.disconnect(socket)  # pyright: ignore[reportArgumentType]
    assert manager.active == []
    assert not manager.watching("ws:a")


def _watching(manager: ActivityConnectionManager, workspace_id: str, page_id: str | None) -> FakeSocket:
    socket = FakeSocket()
    asyncio.run(manager.connect(socket, workspace_id, page_id))  # pyright: ignore[reportArgumentType]
    assert socket.accepted
    return socket


def test_an_activity_publish_reaches_only_the_tabs_showing_that_page_of_that_workspace():
    manager = ActivityConnectionManager()
    page_tab, index_tab, other = (_watching(manager, "ws:a", "p"), _watching(manager, "ws:a", None),
                                  _watching(manager, "ws:b", "p"))
    asyncio.run(manager.publish("ws:a", "p", TIMELINE))
    assert page_tab.sent == [{"timeline": TIMELINE}]
    assert index_tab.sent == [] and other.sent == []


def test_activity_scopes_are_each_watched_page_once_in_connect_order():
    manager = ActivityConnectionManager()
    for page_id in ("p", None, "p", "q"):
        _ = _watching(manager, "ws:a", page_id)
    assert manager.scopes("ws:a") == ["p", None, "q"]
    assert manager.watching("ws:a") and not manager.watching("ws:c")


def test_an_activity_tab_whose_send_fails_is_dropped_and_disconnect_is_idempotent():
    manager = ActivityConnectionManager()
    gone, kept = _watching(manager, "ws:a", None), _watching(manager, "ws:a", None)
    gone.dead = True
    asyncio.run(manager.publish("ws:a", None, TIMELINE))
    assert [stream.websocket for stream in manager.active] == [kept]
    manager.disconnect(gone)  # pyright: ignore[reportArgumentType]
    manager.disconnect(kept)  # pyright: ignore[reportArgumentType]
    assert manager.active == []


def _live(manager: LiveConnectionManager, workspace_id: str, scope: str | None, digest: str) -> FakeSocket:
    socket = FakeSocket()
    asyncio.run(manager.connect(socket, workspace_id, scope, digest))  # pyright: ignore[reportArgumentType]
    assert socket.accepted
    return socket


def test_a_live_publish_reaches_only_the_tabs_of_that_scope_not_drawn_from_its_items():
    manager = LiveConnectionManager()
    behind, current = _live(manager, "ws:a", "p", "old"), _live(manager, "ws:a", "p", "new")
    index_tab, other = _live(manager, "ws:a", None, "old"), _live(manager, "ws:b", "p", "old")
    asyncio.run(manager.publish("ws:a", "p", "new", TIMELINE))
    assert behind.sent == [{"timeline": TIMELINE, "digest": "new"}]
    assert current.sent == [] and index_tab.sent == [] and other.sent == []

    asyncio.run(manager.publish("ws:a", "p", "new", TIMELINE))     # the tab is drawn from these items now
    assert len(behind.sent) == 1


def test_stale_scopes_are_each_scope_with_a_tab_behind_once_in_connect_order():
    manager = LiveConnectionManager()
    for scope, digest in (("p", "old"), (None, "old"), ("p", "old"), ("q", "new"), ("r", "")):
        _ = _live(manager, "ws:a", scope, digest)
    _ = _live(manager, "ws:b", "s", "old")
    assert manager.stale_scopes("ws:a", "new") == ["p", None, "r"]
    assert manager.stale_scopes("ws:c", "new") == []
    assert manager.watching("ws:a") and not manager.watching("ws:c")


def test_a_live_tab_whose_send_fails_is_dropped_and_disconnect_is_idempotent():
    manager = LiveConnectionManager()
    gone, kept = _live(manager, "ws:a", None, "old"), _live(manager, "ws:a", None, "old")
    gone.dead = True
    asyncio.run(manager.publish("ws:a", None, "new", TIMELINE))
    assert [stream.websocket for stream in manager.active] == [kept]
    manager.disconnect(gone)  # pyright: ignore[reportArgumentType]
    manager.disconnect(kept)  # pyright: ignore[reportArgumentType]
    manager.disconnect(kept)  # pyright: ignore[reportArgumentType]
    assert manager.active == [] and not manager.watching("ws:a")


class TextSocket:
    def __init__(self, dead: bool = False):
        self.dead = dead
        self.sent: list[str] = []

    async def accept(self):
        pass

    async def send_text(self, data: str):
        if self.dead:
            raise RuntimeError("the tab is gone")
        self.sent.append(data)


def _reloader_with(*sockets: TextSocket) -> ReloaderConnectionManager:
    manager = ReloaderConnectionManager()
    for socket in sockets:
        asyncio.run(manager.connect(socket))  # pyright: ignore[reportArgumentType]
    return manager


def test_reload_tells_every_tab_to_reload_itself():
    first, second = TextSocket(), TextSocket()
    asyncio.run(_reloader_with(first, second).reload())
    assert first.sent == second.sent == ['{"reload": 1}']


def test_update_tells_every_tab_to_update_in_place():
    first, second = TextSocket(), TextSocket()
    asyncio.run(_reloader_with(first, second).update())
    assert first.sent == second.sent == ['{"update": 1}']


def test_a_tab_that_is_gone_is_dropped_and_the_others_still_hear():
    gone, live = TextSocket(dead=True), TextSocket()
    manager = _reloader_with(gone, live)
    asyncio.run(manager.update())
    asyncio.run(manager.reload())
    assert manager.active == [live]
    assert live.sent == ['{"update": 1}', '{"reload": 1}']


SRC = Path(__file__).resolve().parent.parent / "src"


def _reloader_sends(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.attr for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
            and node.value.id == "ws_reloader" and node.attr in {"reload", "update"}}


def test_only_the_dev_server_reloads_tabs_and_only_data_changes_update_them():
    senders = {path.name: sends for path in SRC.rglob("*.py") if (sends := _reloader_sends(path))}
    assert senders == {"hmr_server.py": {"reload"}, "server.py": {"update"}}
