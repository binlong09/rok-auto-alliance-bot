#!/usr/bin/env python3
"""
Automation Base - Shared mixins for the automation components.

Historically every automation component copy-pasted the same
check_stop_requested() implementation. This mixin holds the single
shared copy; subclasses only set STOP_CONTEXT so the stop log message
stays specific to each component.

(The old DialogCloserMixin / AllianceScreenMixin navigation helpers
were replaced by ScreenRouter.goto(), which navigates by observed
screen state instead of blind escapes and unverified clicks.)
"""


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
