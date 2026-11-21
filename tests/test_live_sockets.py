"""Unit tests for the live browser sockets (src.live_sockets): what the reloader tells every tab,
which tabs a timeline publish reaches, which events each is sent, and how a dead or closed tab
leaves."""

import ast
import asyncio
from pathlib import Path

from src.live_sockets import EventsConnectionManager, ReloaderConnectionManager

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
