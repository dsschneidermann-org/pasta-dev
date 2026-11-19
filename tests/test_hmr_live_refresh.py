"""Unit tests for the timeline's events connection manager (src.hmr_live_refresh): which tabs a
publish reaches, which events each is sent, and how a dead or closed tab leaves."""

import asyncio

from src.hmr_live_refresh import EventsConnectionManager

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
