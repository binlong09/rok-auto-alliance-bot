#!/usr/bin/env python3
"""
Automation Base - Shared mixins for the automation components.

Historically every automation component copy-pasted the same
check_stop_requested() / close_dialogs() implementations. These mixins
hold the single shared copy; subclasses only set STOP_CONTEXT so the
stop log message stays specific to each component.
"""
import time

import timings


class StopCheckMixin:
    """Shared stop-check used by every automation component.

    Subclasses set self.stop_check (callable or None) and self.logger,
    and may override STOP_CONTEXT for the log message.
    """

    STOP_CONTEXT = "operation"

    def check_stop_requested(self):
        """Check if automation should stop."""
        if self.stop_check and self.stop_check():
            self.logger.info(f"Stop requested during {self.STOP_CONTEXT}")
            return True
        return False


class DialogCloserMixin(StopCheckMixin):
    """Shared close_dialogs for components that dismiss game dialogs.

    Requires self.bluestacks (BlueStacksController) in addition to the
    StopCheckMixin attributes.
    """

    def close_dialogs(self):
        """Close any open dialogs using escape key."""
        if self.check_stop_requested():
            return False

        self.logger.info("Closing dialogs")
        if self.bluestacks.send_escape():
            self.logger.info("Sent escape key to close dialog")
            time.sleep(timings.ACTION_SETTLE_WAIT)
            return True

        time.sleep(timings.ACTION_SETTLE_WAIT)
        return True


class AllianceScreenMixin(DialogCloserMixin):
    """Shared navigation into the alliance screen, used by every automation
    that starts from the alliance menu (tech donation, territory claim...).

    Requires self.nav (VerifiedNavigator), self.screen (ScreenDetector) and
    self.coords (CoordinateManager) in addition to the DialogCloserMixin
    attributes.
    """

    def expand_bottom_bar(self):
        """Expand bottom bar if it's not expanded yet, and verify it expanded."""
        if self.screen.is_bottom_bar_expanded():
            self.logger.info("Bottom bar is expanded")
            return True

        return self.nav.click_and_verify(
            "expand bottom bar button",
            template='expand_button',
            fallback_point=self.coords.get_nav('expand_button'),
            verify=self.screen.is_bottom_bar_expanded,
            verify_timeout=5,
        )

    def open_alliance_screen(self):
        """
        Open the alliance screen from the bottom bar and verify it opened.

        The bottom bar can collapse again between steps, so each attempt
        re-expands it before clicking the Alliance icon - otherwise the
        click lands on the game world and the character is wrongly reported
        as not being in an alliance.

        Returns:
            bool: True if the alliance screen is open, False otherwise
        """
        for attempt in range(1, 3):
            if self.check_stop_requested():
                return False

            if not self.expand_bottom_bar():
                self.logger.warning(
                    f"Could not expand bottom bar (attempt {attempt}/2)")
                continue

            if self.nav.click_and_verify(
                "Alliance button",
                template='alliance_icon',
                region=self.coords.get_region('bottom_bar'),
                fallback_point=self.coords.get_nav('alliance_button'),
                attempts=1,
                settle_wait=timings.SCREEN_TRANSITION_WAIT,
            ):
                return True

            self.logger.warning(
                f"Alliance screen did not open (attempt {attempt}/2), retrying "
                "with a fresh bottom-bar expansion")

        return False
