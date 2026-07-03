"""Tests for updater.py: self-update via GitHub Releases.

Covers the pure logic: version parsing/comparison, release asset
selection, zip extraction with user-state preservation, and the
update-availability gating. Network fetch and the Tkinter prompt /
process-swap plumbing are boundaries, exercised via mocks or not at all.
"""
import zipfile
from pathlib import Path

import pytest

import updater
from updater import (
    _extract,
    _is_newer,
    _parse_version,
    _pick_zip_asset,
    get_available_update,
    get_current_version,
)

# ---------------------------------------------------------------------------
# Version parsing and comparison
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("1.2.3", (1, 2, 3)),
    ("v1.2.3", (1, 2, 3)),
    ("V2.0.10", (2, 0, 10)),
    ("  1.0.0  ", (1, 0, 0)),
])
def test_parse_version(raw, expected):
    assert _parse_version(raw) == expected


@pytest.mark.parametrize("current,latest,newer", [
    ("1.0.0", "1.0.1", True),   # patch bump
    ("1.0.0", "1.1.0", True),   # minor bump
    ("1.9.9", "2.0.0", True),   # major bump
    ("1.0.1", "1.0.1", False),  # equal
    ("1.0.2", "1.0.1", False),  # remote older
    ("1.0.0", "v1.0.1", True),  # tag with v prefix
    ("1.0.0", "", False),       # empty tag
    ("1.0.0", "garbage", False),  # unparseable tag never triggers
])
def test_is_newer(current, latest, newer):
    assert _is_newer(current, latest) is newer


# ---------------------------------------------------------------------------
# get_current_version
# ---------------------------------------------------------------------------

def test_current_version_reads_bundled_file(monkeypatch, tmp_path):
    version_file = tmp_path / "VERSION"
    version_file.write_text("1.2.3\n", encoding="utf-8")
    monkeypatch.setattr(updater, "_bundled_resource",
                        lambda name: str(tmp_path / name))
    assert get_current_version() == "1.2.3"


def test_current_version_missing_file_falls_back(monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "_bundled_resource",
                        lambda name: str(tmp_path / name))
    assert get_current_version() == "0.0.0"


def test_repo_version_file_is_parseable():
    """The real VERSION file at the repo root must be a plain x.y.z."""
    root = Path(__file__).resolve().parent.parent
    raw = (root / "VERSION").read_text(encoding="utf-8")
    assert len(_parse_version(raw)) == 3


# ---------------------------------------------------------------------------
# _pick_zip_asset
# ---------------------------------------------------------------------------

def test_pick_zip_asset_returns_first_zip():
    release = {"assets": [
        {"name": "checksums.txt", "browser_download_url": "http://x/txt"},
        {"name": "RoK_Automation_1.0.7.zip", "browser_download_url": "http://x/a.zip"},
        {"name": "other.zip", "browser_download_url": "http://x/b.zip"},
    ]}
    assert _pick_zip_asset(release) == "http://x/a.zip"


def test_pick_zip_asset_case_insensitive():
    release = {"assets": [
        {"name": "RELEASE.ZIP", "browser_download_url": "http://x/up.zip"},
    ]}
    assert _pick_zip_asset(release) == "http://x/up.zip"


def test_pick_zip_asset_no_zip_returns_none_even_with_zipball():
    """A source zipball has no exe - it must never be used as an update."""
    release = {"assets": [{"name": "notes.txt", "browser_download_url": "http://x/t"}],
               "zipball_url": "http://x/source.zip"}
    assert _pick_zip_asset(release) is None


def test_pick_zip_asset_empty_release():
    assert _pick_zip_asset({}) is None


# ---------------------------------------------------------------------------
# _extract
# ---------------------------------------------------------------------------

def make_zip(path, entries):
    """entries: dict of archive-name -> bytes content."""
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)


def test_extract_flat_zip(tmp_path):
    zip_path = tmp_path / "release.zip"
    make_zip(zip_path, {
        "RoK Automation.exe": b"exe",
        "_internal/base_library.zip": b"lib",
        "Tesseract-OCR/tesseract.exe": b"ocr",
    })
    staging = tmp_path / "staging"
    staging.mkdir()

    assert _extract(str(zip_path), str(staging)) is True
    assert (staging / "RoK Automation.exe").read_bytes() == b"exe"
    assert (staging / "_internal" / "base_library.zip").read_bytes() == b"lib"
    assert (staging / "Tesseract-OCR" / "tesseract.exe").read_bytes() == b"ocr"


