#!/usr/bin/env python3
"""Subprocess wrappers that never flash a console window.

The app ships as a windowed PyInstaller executable (console=False in
rok_automation.spec). A windowed process has no console, so every console
child (adb.exe, taskkill, wmic) launched with plain subprocess.run() makes
Windows allocate a brand-new console window that flashes at the user - and
the bot runs ADB commands every couple of seconds.

CREATE_NO_WINDOW suppresses that console entirely. It only affects
console-subsystem children, so routing GUI children (HD-Player.exe)
through these wrappers is harmless. All subprocess calls in src/ must go
through this module; tests/test_subprocess_utils.py enforces it.
"""
import subprocess
import sys

CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
CREATE_NEW_CONSOLE = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0


def run_hidden(cmd, **kwargs):
    """subprocess.run() without a console window flash on Windows."""
    kwargs["creationflags"] = kwargs.get("creationflags", 0) | CREATE_NO_WINDOW
    return subprocess.run(cmd, **kwargs)


def popen_hidden(cmd, **kwargs):
    """subprocess.Popen() without a console window flash on Windows."""
    kwargs["creationflags"] = kwargs.get("creationflags", 0) | CREATE_NO_WINDOW
    return subprocess.Popen(cmd, **kwargs)


def popen_new_console(cmd, **kwargs):
    """subprocess.Popen() in its own console window that survives this
    process exiting. Used for the self-updater, which must keep running
    (and show progress) after the app closes so it can swap files in."""
    kwargs["creationflags"] = kwargs.get("creationflags", 0) | CREATE_NEW_CONSOLE
    return subprocess.Popen(cmd, **kwargs)
