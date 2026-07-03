"""Tests for subprocess_utils: hidden-window subprocess wrappers.

The app ships as a windowed (console=False) PyInstaller executable, so any
console child process (adb.exe, taskkill, wmic) launched without
CREATE_NO_WINDOW flashes a command-prompt window at the user. These tests
pin the wrapper behavior and - via a source scan - guarantee no module in
src/ bypasses the wrappers with a direct subprocess call.
"""
import os
import re
import subprocess
import sys

import pytest

import subprocess_utils
from subprocess_utils import popen_hidden, popen_new_console, run_hidden

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "src"))


# ---------------------------------------------------------------------------
# CREATE_NO_WINDOW constant
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only constant")
def test_constant_matches_subprocess_on_windows():
    assert subprocess_utils.CREATE_NO_WINDOW == subprocess.CREATE_NO_WINDOW
    assert subprocess_utils.CREATE_NO_WINDOW != 0


@pytest.mark.skipif(sys.platform == "win32", reason="non-Windows fallback")
def test_constant_is_zero_off_windows():
    assert subprocess_utils.CREATE_NO_WINDOW == 0


# ---------------------------------------------------------------------------
# run_hidden
# ---------------------------------------------------------------------------

@pytest.fixture
def run_recorder(monkeypatch):
    """Patch subprocess.run, recording (cmd, kwargs) and returning a sentinel."""
    calls = []
    sentinel = object()

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return sentinel

    monkeypatch.setattr(subprocess_utils.subprocess, "run", fake_run)
    return calls, sentinel


def test_run_hidden_sets_create_no_window(run_recorder):
    calls, _ = run_recorder
    run_hidden(["adb", "devices"])
    (_, kwargs), = calls
    assert kwargs["creationflags"] == subprocess_utils.CREATE_NO_WINDOW


def test_run_hidden_merges_caller_creationflags(run_recorder):
    calls, _ = run_recorder
    run_hidden(["adb", "devices"], creationflags=0x10)
    (_, kwargs), = calls
    assert kwargs["creationflags"] == 0x10 | subprocess_utils.CREATE_NO_WINDOW


def test_run_hidden_forwards_cmd_kwargs_and_result(run_recorder):
    calls, sentinel = run_recorder
    result = run_hidden(["adb", "shell", "echo"], capture_output=True,
                        text=True, timeout=15)
    (cmd, kwargs), = calls
    assert cmd == ["adb", "shell", "echo"]
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["timeout"] == 15
    assert result is sentinel


def test_run_hidden_executes_real_command():
    result = run_hidden([sys.executable, "-c", "print('rok-ok')"],
                        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0
    assert result.stdout.strip() == "rok-ok"


# ---------------------------------------------------------------------------
# popen_hidden
# ---------------------------------------------------------------------------

def test_popen_hidden_sets_create_no_window(monkeypatch):
    calls = []
    sentinel = object()

    def fake_popen(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return sentinel

    monkeypatch.setattr(subprocess_utils.subprocess, "Popen", fake_popen)
    result = popen_hidden(["HD-Player.exe", "--instance", "Pie64"])
    (cmd, kwargs), = calls
    assert cmd == ["HD-Player.exe", "--instance", "Pie64"]
    assert kwargs["creationflags"] == subprocess_utils.CREATE_NO_WINDOW
    assert result is sentinel


# ---------------------------------------------------------------------------
# popen_new_console
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only constant")
def test_new_console_constant_matches_subprocess_on_windows():
    assert subprocess_utils.CREATE_NEW_CONSOLE == subprocess.CREATE_NEW_CONSOLE
    assert subprocess_utils.CREATE_NEW_CONSOLE != 0


def test_popen_new_console_sets_flag(monkeypatch):
    calls = []
    sentinel = object()

    def fake_popen(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return sentinel

    monkeypatch.setattr(subprocess_utils.subprocess, "Popen", fake_popen)
    result = popen_new_console(["cmd.exe", "/c", "updater.bat"])
    (cmd, kwargs), = calls
    assert cmd == ["cmd.exe", "/c", "updater.bat"]
    assert kwargs["creationflags"] == subprocess_utils.CREATE_NEW_CONSOLE
    assert result is sentinel


# ---------------------------------------------------------------------------
# Regression scan: nothing in src/ may call subprocess directly
# ---------------------------------------------------------------------------

DIRECT_CALL = re.compile(
    r"subprocess\.(run|Popen|call|check_call|check_output)\s*\("
    r"|from\s+subprocess\s+import\s")


def test_no_direct_subprocess_calls_in_src():
    """Every subprocess call in src/ must go through subprocess_utils,
    otherwise a windowed build flashes a console window per call."""
    offenders = []
    for name in sorted(os.listdir(SRC_DIR)):
        if not name.endswith(".py") or name == "subprocess_utils.py":
            continue
        path = os.path.join(SRC_DIR, name)
        with open(path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                if DIRECT_CALL.search(line):
                    offenders.append(f"{name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Direct subprocess calls found (use subprocess_utils.run_hidden / "
        "popen_hidden so windowed builds don't flash console windows):\n"
        + "\n".join(offenders))
