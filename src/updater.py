#!/usr/bin/env python3
"""Self-update via GitHub Releases.

Flow on startup (called from main.py after the GUI is built):
  1. Read the local VERSION file (bundled into the PyInstaller build).
  2. Hit the GitHub Releases API for the latest tag, on a background
     thread so startup never blocks on the network.
  3. If newer, ask the user via a dialog. Default is No - only an
     explicit Yes updates.
  4. On Yes: download the release zip, extract to a staging dir in
     %TEMP% (skipping user state), spawn updater.bat in its own console,
     and close the app so the bat can swap files in and relaunch.

updater.bat runs from %TEMP%, never from the install dir: cmd reads
batch files incrementally, so a bat inside the install dir could be
overwritten by its own robocopy mid-run.

Users can disable the check entirely with the AUTO_UPDATE=off
environment variable.
"""
import json
import logging
import os
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile

from subprocess_utils import popen_new_console

GITHUB_REPO = "binlong09/rok-auto-alliance-bot"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
HTTP_TIMEOUT = 5
DOWNLOAD_TIMEOUT = 120
USER_AGENT = "RoK-Automation-Updater"
EXE_NAME = "RoK Automation.exe"

# Top-level paths in the install dir that hold user state; never
# overwritten by an update. (Instance configs default to AppData, which
# the updater does not touch at all - these cover portable mode and logs.)
PRESERVE_PATHS = {"instances", "logs", "config.ini", "portable.txt", "debug_output"}

logger = logging.getLogger(__name__)


def _install_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _bundled_resource(name):
    base = getattr(sys, "_MEIPASS", None) or _install_dir()
    return os.path.join(base, name)