def test_extract_strips_single_top_level_dir(tmp_path):
    """build.py zips everything under a 'RoK Automation/' folder."""
    zip_path = tmp_path / "release.zip"
    make_zip(zip_path, {
        "RoK Automation/RoK Automation.exe": b"exe",
        "RoK Automation/_internal/python313.dll": b"dll",
    })
    staging = tmp_path / "staging"
    staging.mkdir()

    assert _extract(str(zip_path), str(staging)) is True
    assert (staging / "RoK Automation.exe").read_bytes() == b"exe"
    assert (staging / "_internal" / "python313.dll").read_bytes() == b"dll"
    assert not (staging / "RoK Automation").exists()


def test_extract_skips_user_state(tmp_path):
    zip_path = tmp_path / "release.zip"
    make_zip(zip_path, {
        "RoK Automation.exe": b"exe",
        "instances/index.json": b"{}",
        "instances/abc/config.ini": b"[BlueStacks]",
        "logs/rok_automation.log": b"old log",
        "config.ini": b"[BlueStacks]",
        "portable.txt": b"",
    })
    staging = tmp_path / "staging"
    staging.mkdir()

    assert _extract(str(zip_path), str(staging)) is True
    assert (staging / "RoK Automation.exe").exists()
    assert not (staging / "instances").exists()
    assert not (staging / "logs").exists()
    assert not (staging / "config.ini").exists()
    assert not (staging / "portable.txt").exists()


def test_extract_refuses_path_traversal(tmp_path):
    """Zip-slip: entries must never escape the staging dir."""
    zip_path = tmp_path / "release.zip"
    make_zip(zip_path, {
        "RoK Automation.exe": b"exe",
        "../escaped.txt": b"evil",
        "_internal/../../escaped2.txt": b"evil",
    })
    staging = tmp_path / "staging"
    staging.mkdir()

    assert _extract(str(zip_path), str(staging)) is True
    assert (staging / "RoK Automation.exe").exists()
    assert not (tmp_path / "escaped.txt").exists()
    assert not (tmp_path / "escaped2.txt").exists()


def test_extract_bad_zip_returns_false(tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"this is not a zip")
    staging = tmp_path / "staging"
    staging.mkdir()
    assert _extract(str(bad), str(staging)) is False


# ---------------------------------------------------------------------------
# _download (local file:// URL - no network)
# ---------------------------------------------------------------------------

def test_download_copies_bytes(tmp_path):
    src = tmp_path / "src.bin"
    src.write_bytes(b"release-bytes")
    dest = tmp_path / "dest.bin"
    assert updater._download(src.as_uri(), str(dest)) is True
    assert dest.read_bytes() == b"release-bytes"


def test_download_missing_source_returns_false(tmp_path):
    missing = tmp_path / "nope.bin"
    dest = tmp_path / "dest.bin"
    assert updater._download(missing.as_uri(), str(dest)) is False


# ---------------------------------------------------------------------------
# get_available_update gating
# ---------------------------------------------------------------------------

def test_no_release_means_no_update(monkeypatch):
    monkeypatch.setattr(updater, "_fetch_latest_release", lambda: None)
    assert get_available_update() is None


def test_same_version_means_no_update(monkeypatch):
    monkeypatch.setattr(updater, "get_current_version", lambda: "1.0.7")
    monkeypatch.setattr(updater, "_fetch_latest_release",
                        lambda: {"tag_name": "v1.0.7"})
    assert get_available_update() is None


def test_older_release_means_no_update(monkeypatch):
    monkeypatch.setattr(updater, "get_current_version", lambda: "1.0.7")
    monkeypatch.setattr(updater, "_fetch_latest_release",
                        lambda: {"tag_name": "1.0.6"})
    assert get_available_update() is None


def test_missing_tag_means_no_update(monkeypatch):
    monkeypatch.setattr(updater, "get_current_version", lambda: "1.0.7")
    monkeypatch.setattr(updater, "_fetch_latest_release", lambda: {"assets": []})
    assert get_available_update() is None


def test_newer_release_is_returned(monkeypatch):
    release = {"tag_name": "1.0.8", "assets": []}
    monkeypatch.setattr(updater, "get_current_version", lambda: "1.0.7")
    monkeypatch.setattr(updater, "_fetch_latest_release", lambda: release)
    assert get_available_update() is release


# ---------------------------------------------------------------------------
# AUTO_UPDATE opt-out
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,enabled", [
    ("off", False),
    ("OFF ", False),
    ("prompt", True),
    ("", True),
])
def test_update_check_enabled(monkeypatch, value, enabled):
    monkeypatch.setenv("AUTO_UPDATE", value)
    assert updater._update_check_enabled() is enabled


def test_update_check_enabled_by_default(monkeypatch):
    monkeypatch.delenv("AUTO_UPDATE", raising=False)
    assert updater._update_check_enabled() is True
