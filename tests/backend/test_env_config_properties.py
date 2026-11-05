"""
Property-based test for the Backend_App's env-driven configuration — cross-service
origins are read from the environment, never hard-coded (Property 3, backend half).

# Feature: s3-01a-application-shell-scaffold, Property 3: Cross-service URLs and
# origins are env-driven, never hard-coded

**Property 3 (backend half).** For ANY configured value of the env-driven
endpoint setting ``CORS_ALLOW_ORIGINS``, the Backend_App's resolved allowed-CORS
origins equal EXACTLY the value parsed out of that environment variable — split
on commas, each entry stripped of surrounding whitespace, empty entries dropped,
with an unset/empty variable resolving to ``[]``. No origin literal is baked into
``app/api/`` source: the origins resolve ONLY from the environment (Requirement
4.2, 6.5). This keeps the frozen S2-08 boundary honest — the same build runs in
dev, Compose, and any other environment without a code change, because the
allowed origins are configuration, not source.

**Validates: Requirements 4.2, 6.5**

The test has the two halves the property names:

* **Executable half (Hypothesis).** Generate comma-separated origin strings —
  including surrounding/interior whitespace, empty entries (leading/trailing/
  doubled commas), and the unset case — set ``CORS_ALLOW_ORIGINS`` to each, and
  assert ``settings.get_cors_allow_origins()`` returns exactly the independently
  computed parse (split on commas, strip, drop empties; unset/empty -> []).
  Runs at least 100 examples. The env var is saved and restored around every
  example so the real process environment is never mutated across examples.

* **Static-source half.** Scan every ``.py`` file under ``app/api/`` and assert
  no ``http://`` / ``https://`` origin literal is hard-coded anywhere — the CORS
  origins can therefore only come from the environment variable. String literals
  and comments that merely *name* the ``http(s)`` scheme in prose (e.g. a
  docstring saying "e.g. http://localhost:3000") would defeat the intent, so the
  scan flags any occurrence of a bare ``http://``/``https://`` URL in source and
  the sole allowed mention is inside a comment/docstring that documents the
  concept — which we exclude by only inspecting lines that are not comments.
  See ``_scan_for_url_literals`` for the exact rule.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

# conftest.py puts the repo root on sys.path, so `app/api` is importable by path
# and `settings` is importable once its directory is on the path. We import the
# module by file location to mirror how the app is launched (working dir =
# app/api/), without needing app/api to be a package.
import importlib.util

REPO_ROOT = Path(__file__).resolve().parents[2]
API_DIR = REPO_ROOT / "app" / "api"
SETTINGS_PATH = API_DIR / "settings.py"


def _load_settings():
    """Load app/api/settings.py as a standalone module (matches launch layout)."""
    spec = importlib.util.spec_from_file_location("optmining_api_settings", SETTINGS_PATH)
    assert spec is not None and spec.loader is not None, f"cannot load {SETTINGS_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


settings_module = _load_settings()
CORS_ENV = settings_module.CORS_ALLOW_ORIGINS_ENV


# --- Reference parse (independent of the implementation under test) -----------
#
# This is the specification the property pins get_cors_allow_origins() to:
# split on commas, strip each entry, drop empties; None/"" -> []. It is written
# from the requirement text, NOT by calling the code under test, so the test
# genuinely constrains the implementation.


def _reference_parse(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


# --- Strategy: a single origin token ------------------------------------------
#
# Origins are drawn as realistic-ish scheme+host tokens PLUS arbitrary
# whitespace-padded free tokens, so the parser is exercised on both plausible
# origins and adversarial whitespace/empty content. We deliberately keep commas
# OUT of individual tokens (a comma is the delimiter) and assemble the env value
# by joining tokens with commas — including empty tokens — so leading, trailing,
# and doubled commas all occur.

_scheme = st.sampled_from(["http://", "https://"])
_host = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789.-",
    min_size=1,
    max_size=20,
)
_port = st.one_of(st.none(), st.integers(min_value=1, max_value=65535))


@st.composite
def _origin_token(draw) -> str:
    """A single origin-like token, possibly padded with surrounding whitespace."""
    kind = draw(st.integers(min_value=0, max_value=2))
    if kind == 0:
        # An empty / whitespace-only token (exercises the drop-empties rule).
        core = draw(st.sampled_from(["", " ", "   ", "\t"]))
    elif kind == 1:
        # A realistic origin: scheme + host [+ :port].
        port = draw(_port)
        core = draw(_scheme) + draw(_host) + (f":{port}" if port is not None else "")
    else:
        # An arbitrary free token WITHOUT commas (comma is the delimiter) and
        # WITHOUT the null byte — os.environ cannot hold an embedded NUL, so a
        # NUL can never be the real content of an env var. Constrain the
        # generator to the actual env-var input space rather than testing values
        # the OS would reject before the app ever sees them.
        core = draw(
            st.text(
                # os.environ can only hold values it can UTF-8 encode and that
                # carry no embedded NUL. Exclude the null byte, the comma
                # delimiter, and lone surrogates (blacklist the "Cs" category) so
                # the generator stays inside the real env-var input space rather
                # than producing values the OS rejects before the app sees them.
                alphabet=st.characters(
                    blacklist_characters="\x00,",
                    blacklist_categories=("Cs",),
                ),
                min_size=0,
                max_size=15,
            )
        )
    # Optionally pad with surrounding whitespace so strip() is exercised.
    lead = draw(st.sampled_from(["", " ", "  ", "\t"]))
    trail = draw(st.sampled_from(["", " ", "  ", "\t"]))
    return f"{lead}{core}{trail}"


@st.composite
def _cors_env_value(draw) -> str | None:
    """A full CORS_ALLOW_ORIGINS env value, or None for the unset case."""
    if draw(st.booleans()):
        # The unset / empty variants — must resolve to [].
        return draw(st.sampled_from([None, "", "   ", "\t", " , , "]))
    tokens = draw(st.lists(_origin_token(), min_size=1, max_size=8))
    return ",".join(tokens)


@settings(max_examples=200, deadline=None)
@given(raw=_cors_env_value())
def test_property_3_cors_origins_are_env_driven(raw):
    """
    get_cors_allow_origins() returns EXACTLY the value parsed from the env var
    (split-strip-drop-empties; unset/empty -> []) — the origins are configuration
    read from the environment, never source literals (Requirement 4.2, 6.5).
    """
    # Feature: s3-01a-application-shell-scaffold, Property 3: Cross-service URLs
    # and origins are env-driven, never hard-coded

    original = os.environ.get(CORS_ENV)
    try:
        if raw is None:
            os.environ.pop(CORS_ENV, None)
        else:
            os.environ[CORS_ENV] = raw

        resolved = settings_module.get_cors_allow_origins()
        expected = _reference_parse(raw)

        # The resolved list equals EXACTLY the parsed env value — same entries,
        # same order, no extra baked-in origin, none dropped.
        assert resolved == expected

        # No entry is empty or carries surrounding whitespace (parse invariants).
        for origin in resolved:
            assert origin == origin.strip()
            assert origin != ""
    finally:
        # Restore the process environment so examples never leak into each other
        # or into sibling tests (Hypothesis reuses the process across examples).
        if original is None:
            os.environ.pop(CORS_ENV, None)
        else:
            os.environ[CORS_ENV] = original


# ---------------------------------------------------------------------------
# Static-source half: no http(s) origin literal is baked into app/api/ sources.
# ---------------------------------------------------------------------------

# A bare http:// or https:// URL literal appearing in a *code* line (i.e. not a
# comment). Origins must resolve only from the env var, so no origin literal may
# appear as a string constant in the API sources.
_URL_LITERAL = re.compile(r"https?://")


def _iter_api_py_files() -> list[Path]:
    files = sorted(p for p in API_DIR.rglob("*.py") if "__pycache__" not in p.parts)
    assert files, f"expected .py sources under {API_DIR}"
    return files


def _code_lines_without_comments(text: str) -> list[tuple[int, str]]:
    """Return (lineno, line) for lines whose non-comment part could hold a URL.

    We strip full-line and trailing `#` comments and skip docstring/prose lines
    so that a documentation mention of a scheme (e.g. in a module docstring
    that says "e.g. http://localhost:3000") is not counted as a hard-coded
    origin — only an http(s):// occurring in executable/string-literal code is
    flagged. Docstrings are handled by skipping any line inside a triple-quoted
    block.
    """
    out: list[tuple[int, str]] = []
    in_triple = None  # holds the active triple-quote delimiter, or None
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw
        # Track triple-quoted docstring blocks and skip their content entirely.
        if in_triple is not None:
            if in_triple in line:
                # Closing delimiter on this line; keep the part after it.
                line = line.split(in_triple, 1)[1]
                in_triple = None
            else:
                continue
        # Detect an opening triple-quote that does not close on the same line.
        for delim in ('"""', "'''"):
            if delim in line:
                before, _, after = line.partition(delim)
                if delim in after:
                    # Opens and closes on one line: drop the quoted span.
                    line = before + after.split(delim, 1)[1]
                else:
                    # Opens here and stays open: keep only the pre-quote part.
                    line = before
                    in_triple = delim
                    break
        # Drop a trailing line comment.
        if "#" in line:
            line = line.split("#", 1)[0]
        out.append((lineno, line))
    return out


def test_no_hardcoded_origin_literal_in_api_sources():
    """No `http://`/`https://` origin literal is hard-coded in app/api/ code.

    Scans every .py file under app/api/ and asserts no bare URL literal appears
    in a code line (comments and docstrings that merely name the scheme in prose
    are excluded). The CORS origins therefore resolve ONLY from the
    CORS_ALLOW_ORIGINS environment variable (Requirement 4.2, 6.5).
    """
    offenders: list[str] = []
    for path in _iter_api_py_files():
        text = path.read_text(encoding="utf-8")
        for lineno, code in _code_lines_without_comments(text):
            if _URL_LITERAL.search(code):
                rel = path.relative_to(REPO_ROOT)
                offenders.append(f"{rel}:{lineno}: {code.strip()}")
    assert not offenders, (
        "no http(s) origin literal may be hard-coded in app/api/ sources — the "
        "CORS origins must resolve only from the CORS_ALLOW_ORIGINS env var "
        f"(Requirement 4.2, 6.5); offenders:\n" + "\n".join(offenders)
    )