def get_current_version():
    try:
        with open(_bundled_resource("VERSION"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "0.0.0"


def _parse_version(v):
    v = v.strip().lstrip("vV")
    return tuple(int(p) for p in v.split(".") if p.isdigit())


def _is_newer(current, latest):
    return _parse_version(latest) > _parse_version(current)


def _update_check_enabled():
    return os.getenv("AUTO_UPDATE", "prompt").strip().lower() != "off"


def _fetch_latest_release():
    req = urllib.request.Request(RELEASES_API, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def get_available_update():
    """Return the latest release dict if it is newer than this build."""
    current = get_current_version()
    release = _fetch_latest_release()
    if not release:
        return None
    latest = (release.get("tag_name") or "").strip()
    if not latest or not _is_newer(current, latest):
        return None
    return release


def _pick_zip_asset(release):
    """URL of the first .zip release asset. No zipball fallback: a source
    archive contains no exe and must never be robocopied over an install."""
    for asset in release.get("assets", []):
        if asset.get("name", "").lower().endswith(".zip"):
            return asset.get("browser_download_url")
    return None


def _download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp, \
                open(dest, "wb") as f:
            shutil.copyfileobj(resp, f)
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _extract(zip_path, staging_dir):
    """Extract zip into staging_dir, skipping preserved paths.

    If the zip has a single top-level folder (build.py zips everything
    under 'RoK Automation/'; the CI zip is flat), descend into it so the
    staging dir matches the install dir layout.
    """
    try:
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            top = {n.split("/", 1)[0] for n in names if n}
            strip_prefix = ""
            if len(top) == 1:
                only = next(iter(top))
                if any(n.startswith(only + "/") for n in names):
                    strip_prefix = only + "/"

            for member in zf.infolist():
                name = member.filename
                if strip_prefix and name.startswith(strip_prefix):
                    name = name[len(strip_prefix):]
                if not name or name.endswith("/"):
                    continue
                first = name.split("/", 1)[0].split("\\", 1)[0]
                if first in PRESERVE_PATHS or name in PRESERVE_PATHS:
                    continue
                target = os.path.join(staging_dir, name.replace("/", os.sep))
                # Zip-slip guard: never write outside the staging dir.
                if os.path.commonpath(
                        [os.path.abspath(staging_dir),
                         os.path.abspath(target)]) != os.path.abspath(staging_dir):
                    logger.warning("Skipping unsafe zip entry: %s", member.filename)
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        return True
    except (zipfile.BadZipFile, OSError):
        return False


def _download_and_stage(asset_url):
    """Download the release zip and extract it to a staging dir in %TEMP%.

    Returns the staging dir path, or None on failure (temp dir cleaned up).
    """
    tmp_dir = tempfile.mkdtemp(prefix="rok_automation_update_")
    zip_path = os.path.join(tmp_dir, "release.zip")

    logger.info("Downloading update from %s", asset_url)
    if not _download(asset_url, zip_path):
        logger.error("Update download failed")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None

    staging = os.path.join(tmp_dir, "staging")
    os.makedirs(staging, exist_ok=True)
    logger.info("Extracting update...")
    if not _extract(zip_path, staging):
        logger.error("Update extraction failed")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None

    try:
        os.remove(zip_path)
    except OSError:
        pass
    return staging


def _spawn_updater(staging_dir):
    """Copy the bundled updater.bat next to the staging dir and run it in
    its own console. Returns True if the updater was spawned."""
    bundled_bat = _bundled_resource("updater.bat")
    if not os.path.exists(bundled_bat):
        logger.error("updater.bat missing from bundle - cannot apply update")
        return False

    if getattr(sys, "frozen", False):
        exe_name = os.path.basename(sys.executable)
    else:
        exe_name = EXE_NAME

    try:
        bat = os.path.join(os.path.dirname(staging_dir), "updater.bat")
        shutil.copy2(bundled_bat, bat)
        popen_new_console(
            ["cmd.exe", "/c", bat, staging_dir, _install_dir(), exe_name],
            close_fds=True,
        )
    except OSError:
        logger.exception("Failed to spawn the updater")
        return False

    logger.info("Update staged; closing so the updater can swap files in")
    return True


# ---------------------------------------------------------------------------
# GUI integration (Tkinter)
# ---------------------------------------------------------------------------

def check_for_updates_async(root):
    """Check GitHub for a newer release on a background thread; if one
    exists, prompt on the Tk main loop. Call once after the GUI is built."""
    if not _update_check_enabled():
        logger.info("Update check disabled (AUTO_UPDATE=off)")
        return

    def worker():
        release = get_available_update()
        if release:
            root.after(0, _prompt_and_install, root, release)

    threading.Thread(target=worker, daemon=True, name="update-check").start()


def _prompt_and_install(root, release):
    from tkinter import messagebox

    current = get_current_version()
    latest = (release.get("tag_name") or "").strip()
    notes = (release.get("body") or "").strip().splitlines()
    first_line = notes[0] if notes else "(no release notes)"

    if not messagebox.askyesno(
        "Update Available",
        f"A new version of RoK Automation is available.\n\n"
        f"Current version: v{current.lstrip('vV')}\n"
        f"Latest version: {latest}\n\n"
        f"{first_line}\n\n"
        "Update now? The app will restart automatically.",
        parent=root,
    ):
        logger.info("Update to %s declined by user", latest)
        return

    asset_url = _pick_zip_asset(release)
    if not asset_url:
        messagebox.showwarning(
            "Update", "The release has no downloadable zip.\n"
            "Please download it manually from GitHub.", parent=root)
        return

    progress = _show_progress_window(root, latest)

    def worker():
        staging = _download_and_stage(asset_url)
        root.after(0, _finish_install, root, progress, staging)

    threading.Thread(target=worker, daemon=True, name="update-download").start()


def _show_progress_window(root, latest):
    import tkinter as tk
    from tkinter import ttk

    win = tk.Toplevel(root)
    win.title("Updating")
    win.resizable(False, False)
    win.protocol("WM_DELETE_WINDOW", lambda: None)  # not cancellable
    tk.Label(
        win,
        text=f"Downloading update {latest}...\n"
             "The app will restart automatically when done.",
        padx=20, pady=12,
    ).pack()
    bar = ttk.Progressbar(win, mode="indeterminate", length=280)
    bar.pack(padx=20, pady=(0, 16))
    bar.start(10)
    win.transient(root)
    win.grab_set()
    return win


def _finish_install(root, progress, staging):
    from tkinter import messagebox

    progress.destroy()
    if staging is None:
        messagebox.showwarning(
            "Update failed",
            "The update could not be downloaded.\n"
            "Continuing with the current version.", parent=root)
        return

    if not _spawn_updater(staging):
        messagebox.showwarning(
            "Update failed",
            "The updater could not be started.\n"
            "Continuing with the current version.", parent=root)
        return

    # Close the GUI; main() returns after mainloop and the process exits,
    # letting updater.bat swap the files in and relaunch.
    root.destroy()
