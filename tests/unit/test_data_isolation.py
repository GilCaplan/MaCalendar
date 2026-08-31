"""No test may touch ~/.assistant_tools.

That directory holds the real calendar, the command memory the parser learns
from, the hand-curated vocabulary and the event categories. A test script with
no isolation once ran `DELETE FROM events` against it and emptied the real
calendar — 657 events, unrecoverable.

Two guards, both checked here: every runnable test script isolates its stores
before importing `assistant`, and `CalendarDB` refuses to open the real file
from a test run even if one doesn't.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# Scripts you can run directly that drive the pipeline or the stores. Each must
# call tests.isolation.isolate() before importing anything from `assistant`.
RUNNABLE = [
    "tests/test_ollama_parser.py",
    "tests/test_todo_parser.py",
    "scripts/test_pipeline.py",
    "scripts/test_ollama.py",
    "scripts/test_stt.py",
    "scripts/benchmark_models.py",
]


@pytest.mark.parametrize("relpath", RUNNABLE)
def test_every_runnable_script_isolates_before_importing_assistant(relpath):
    src = (REPO / relpath).read_text()

    isolate_at = src.find("isolate(")
    assert isolate_at != -1, (
        f"{relpath} never calls tests.isolation.isolate() — it would run "
        "against the real calendar, command memory and vocabulary."
    )
    first_app_import = min(
        [m.start() for m in re.finditer(r"^\s*(?:from|import)\s+assistant\b", src, re.M)]
        or [len(src)]
    )
    assert isolate_at < first_app_import, (
        f"{relpath} imports `assistant` before isolate(). The store paths are "
        "module constants and default arguments read at import time, so "
        "isolating afterwards is too late."
    )


def test_the_audit_harness_isolates_too():
    # It has its own preamble (it works from a *copy* of the real vocabulary on
    # purpose), so it is exempt from the import-order check but not from this.
    src = (REPO / "scripts/audit_assistant.py").read_text()
    for var in ("MACALENDAR_DB", "MACALENDAR_MEMORY_DB", "MACALENDAR_VOCAB"):
        assert var in src, f"audit_assistant.py does not set {var}"


def test_the_suite_itself_is_pointed_at_scratch_files():
    from tests.isolation import REAL_DIR, STORES
    for var in STORES:
        path = os.environ.get(var)
        assert path, f"{var} is not set for this test run"
        assert os.path.realpath(os.path.dirname(path)) != os.path.realpath(REAL_DIR), (
            f"{var} points into the real store directory"
        )


def test_opening_the_real_database_from_a_test_is_refused():
    """The backstop: even with no isolation at all, a test cannot open it."""
    from assistant.db import DB_PATH, CalendarDB

    with pytest.raises(RuntimeError, match="Refusing to open the real calendar"):
        CalendarDB(path=DB_PATH)


def test_the_guard_lets_the_real_app_through():
    """It must only fire under pytest — the app itself opens that file for real."""
    code = (
        "import os, sys; sys.path.insert(0, %r)\n"
        "for v in ('PYTEST_CURRENT_TEST', 'PYTEST_VERSION'):\n"
        "    os.environ.pop(v, None)\n"
        "os.environ.pop('MACALENDAR_DB', None)\n"
        "from assistant.db import CalendarDB, DB_PATH\n"
        "CalendarDB._guard_real_db(DB_PATH)\n"
        "print('allowed')\n" % str(REPO)
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         cwd=str(REPO))
    assert out.returncode == 0, out.stderr
    assert "allowed" in out.stdout
