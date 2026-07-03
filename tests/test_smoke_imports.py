"""Smoke test: every non-GUI module in src/ can be imported.

GUI/entry modules (unified_gui, instance_manager_gui, main) and the
ocr_debug_tool are skipped: they pull in tkinter or have side effects.
Importing alone must not require an emulator, ADB, or a tesseract binary.
"""
import importlib

import pytest

MODULES = [
    'timings',
    'coordinate_manager',
    'template_matcher',
    'config_manager',
    'bluestacks_controller',
    'ocr_helper',
    'screen_detector',
    'navigation_helper',
    'recovery_manager',
    'build_automation',
    'donation_automation',
    'expedition_automation',
    'character_switcher',
    'account_switcher',
    'daily_task_tracker',
    'schedule_manager',
    'instance_manager',
    'rok_game_controller',
    'multi_instance_launcher',
]


@pytest.mark.parametrize('module_name', MODULES)
def test_module_imports(module_name):
    assert importlib.import_module(module_name) is not None
