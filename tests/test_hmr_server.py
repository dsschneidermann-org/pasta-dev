"""Unit tests for the dev server's reporting surfaces (src.hmr_server).

Two of them: the reload-failure filter, and the request logging middleware. The reload machinery
itself needs a live uvicorn process, a file watcher and a real edit, so it is exercised by hand
against the running dev server rather than in this suite; what is pinned here are the parts that
fail silently - a failed re-exec that left no usable trace in the console, and a failed response
that was never logged (or was logged with a credential in it).
"""

import asyncio
import logging

import pytest

from src.hmr_server import LoggingMiddleware, _LoggingErrorFilter


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


# --- Request logging -------------------------------------------------------------------
_PATH = "/ws:abc/page/p1/status"


def _responder(status: int):
    """A bare ASGI app that answers with `status` and nothing else."""
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": status, "headers": []})
        await send({"type": "http.response.body", "body": b""})
    return app


async def _raiser(scope, receive, send):
    """Stands in for `fastapi_dispatch` when a failed reload left no app to serve."""
    raise RuntimeError("reload left no app to serve")


def _drive(app, body: bytes, client):
    """Push one request through LoggingMiddleware; return (status or None, exception or None)."""
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
        "scheme": "http", "path": _PATH, "raw_path": _PATH.encode(), "query_string": b"",
        "root_path": "", "server": ("testserver", 8000), "client": client,
        "headers": [(b"host", b"testserver"), (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode())],
    }
    sent = []
    pending = [{"type": "http.request", "body": body, "more_body": False}]

    async def receive():
        # The body once, then the disconnect a real server sends after it - which is what
        # BaseHTTPMiddleware expects to see next once it has cached the body.
        return pending.pop(0) if pending else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    async def run():
        try:
            await LoggingMiddleware(app)(scope, receive, send)
        except Exception as exc:
            return exc
        return None

    raised = asyncio.run(run())
    return next((m["status"] for m in sent if m["type"] == "http.response.start"), None), raised


@pytest.fixture
def logged(caplog):
    """Drive one request through the middleware, capturing what reaches the dev console."""
    def _run(app, body: bytes = b"", client=("10.0.0.7", 51234)):
        with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
            status, raised = _drive(app, body, client)
        return status, raised, caplog.text
    return _run


def test_a_failed_response_is_logged_with_the_request_that_caused_it(logged):
    status, _, text = logged(_responder(404), body=b'{"status": "done"}')
    assert status == 404
    assert "404" in text
    assert _PATH in text
    assert "10.0.0.7" in text


def test_a_successful_response_is_not_logged(logged):
    # The middleware is invisible on the ordinary path; every 2xx logging a line would bury the
    # failures it exists to surface.
    status, _, text = logged(_responder(200), body=b'{"status": "done"}')
    assert status == 200
    assert text == ""


def test_credentials_in_the_body_do_not_reach_the_log(logged):
    # Bodies are logged only on failure, and a 401 body is exactly where a credential sits - so
    # unredacted, this would single out the requests most likely to be carrying one.
    _, _, text = logged(_responder(401), body=b'{"user": "dennis", "password": "hunter2"}')
    assert "hunter2" not in text
    assert "dennis" in text  # the rest of the body still has to be there to debug from


def test_redaction_reaches_keys_nested_in_the_body(logged):
    # JSON-RPC buries its arguments under "params", so a top-level-only sweep would miss them.
    _, _, text = logged(_responder(422), body=b'{"params": {"api_key": "sk-live-1", "page": "p1"}}')
    assert "sk-live-1" not in text
    assert "p1" in text


def test_a_request_without_a_peer_address_is_still_served(logged):
    # Some transports leave `client` out of the scope (a unix socket has no peername). Reading
    # `.host` off that None failed the request before it ever reached the app, which took the
    # response down over a detail only the log cared about.
    status, raised, _ = logged(_responder(200), client=None)
    assert status == 200
    assert raised is None


def test_an_error_raised_before_any_response_is_still_logged(logged):
    # The reload-failure path: `fastapi_dispatch` raises, so no status ever comes back and a
    # status check alone logs nothing - losing the one 500 most worth reading.
    _, raised, text = logged(_raiser)
    assert isinstance(raised, RuntimeError)  # re-raised, so uvicorn still prints the traceback
    assert "ERROR" in text
    assert _PATH in text
