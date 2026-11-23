"""Unit tests for src.live_publish: what a round reads, builds and sends, how asks for rounds coalesce,
and how a failed round ends without reaching the caller."""

import asyncio
import logging
import threading

from src.live_publish import LivePublisher
from src.live_sockets import LiveConnectionManager


class _Tab:
    def __init__(self):
        self.sent = []

    async def accept(self):
        pass

    async def send_json(self, data):
        self.sent.append(data)


def _publisher(digests=("now",), release=None):
    """A publisher whose reads return these digests in turn, the last repeating, recording its reads and
    builds; a build waits on release when one is given."""
    reads, builds = [], []

    def read(workspace_id):
        reads.append(workspace_id)
        return digests[min(len(reads), len(digests)) - 1], ["item"]

    def build(workspace_id, items, scopes):
        builds.append(list(scopes))
        if release is not None:
            _ = release.wait(5)
        return {scope: {"scope": scope, "items": items} for scope in scopes}
    manager = LiveConnectionManager()
    return LivePublisher("check", manager, read, build), manager, reads, builds


async def _settle(publisher):
    while publisher.tasks:
        await asyncio.gather(*list(publisher.tasks))


def test_a_tab_drawn_from_the_current_items_is_sent_nothing_and_nothing_is_built():
    publisher, manager, reads, builds = _publisher()
    tab = _Tab()

    async def run():
        await manager.connect(tab, "ws:a", None, "now")
        publisher.schedule("ws:a")
        await _settle(publisher)
    asyncio.run(run())
    assert reads == ["ws:a"] and builds == [] and tab.sent == []


def test_each_tab_behind_is_sent_its_scope_s_payload_with_the_digest():
    publisher, manager, _, builds = _publisher()
    page_tab, index_tab, current = _Tab(), _Tab(), _Tab()

    async def run():
        await manager.connect(page_tab, "ws:a", "p", "")
        await manager.connect(index_tab, "ws:a", None, "old")
        await manager.connect(current, "ws:a", "q", "now")
        publisher.schedule("ws:a")
        await _settle(publisher)
    asyncio.run(run())
    assert builds == [["p", None]]
    assert page_tab.sent == [{"timeline": {"scope": "p", "items": ["item"]}, "digest": "now"}]
    assert index_tab.sent == [{"timeline": {"scope": None, "items": ["item"]}, "digest": "now"}]
    assert current.sent == []


def _burst(before_round, during_round):
    """Ask for rounds before the first starts and while it builds, the items changing meanwhile; return
    the reads, the builds and what the tab was sent."""
    release = threading.Event()
    publisher, manager, reads, builds = _publisher(digests=("first", "second"), release=release)
    tab = _Tab()

    async def run():
        await manager.connect(tab, "ws:a", None, "")
        for _ in range(before_round):
            publisher.schedule("ws:a")
        while not builds:
            await asyncio.sleep(0.01)              # the first round is building
        for _ in range(during_round):
            publisher.schedule("ws:a")
        release.set()
        await _settle(publisher)
    asyncio.run(run())
    return reads, builds, tab.sent


def test_asks_before_a_round_starts_share_it():
    reads, builds, sent = _burst(before_round=5, during_round=0)
    assert len(reads) == 1 and builds == [[None]]
    assert [message["digest"] for message in sent] == ["first"]


def test_asks_while_a_round_runs_cost_exactly_one_more_which_sends_what_changed_meanwhile():
    reads, builds, sent = _burst(before_round=1, during_round=4)
    assert len(reads) == 2 and builds == [[None], [None]]
    assert [message["digest"] for message in sent] == ["first", "second"]


def test_nothing_is_read_while_no_tab_watches():
    publisher, _, reads, _ = _publisher()

    async def run():
        publisher.schedule("ws:a")
        return set(publisher.tasks)
    assert asyncio.run(run()) == set()
    assert reads == []


def test_a_failed_round_is_logged_never_raised_and_the_next_ask_runs_a_fresh_one(caplog):
    manager = LiveConnectionManager()
    attempts = []

    def read(workspace_id):
        attempts.append(workspace_id)
        if len(attempts) == 1:
            raise RuntimeError("disk gone")
        return "now", []
    publisher = LivePublisher("check", manager, read, lambda workspace_id, items, scopes: {scope: {} for scope in scopes})
    tab = _Tab()

    async def run():
        await manager.connect(tab, "ws:a", None, "")
        publisher.schedule("ws:a")
        await _settle(publisher)
        publisher.schedule("ws:a")
        await _settle(publisher)
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        asyncio.run(run())
    assert "[check] could not publish the ws:a live update" in caplog.text
    assert tab.sent == [{"timeline": {}, "digest": "now"}]
