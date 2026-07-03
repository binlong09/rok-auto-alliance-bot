"""Tests for BlueStacksController pure-logic pieces (no ADB needed):
type_text() escaping and _write_resolution_to_conf() rewriting."""
import logging

import pytest

import bluestacks_controller
from bluestacks_controller import BlueStacksController


class FakeCompleted:
    def __init__(self, returncode=0):
        self.returncode = returncode
        self.stdout = ''
        self.stderr = ''


@pytest.fixture
def controller():
    """Bare controller with only the attributes type_text needs."""
    ctrl = object.__new__(BlueStacksController)
    ctrl.adb_path = 'adb'
    ctrl.adb_device = 'x'
    ctrl.logger = logging.getLogger('test_bluestacks')
    return ctrl


@pytest.fixture
def run_capture(monkeypatch):
    """Patch subprocess.run and time.sleep in the module; capture argv."""
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return FakeCompleted(0)

    monkeypatch.setattr(bluestacks_controller.subprocess, 'run', fake_run)
    monkeypatch.setattr(bluestacks_controller.time, 'sleep', lambda *_: None)
    return calls


def test_type_text_spaces_become_percent_s(controller, run_capture):
    assert controller.type_text('hello world again') is True
    assert run_capture[0][-1] == 'hello%sworld%sagain'


def test_type_text_special_chars_backslash_escaped(controller, run_capture):
    assert controller.type_text('a(b)$c;d') is True
    assert run_capture[0][-1] == 'a\\(b\\)\\$c\\;d'
    # Full argv shape: adb -s <device> shell input text <escaped>
    assert run_capture[0][:6] == ['adb', '-s', 'x', 'shell', 'input', 'text']


def test_type_text_backslash_escaped_first(controller, run_capture):
    assert controller.type_text('a\\b') is True
    assert run_capture[0][-1] == 'a\\\\b'


def test_type_text_nonzero_returncode_returns_false(controller, monkeypatch):
    monkeypatch.setattr(bluestacks_controller.subprocess, 'run',
                        lambda cmd, **kw: FakeCompleted(1))
    monkeypatch.setattr(bluestacks_controller.time, 'sleep', lambda *_: None)
    assert controller.type_text('hello') is False


# ---------------------------------------------------------------------------
# _write_resolution_to_conf
# ---------------------------------------------------------------------------

CONF_LINES = [
    'bst.installed_images="Pie64"\n',
    'bst.instance.Pie64.abi_list="x86,x64"\n',
    'bst.instance.Pie64.fb_width="1600"\n',
    'bst.instance.Pie64.fb_height="900"\n',
    'bst.instance.Pie64.dpi="320"\n',
    'bst.instance.Pie64.status="2"\n',
    'bst.instance.Other.fb_width="800"\n',
]


def make_controller(conf_path, instance_name='Pie64'):
    ctrl = object.__new__(BlueStacksController)
    ctrl.logger = logging.getLogger('test_bluestacks_conf')
    ctrl.bluestacks_conf_path = str(conf_path)
    ctrl.bluestacks_instance_name = instance_name
    return ctrl


def test_conf_existing_keys_rewritten_in_place(tmp_path):
    conf = tmp_path / 'bluestacks.conf'
    conf.write_text(''.join(CONF_LINES), encoding='utf-8')
    ctrl = make_controller(conf)

    assert ctrl._write_resolution_to_conf(1280, 720, 240) is True

    lines = conf.read_text(encoding='utf-8').splitlines()
    assert lines[2] == 'bst.instance.Pie64.fb_width="1280"'
    assert lines[3] == 'bst.instance.Pie64.fb_height="720"'
    assert lines[4] == 'bst.instance.Pie64.dpi="240"'
    assert len(lines) == len(CONF_LINES)  # nothing appended


def test_conf_missing_keys_appended_when_instance_exists(tmp_path):
    conf = tmp_path / 'bluestacks.conf'
    # Instance exists (status key) but has no display keys at all
    conf.write_text('bst.instance.Pie64.status="2"\n', encoding='utf-8')
    ctrl = make_controller(conf)

    assert ctrl._write_resolution_to_conf(1280, 720, 240) is True

    lines = conf.read_text(encoding='utf-8').splitlines()
    assert lines[0] == 'bst.instance.Pie64.status="2"'
    assert set(lines[1:]) == {
        'bst.instance.Pie64.fb_width="1280"',
        'bst.instance.Pie64.fb_height="720"',
        'bst.instance.Pie64.dpi="240"',
    }


def test_conf_returns_false_when_instance_has_no_keys(tmp_path):
    conf = tmp_path / 'bluestacks.conf'
    conf.write_text('bst.instance.Other.fb_width="800"\n', encoding='utf-8')
    ctrl = make_controller(conf, instance_name='Pie64')

    assert ctrl._write_resolution_to_conf(1280, 720, 240) is False
    # File untouched
    assert conf.read_text(encoding='utf-8') == 'bst.instance.Other.fb_width="800"\n'


def test_conf_other_lines_preserved(tmp_path):
    conf = tmp_path / 'bluestacks.conf'
    conf.write_text(''.join(CONF_LINES), encoding='utf-8')
    ctrl = make_controller(conf)

    assert ctrl._write_resolution_to_conf(1280, 720, 240) is True

    lines = conf.read_text(encoding='utf-8').splitlines()
    assert lines[0] == 'bst.installed_images="Pie64"'
    assert lines[1] == 'bst.instance.Pie64.abi_list="x86,x64"'
    assert lines[5] == 'bst.instance.Pie64.status="2"'
    assert lines[6] == 'bst.instance.Other.fb_width="800"'
