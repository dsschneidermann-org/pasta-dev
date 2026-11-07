"""Unit tests for the dev server (src.hmr_server): reload-failure reporting, and the framework
internals the reload swap relies on.

The reload machinery as a whole needs a live uvicorn process, a file watcher and a real edit, so it
is exercised by hand against the running dev server rather than in this suite. What is pinned here
is what regressed silently: a failed re-exec that left no usable trace in the console, and the
fastmcp/mcp internals behind the mount swap and the list_changed notification, which a framework
upgrade can move without any error.
"""

import asyncio
import logging

import pytest
from fastmcp import FastMCP
from mcp.server.connection import Connection

import src.hmr_server as hmr_server
from src.hmr_server import _LoggingErrorFilter, _mount


@pytest.fixture
def swallow(caplog):
    """Run a reload failure through the filter hmr uses, capturing what reaches the dev console."""
    def _run(exc: BaseException):
        with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
            with _LoggingErrorFilter():
                raise exc
        return caplog.text
    return _run


def test_a_swallowed_reload_error_reaches_the_console_as_an_error(swallow):
    # hmr prints a failed re-exec through sys.excepthook and swallows it, which lands a bare
    # traceback between uvicorn's INFO lines - no level, no prefix, nothing a reader can scan for.
    text = swallow(ValueError("Invalid page-type declarations:\n- bug-report: bad setter"))
    assert "ERROR" in text
    assert "[HMR]" in text


def test_the_report_names_the_error_that_failed_the_reload(swallow):
    text = swallow(ValueError("Invalid page-type declarations:\n- bug-report: bad setter"))
    assert "Invalid page-type declarations" in text
    assert "bad setter" in text


def test_the_report_states_the_consequence_not_just_the_error(swallow):
    # The traceback alone never said what it cost: the reload did not take, so the modules loaded
    # before it are still the ones serving. That is the line the developer actually needs, and its
    # absence is why a 200 OK on the very next line read as normal.
    text = swallow(ValueError("boom"))
    assert "did not take" in text.lower() or "still serving" in text.lower()


def test_the_failure_is_still_swallowed_so_the_dev_server_survives(swallow):
    # Logging must not change hmr's contract: the error is reported, not re-raised. A raise here
    # would tear down the watcher and drop every live MCP session on a half-finished save.
    assert swallow(ValueError("boom")) is not None


def test_a_clean_reload_reports_nothing(caplog):
    # No error, no noise - the filter is invisible on the ordinary path.
    with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
        with _LoggingErrorFilter():
            pass
    assert caplog.text == ""


def test_a_mounted_server_is_served_through_the_proxy_until_unmounted():
    # The reload swap leans on a fastmcp internal: mount() appends one provider to the proxy's
    # `providers`, and removing that provider unmounts it. An upgrade that moves this fails here
    # rather than leaving the dev server serving a stale or doubled tool set.
    proxy, child = FastMCP("proxy"), FastMCP("child")

    @child.tool
    def ping() -> str:
        return "pong"

    async def tool_names() -> set[str]:
        return {tool.name for tool in await proxy.list_tools()}

    unmount = _mount(proxy, child)
    assert "ping" in asyncio.run(tool_names())
    unmount()
    assert "ping" not in asyncio.run(tool_names())


class _RecordingOutbound:
    """Stands in for a client's standalone stream, recording each notification sent down it."""

    def __init__(self):
        self.sent: list[str] = []

    async def notify(self, method, params, opts=None):
        self.sent.append(method)

    async def send_raw_request(self, method, params, opts=None):
        raise AssertionError("a reload sends notifications, never requests")


class _BrokenOutbound(_RecordingOutbound):
    async def notify(self, method, params, opts=None):
        raise RuntimeError("stream gone")


@pytest.fixture
def capturing():
    restore = hmr_server._capture_connections()
    try:
        yield
    finally:
        restore()
        hmr_server._live_connections.clear()


def test_a_connection_built_while_capturing_is_recorded(capturing):
    connection = Connection.for_loop(_RecordingOutbound())
    assert connection in hmr_server._live_connections


def test_a_connection_built_after_capture_stops_is_not_recorded():
    hmr_server._capture_connections()()
    connection = Connection.for_loop(_RecordingOutbound())
    assert connection not in hmr_server._live_connections


def test_a_reload_tells_each_live_connection_every_list_may_have_changed(capturing):
    outbound = _RecordingOutbound()
    connection = Connection.for_loop(outbound)  # held, so the weak set keeps it
    asyncio.run(hmr_server._notify_list_changed())
    assert connection in hmr_server._live_connections
    assert outbound.sent == ["notifications/tools/list_changed",
                             "notifications/resources/list_changed",
                             "notifications/prompts/list_changed"]


def test_one_broken_connection_does_not_stop_the_others_hearing_of_a_reload(capturing):
    # A client that vanished mid-reload must not cost every other client its refresh.
    broken, healthy = _BrokenOutbound(), _RecordingOutbound()
    connections = [Connection.for_loop(broken), Connection.for_loop(healthy)]
    asyncio.run(hmr_server._notify_list_changed())
    assert len(connections) == 2
    assert healthy.sent == ["notifications/tools/list_changed",
                            "notifications/resources/list_changed",
                            "notifications/prompts/list_changed"]
