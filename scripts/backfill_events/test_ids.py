"""Unit tests for reading the creation instant back out of an id (src.ids)."""

import time

import pytest

from src.ids import id_time, new_id


def test_id_time_decodes_a_prefixed_id_and_a_bare_token():
    assert id_time("ws:mrteq0c5-238cf6") == 1784562980.405
    assert id_time("mrteq0c5-238cf6") == 1784562980.405


def test_id_time_round_trips_a_created_id():
    assert id_time(new_id("x")) == pytest.approx(time.time(), abs=5)


@pytest.mark.parametrize("identifier", ["page:NOT-base36", "x:", "", "page:-abc"])
def test_id_time_is_none_without_a_base36_timestamp(identifier):
    assert id_time(identifier) is None
