"""The browsable source link of the git checkout the server runs from.

Pasta is AGPL-3.0, so the web UI points its users at the source of the instance serving them.
"""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
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


def read_remote_url(repo_dir: Path) -> str | None:
    """The URL of the current branch's remote, else `origin`, in the checkout at `repo_dir`.

    None whenever git cannot say: no git, no checkout, no remote.
    """
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--get-url"],
            cwd=repo_dir, capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None
