"""The browsable source link of the git checkout the server runs from.

Pasta is AGPL-3.0, so the web UI points its users at the source of the instance serving them.
"""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

# scp-like `[user@]host:path`. A host of two or more characters keeps a Windows drive path out.
_SCP_LIKE = re.compile(r"^(?:[^@/:]+@)?([^@/:]{2,}):(.+)$")


@dataclass(frozen=True)
class SourceLink:
    href: str
    text: str


def source_link(remote_url: str | None) -> SourceLink | None:
    """The web page a git remote URL names, or None when it names none. Credentials never survive."""
    remote = (remote_url or "").strip()
    if remote.startswith(("http://", "https://", "ssh://")):
        parts = urlsplit(remote)
        try:
            port = parts.port
        except ValueError:
            return None
        # An SSH port says nothing about where the web page is served.
        if parts.scheme == "ssh":
            return _link("https", parts.hostname, None, parts.path)
        return _link(parts.scheme, parts.hostname, port, parts.path)
    if "://" in remote:
        return None
    match = _SCP_LIKE.match(remote)
    if match is None:
        return None
    return _link("https", match.group(1), None, match.group(2))


def _link(scheme: str, host: str | None, port: int | None, path: str) -> SourceLink | None:
    path = path.strip("/").removesuffix(".git").rstrip("/")
    if not host or ":" in host or not path:
        return None
    netloc = f"{host}:{port}" if port is not None else host
    href = f"{scheme}://{netloc}/{path}"
    return SourceLink(href=href, text=href.partition("://")[2])
