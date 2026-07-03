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
