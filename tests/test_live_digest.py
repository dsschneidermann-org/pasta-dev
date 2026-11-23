"""Unit tests for src.live_digest: when two sets of items digest alike and when they do not."""

from src.live_digest import items_digest

EVENTS = [{"at": "2026-11-23T10:00:00+00:00", "event": "created", "pageId": "p1"},
          {"at": "2026-11-23T10:01:00+00:00", "event": "status", "pageId": "p1"}]


def test_a_digest_is_sixteen_lowercase_hex_characters():
    digest = items_digest(EVENTS)
    assert len(digest) == 16 and digest == digest.lower()
    assert int(digest, 16) >= 0


def test_equal_items_give_the_same_digest():
    assert items_digest(EVENTS) == items_digest([dict(event) for event in EVENTS])
    assert items_digest([]) == items_digest([])


def test_adding_removing_changing_or_reordering_an_item_changes_the_digest():
    added = EVENTS + [{"at": "2026-11-23T10:02:00+00:00", "event": "archived", "pageId": "p1"}]
    changed = [EVENTS[0], {**EVENTS[1], "pageId": "p2"}]
    digests = {items_digest(EVENTS), items_digest(added), items_digest(EVENTS[:1]),
               items_digest(changed), items_digest(EVENTS[::-1]), items_digest([])}
    assert len(digests) == 6


def test_an_item_moved_from_one_list_of_a_view_to_the_other_changes_the_digest():
    entry = {"at": "2026-11-23T10:00:00+00:00", "kind": "call", "pageId": "p1"}
    assert items_digest([[entry], []]) != items_digest([[], [entry]])


def test_non_ascii_text_is_digested_as_its_characters():
    assert items_digest([{"title": "Café"}]) != items_digest([{"title": "Cafe"}])
