"""The source link: a pure mapping from a git remote URL to the web page it names, and the thin
reader that asks git for the checkout's remote."""

import subprocess

import pytest

from src.source_link import SourceLink, read_remote_url, to_source_link


def test_source_link_maps_an_scp_like_remote_to_https():
    assert to_source_link("git@github.com:dsschneidermann-org/pasta-dev.git") == SourceLink(
        href="https://github.com/dsschneidermann-org/pasta-dev",
        text="github.com/dsschneidermann-org/pasta-dev")


def test_source_link_keeps_an_https_remote():
    assert to_source_link("https://github.com/dsschneidermann/pasta\n") == SourceLink(
        href="https://github.com/dsschneidermann/pasta", text="github.com/dsschneidermann/pasta")


def test_source_link_strips_credentials():
    link = to_source_link("https://user:secret@example.com/a/b.git")
    assert link == SourceLink(href="https://example.com/a/b", text="example.com/a/b")


def test_source_link_maps_an_ssh_url_to_https_without_its_port():
    assert to_source_link("ssh://git@example.com:2222/a/b.git") == SourceLink(
        href="https://example.com/a/b", text="example.com/a/b")


def test_source_link_keeps_an_http_port():
    assert to_source_link("http://example.com:8080/a/b/") == SourceLink(
        href="http://example.com:8080/a/b", text="example.com:8080/a/b")


@pytest.mark.parametrize("remote_url", [
    None, "", "   ", "origin", "../pasta", "/srv/git/pasta.git", "C:/Repos/pasta",
    "C:\\Repos\\pasta", "file:///srv/pasta.git", "git://example.com/a/b.git",
    "https://example.com/", "https://example.com:notaport/a/b", "https://[::1]/a/b",
])
def test_source_link_is_none_without_a_web_page(remote_url):
    assert to_source_link(remote_url) is None


def _git(*args):
    subprocess.run(["git", *args], check=True, capture_output=True)


def test_read_remote_url_reads_the_checkouts_remote(tmp_path):
    _git("init", "-q", str(tmp_path))
    _git("-C", str(tmp_path), "remote", "add", "origin", "git@example.com:o/r.git")
    assert read_remote_url(tmp_path) == "git@example.com:o/r.git"


def test_read_remote_url_is_none_in_a_checkout_without_a_remote(tmp_path):
    _git("init", "-q", str(tmp_path))
    assert read_remote_url(tmp_path) is None


def test_read_remote_url_is_none_outside_a_checkout(tmp_path, monkeypatch):
    # Stop git's upward search at tmp_path, so an enclosing checkout cannot answer for it.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert read_remote_url(tmp_path) is None


def test_read_remote_url_is_none_for_a_missing_directory(tmp_path):
    assert read_remote_url(tmp_path / "missing") is None
