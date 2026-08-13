"""Tests for the Project Gutenberg (Gutendex) client. HTTP is mocked
throughout -- these must never make a real network call, so they run
offline and deterministically.
"""
import urllib.error

from pd_verification import gutenberg


def test_get_wraps_url_error(monkeypatch):
    def _raise(*a, **k):
        raise urllib.error.URLError("simulated network failure")
    monkeypatch.setattr(gutenberg.urllib.request, "urlopen", _raise)
    try:
        gutenberg._get("https://gutendex.com/books/1")
        assert False, "expected GutenbergLookupError"
    except gutenberg.GutenbergLookupError:
        pass


def test_get_wraps_bare_oserror_not_just_urllib_types(monkeypatch):
    # Regression test for ISSUE-10 (branch-audit-2026-08-12.md): on Python
    # 3.9, socket.timeout is an OSError subclass but NOT a TimeoutError
    # subclass (that alias was only added in 3.10). A handler written as
    # `except (URLError, HTTPError, TimeoutError)` therefore let a real
    # timeout on 3.9 escape uncaught and 500 the /producers route. This
    # simulates that gap directly with a bare OSError -- neither a URLError,
    # an HTTPError, nor a TimeoutError -- which must still be caught.
    def _raise(*a, **k):
        raise OSError("simulated socket.timeout-shaped failure, pre-3.10 style")
    monkeypatch.setattr(gutenberg.urllib.request, "urlopen", _raise)
    try:
        gutenberg._get("https://gutendex.com/books/1")
        assert False, "expected GutenbergLookupError -- bare OSError must not escape"
    except gutenberg.GutenbergLookupError:
        pass


def test_get_success_returns_parsed_json(monkeypatch):
    class _FakeResponse:
        def read(self):
            return b'{"ok": true}'
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
    monkeypatch.setattr(gutenberg.urllib.request, "urlopen", lambda *a, **k: _FakeResponse())
    assert gutenberg._get("https://gutendex.com/books/1") == {"ok": True}
