"""Manual MCP streamable-HTTP probe for the pasta server.

Runs the full client handshake against a pasta MCP endpoint and prints the
status line, the interesting headers, and the decoded body of every exchange
verbatim. It is meant to be rerun at will while investigating server bugs (e.g.
the "StreamableHTTPSessionManager task group was not initialized" error) - a
failing step and *where* it fails are made obvious rather than swallowed.

Steps: initialize -> notifications/initialized -> tools/list -> tools/call(listWorkspaces).

Usage (server must already be running on the target host/port):
    uv run python scripts/mcp_probe.py                                 # default URL below
    uv run python scripts/mcp_probe.py http://localhost:8000/pasta/mcp
    uv run python scripts/mcp_probe.py http://localhost:8000/pasta/mcp/pasta

The URL is a positional arg so you can point it at candidate paths (the HMR
proxy and the real server can end up at different mount points).
"""

from __future__ import annotations

import json
import sys

import httpx

DEFAULT_URL = "http://localhost:8000/pasta/mcp"

# Any recent protocol version works - FastMCP negotiates down in the initialize
# result if it prefers another. This is just what the probe offers.
PROTOCOL_VERSION = "2025-06-18"

# Streamable HTTP responses may come back as JSON or as an SSE stream, so we must
# accept both on every request.
BASE_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def parse_body(response: httpx.Response):
    """Decode the JSON-RPC payload from a JSON or text/event-stream response.

    Returns a dict/list for JSON, a list of frames for SSE, the raw text if it
    is non-empty but not decodable, or None for an empty body.
    """
    content_type = response.headers.get("content-type", "")
    text = response.text

    if "text/event-stream" in content_type:
        frames = []
        for line in text.splitlines():
            if line.startswith("data:"):
                raw = line[len("data:") :].strip()
                if raw:
                    try:
                        frames.append(json.loads(raw))
                    except json.JSONDecodeError:
                        frames.append(raw)
        return frames

    if text.strip():
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return None


def show(label: str, response: httpx.Response):
    """Print one exchange (status, key headers, decoded body) and return the body."""
    print(f"\n=== {label} ===")
    print(f"HTTP {response.status_code} {response.reason_phrase}")
    for key in ("content-type", "mcp-session-id", "mcp-protocol-version"):
        if key in response.headers:
            print(f"  {key}: {response.headers[key]}")
    body = parse_body(response)
    print(json.dumps(body, indent=2, ensure_ascii=False) if body is not None else "(empty body)")
    return body


def rpc(request_id, method: str, params=None) -> dict:
    """Build a JSON-RPC message. Pass request_id=None for a notification (no id)."""
    message = {"jsonrpc": "2.0", "method": method}
    if request_id is not None:
        message["id"] = request_id
    if params is not None:
        message["params"] = params
    return message


def run(url: str) -> None:
    headers = dict(BASE_HEADERS)
    print(f"MCP endpoint: {url}")

    with httpx.Client(timeout=15.0) as client:
        # 1. initialize - this is where a missing/unrun MCP lifespan surfaces.
        init = client.post(
            url,
            headers=headers,
            json=rpc(
                1,
                "initialize",
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "mcp-probe", "version": "0.0.0"},
                },
            ),
        )
        show("initialize", init)

        if init.status_code >= 400:
            print("\ninitialize failed - stopping here (the rest of the handshake needs a session).")
            return

        # FastMCP hands back the session id in a response header; echo it on every
        # subsequent request.
        session_id = init.headers.get("mcp-session-id")
        if session_id:
            headers["mcp-session-id"] = session_id

        # 2. notifications/initialized - a notification (no id); server returns 202/empty.
        note = client.post(url, headers=headers, json=rpc(None, "notifications/initialized"))
        show("notifications/initialized", note)

        # 3. tools/list - confirms the mounted tool set is reachable through this endpoint.
        tools = client.post(url, headers=headers, json=rpc(2, "tools/list"))
        show("tools/list", tools)

        # 4. tools/call listWorkspaces - a real, side-effect-free tool round-trip.
        call = client.post(
            url,
            headers=headers,
            json=rpc(3, "tools/call", {"name": "listWorkspaces", "arguments": {}}),
        )
        show("tools/call listWorkspaces", call)

        # 5. tools/call nextActions - demonstrate page states.
        call = client.post(
            url,
            headers=headers,
            json=rpc(3, "tools/call", {"name": "describeMutations", "arguments": {}}),
        )
        show("tools/call describeMutations", call)

        # 5. tools/call nextActions - demonstrate page states.
        call = client.post(
            url,
            headers=headers,
            json=rpc(3, "tools/call", {"name": "nextActions", "arguments": {
                "workspaceId": "ws:mrteq0c5-238cf6",
                "pageId": "feature-brief:msar0xh2-b79823",
            }}),
        )
        show("tools/call nextActions", call)

def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    try:
        run(url)
    except httpx.ConnectError:
        print(f"\nCould not connect to {url} - is the server running on that host/port?")
        sys.exit(1)
    except httpx.RequestError as exc:
        print(f"\nRequest to {url} failed: {type(exc).__name__}: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
