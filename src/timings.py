#!/usr/bin/env python3
"""
Timings - Centralized, named timing constants for the automation modules.

Every `time.sleep(...)` call across the automation code used to hard-code a
bare number with no explanation of why that particular duration was chosen.
This module gives each recurring wait a name grouped by *why* the code is
waiting (not by its exact duration), so:

  - the reason for a wait is documented at the call site
    (`time.sleep(timings.SCREEN_TRANSITION_WAIT)` instead of `time.sleep(2)`)
  - every occurrence of the same kind of wait can be tuned in one place
  - values can optionally be tuned per-install via config.ini, without
    touching code (see load_overrides() below)

This is a pure refactor of existing behavior: the default values below are
exactly the literals that were previously scattered across the automation
modules.
"""
import logging

logger = logging.getLogger(__name__)

# --- Low-level input primitives ---------------------------------------------

# Very short pause after a raw ADB input primitive (swipe, escape keyevent)
# before returning control to the caller. Lives at the BlueStacksController
# level, below the higher-level "settle" waits used by automation modules.
MICRO_DELAY = 0.5

# --- General UI settle waits -------------------------------------------------

# Standard pause after a click or dialog-close for the UI to settle before
# the next check or action. This is the most common wait in the codebase.
ACTION_SETTLE_WAIT = 1.0

# Longer settle pause for ambiguous or heavier UI transitions: after a
# scroll swipe, a "blind" recovery escape with no known target screen, or
# re-checking process state after a suspected ADB transport error.
EXTENDED_SETTLE_WAIT = 1.5

# --- Screen navigation waits -------------------------------------------------

# Wait after navigating to a new screen/menu for it to finish rendering
# (e.g. bookmark screen, alliance screen, campaign/expedition screens).
SCREEN_TRANSITION_WAIT = 2.0

# Buffer wait after a heavier action or screen change - e.g. after selecting
# a build flag, after the loading screen disappears, after opening the
# profile menu, or before switching to the next character.
LONG_TRANSITION_WAIT = 3.0

# Wait for the world map to fully render after switching character (map
# rendering after a character switch is noticeably slower than a normal
# screen transition).
MAP_LOAD_WAIT = 4.0

# Wait for a heavy, list-style screen (character selection list, alliance
# tech donation list) to fully populate before interacting with it.
CHARACTER_SELECT_LOAD_WAIT = 6.0

# --- Polling intervals -------------------------------------------------------

# Interval between checks in polling loops (loading-screen detection,
# stop-event checks while waiting for the game to load).
POLL_INTERVAL = 2.0

# Interval used while polling for the character login confirmation dialog
# to appear after selecting a character.
CHARACTER_LOGIN_POLL_INTERVAL = 1.5

# --- ADB / process lifecycle waits ------------------------------------------

# Delay between retry attempts for ADB-related operations (shell
# verification, game launch retries).
ADB_RETRY_DELAY = 2.0

# Wait after force-stopping the RoK app to make sure it is fully stopped
# before the BlueStacks instance itself is torn down.
APP_STOP_WAIT = 2.0

# Pause between launching successive BlueStacks instances in a
# multi-instance run. Not currently consumed by any sleep in this module's
# owning files, but reserved here so the multi-instance orchestration UI
# can share the same tunable timings module.
LAUNCH_STAGGER_WAIT = 5.0


# Names of every overridable constant defined above. Kept as an explicit
# list (rather than e.g. scanning globals()) so load_overrides() only ever
# touches the timings we intend to expose, and so the [Timings] section
# keys are documented in one place.
_ALL_CONSTANTS = [
    "MICRO_DELAY",
    "ACTION_SETTLE_WAIT",
    "EXTENDED_SETTLE_WAIT",
    "SCREEN_TRANSITION_WAIT",
    "LONG_TRANSITION_WAIT",
    "MAP_LOAD_WAIT",
    "CHARACTER_SELECT_LOAD_WAIT",
    "POLL_INTERVAL",
    "CHARACTER_LOGIN_POLL_INTERVAL",
    "ADB_RETRY_DELAY",
    "APP_STOP_WAIT",
    "LAUNCH_STAGGER_WAIT",
]


def load_overrides(config_manager):
    """
    Apply overrides for the timing constants above from an optional
    [Timings] section in config.ini.

    Keys are the lowercased constant names (e.g. a config line
    `character_select_load_wait = 8` overrides CHARACTER_SELECT_LOAD_WAIT).
    Missing keys are ignored - the compiled-in default is kept. Invalid
    (non-numeric or negative) values are logged as a warning and skipped,
    also keeping the default, so a typo in config.ini can never crash
    startup.

    Only the existing public ConfigManager API (get_config(section, key,
    default)) is used, so this works with any object exposing that method
    and requires no changes to ConfigManager itself.

    Safe to call multiple times (e.g. once per controller instance, or once
    per BlueStacks instance in a multi-instance run) - it simply re-applies
    the same overrides.

    Args:
        config_manager: ConfigManager instance (or any object exposing
            get_config(section, key, default=None)).
    """
    if config_manager is None:
        return

    get_config = getattr(config_manager, "get_config", None)
    if get_config is None:
        logger.warning(
            "timings.load_overrides() called with an object with no get_config() method; skipping"
        )
        return

    module_globals = globals()

    for name in _ALL_CONSTANTS:
        raw_value = get_config("Timings", name.lower(), None)
        if raw_value is None:
            continue

        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            logger.warning(
                f"Ignoring invalid [Timings] override for '{name.lower()}': "
                f"{raw_value!r} is not a number"
            )
            continue

        if value < 0:
            logger.warning(
                f"Ignoring invalid [Timings] override for '{name.lower()}': "
                f"{value} is negative"
            )
            continue

        logger.info(f"Overriding timings.{name} = {value} (was {module_globals[name]})")
        module_globals[name] = value
