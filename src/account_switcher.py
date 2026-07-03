#!/usr/bin/env python3
"""
Account Switcher - Switches between game accounts (email logins).

Unlike the character switcher (which rotates characters *within* one logged
in account), this module logs the game out and logs back in with a different
account, so one BlueStacks instance can farm several accounts.

The whole flow is OCR/template driven and verifies each screen before
acting:

    home -> avatar -> Settings -> Account -> Switch Account
         -> login screen -> (saved account entry OR email+password form)
         -> wait for game to load -> home

Configuration (config.ini):

    [Accounts]
    accounts = fbuilder@minnyat.dev:secret1, fbuilder1@minnyat.dev:secret2

Each entry is email:password. When the section is present the controller
runs the full character automation once per account.

NOTE: the login UI differs slightly between RoK versions (global/kr/gamota)
and Lilith account center updates. All lookups are text based with several
keyword variants; run with debug_mode enabled the first time to capture
screenshots if a step fails, and add template images (see template_matcher.py)
for any icon this flow cannot find via text.
"""
import time
import logging

import timings


class AccountSwitcher:
    """Automates logging out and into a different account."""

    def __init__(self, ocr_helper, screen_detector, bluestacks, coords, navigator,
                 recovery_manager, click_delay_ms=1000, game_load_wait_seconds=60,
                 stop_check_callback=None):
        """
        Args:
            ocr_helper: OCRHelper instance for text detection
            screen_detector: ScreenDetector instance for screen state detection
            bluestacks: BlueStacksController instance for input
            coords: CoordinateManager instance for coordinates
            navigator: VerifiedNavigator instance for verified clicks
            recovery_manager: RecoveryManager instance to reach a known state
            click_delay_ms: Delay between clicks in milliseconds
            game_load_wait_seconds: Max seconds to wait for the game to load
            stop_check_callback: Optional callback to check if automation should stop
        """
        self.logger = logging.getLogger(__name__)
        self.ocr = ocr_helper
        self.screen = screen_detector
        self.bluestacks = bluestacks
        self.coords = coords
        self.nav = navigator
        self.recovery = recovery_manager
        self.click_delay_ms = click_delay_ms
        self.game_load_wait_seconds = game_load_wait_seconds
        self.stop_check = stop_check_callback

    @staticmethod
    def parse_accounts(config_manager):
        """
        Parse the [Accounts] accounts option into a list of dicts.

        Format: comma-separated email:password pairs.

        Returns:
            list[dict]: [{'email': ..., 'password': ...}, ...] (empty if unset)
        """
        raw = config_manager.get_config('Accounts', 'accounts', '') or ''
        accounts = []
        for entry in raw.split(','):
            entry = entry.strip()
            if not entry:
                continue
            if ':' not in entry:
                logging.getLogger(__name__).warning(
                    f"Ignoring malformed [Accounts] entry (expected email:password): {entry!r}"
                )
                continue
            email, password = entry.split(':', 1)
            accounts.append({'email': email.strip(), 'password': password.strip()})
        return accounts

    def check_stop_requested(self):
        """Check if automation should stop."""
        if self.stop_check and self.stop_check():
            self.logger.info("Stop requested during account switching")
            return True
        return False

    def open_account_screen(self):
        """
        Navigate home -> avatar -> Settings -> Account, verifying each screen.

        Returns:
            bool: True if the account management screen is open
        """
        if self.check_stop_requested():
            return False

        # Start from a known state
        if not self.recovery.return_to_home(max_attempts=4):
            self.logger.error("Could not reach home village before account switch")
            return False

        # Avatar -> profile menu
        if not self.nav.click_and_verify(
            "avatar icon",
            template='avatar_icon',
            fallback_point=self.coords.get_nav('avatar_icon'),
            verify=self.screen.is_in_profile_menu,
            verify_timeout=8,
            settle_wait=timings.LONG_TRANSITION_WAIT,
        ):
            self.logger.error("Profile menu did not open")
            return False

        # Settings button -> settings screen (OCR hit is the label below the
        # gear icon, so click above the text)
        if not self.nav.click_and_verify(
            "settings button",
            template='settings_icon',
            texts=["Settings"],
            region=self.coords.get_region('profile_menu'),
            offset={'x': 0, 'y': -45},
            fallback_point=self.coords.get_nav('settings_icon'),
            verify=self.screen.is_in_settings_screen,
            verify_timeout=8,
            settle_wait=timings.SCREEN_TRANSITION_WAIT,
        ):
            self.logger.error("Settings screen did not open")
            return False

        # Account button -> account screen (label sits below the icon)
        if not self.nav.click_and_verify(
            "account button",
            template='account_button',
            texts=["Account"],
            region=self.coords.get_region('settings_screen'),
            offset={'x': 0, 'y': -45},
            verify=self.screen.is_in_account_screen,
            verify_timeout=8,
            settle_wait=timings.SCREEN_TRANSITION_WAIT,
        ):
            self.logger.error("Account screen did not open")
            return False

        return True

    def open_switch_accounts_dialog(self):
        """
        On the User Center page, click "Switch Accounts" and verify the
        switch dialog opened (saved-account dropdown + Login button).

        Returns:
            bool: True if the Switch Accounts dialog is open
        """
        if self.check_stop_requested():
            return False

        # Search for the word "Switch" only: the OCR word-splitting fallback
        # would otherwise match the bare word "Accounts", which also appears
        # on the Accounts tile and would open the wrong page.
        return self.nav.click_and_verify(
            "Switch Accounts button",
            template='switch_account_button',
            texts=["Switch"],
            region=self.coords.get_region('account_screen'),
            verify=self.screen.is_in_switch_accounts_dialog,
            verify_timeout=8,
            settle_wait=timings.SCREEN_TRANSITION_WAIT,
        )

    def _press_login_button(self, description):
        """
        Locate and press the red Login CTA button, never the gray
        "Verification Code Login" / "Log in to another account" links.

        Plain OCR for "Login" is ambiguous here: the dialog contains several
        strings ending in "Login", and depending on which preprocessing
        variant wins, OCR can return the link instead of the button. So:
          1. template 'login_button' (white-on-red "Login") at a strict 0.92
             threshold - the gray links can't match, and the wider
             "Verification Code Login" red button peaks at ~0.88;
          2. red-color detection - the red CTA is the only red element on
             the password form / dropdown dialog;
          3. OCR text as a last resort.

        Args:
            description: What we're logging in for (log message)

        Returns:
            bool: True if the button was clicked
        """
        region = self.coords.get_region('switch_accounts_dialog')

        target = self.ocr.find_template('login_button', region=region, threshold=0.92)

        if not target:
            self.logger.info("Login button template not matched, trying red-color detection")
            target = self.ocr.detect_red_banner_position(region)

        if not target:
            self.logger.info("Red-color detection failed, falling back to OCR")
            target = self.ocr.detect_text_position(["Login"], region)

        if not target:
            self.logger.error("Could not find the Login button")
            return False

        self.logger.info(f"Pressing Login ({description}) at ({target['x']}, {target['y']})")
        if not self.bluestacks.click(target['x'], target['y'], self.click_delay_ms):
            return False

        time.sleep(timings.SCREEN_TRANSITION_WAIT)
        return True

    def open_manual_login_form(self):
        """
        From the Switch Accounts dialog, open the manual login form via
        the "Log in to another account" link.

        Returns:
            bool: True if the link was clicked
        """
        link = self.ocr.detect_text_position(
            ["Log in to another account", "another account"],
            self.coords.get_region('switch_accounts_dialog'))
        if not link:
            self.logger.error("Could not find 'Log in to another account' link")
            return False

        self.logger.info("Opening manual login ('Log in to another account')")
        self.bluestacks.click(link['x'], link['y'], self.click_delay_ms)
        time.sleep(timings.SCREEN_TRANSITION_WAIT)
        return True

    def select_account_in_dialog(self, email, password, force_manual_login=False):
        """
        In the Switch Accounts dialog: make sure the dropdown shows the
        target account, then press Login.

        The dialog shows one saved account in a dropdown row. If it is
        already the target, just Login. If not, expand the dropdown and
        pick the target from the saved list. If the target isn't saved at
        all, fall back to "Log in to another account" with email/password
        (verification-code step -> Password Login -> form).

        Args:
            email: Full target account email (matched whole, so
                fbuilder@... can never hit the fbuilder1@... row)
            password: Account password (only used for the manual-login fallback)
            force_manual_login: Skip the saved-account dropdown entirely and
                always log in via the email+password form

        Returns:
            bool: True if Login was pressed for the target account
        """
        if self.check_stop_requested():
            return False

        dialog_region = self.coords.get_region('switch_accounts_dialog')

        if force_manual_login:
            if not self.open_manual_login_form():
                return False
            return self.login_with_email(email, password)

        # Is the target already selected in the dropdown?
        pos = self.ocr.detect_text_position([email], dialog_region)

        if not pos:
            # Expand the dropdown (click the row showing the current email -
            # any token containing '@' inside the dialog) and look again.
            self.logger.info(f"{email} not selected yet, expanding the account dropdown")
            row = self.ocr.detect_text_position(["@"], dialog_region)
            if row:
                self.bluestacks.click(row['x'], row['y'], self.click_delay_ms)
                time.sleep(timings.ACTION_SETTLE_WAIT)
                # The expanded list can extend below the dialog - search wide
                pos = self.ocr.detect_text_position(
                    [email], self.coords.get_region('account_screen'))
                if pos:
                    self.logger.info(f"Selecting {email} from the saved accounts list")
                    self.bluestacks.click(pos['x'], pos['y'], self.click_delay_ms)
                    time.sleep(timings.ACTION_SETTLE_WAIT)

            if not pos:
                # Not a saved account - use the manual login form
                self.logger.info(f"{email} is not a saved account, using manual login")
                if not self.open_manual_login_form():
                    return False
                return self.login_with_email(email, password)

        # Press the Login button
        return self._press_login_button(f"switch to {email}")

    def login_with_email(self, email, password):
        """
        Complete the manual email+password login.

        Called after "Log in to another account" was pressed in the Switch
        Accounts dialog. The Lilith dialog then shows a verification-code
        step first; the password form is behind its "Password Login" link:

            [Email Address        ]        <- verification-code step
            (Verification Code Login)
             Password Login                <- click this link first

            [Email Address        ]        <- password form
            [Please Enter Password]
            (Login)

        Args:
            email: Account email address
            password: Account password

        Returns:
            bool: True if the login form was filled and submitted
        """
        if self.check_stop_requested():
            return False

        region = self.coords.get_region('switch_accounts_dialog')

        # Step 1: switch from the verification-code step to the password form
        if not self.ocr.detect_text_in_region(["Please Enter Password", "Enter Password"], region):
            link = self.ocr.wait_for_text_position(["Password Login"], region, timeout=8)
            if not link:
                self.logger.error("Could not find the 'Password Login' link")
                return False
            self.logger.info("Choosing Password Login")
            self.bluestacks.click(link['x'], link['y'], self.click_delay_ms)
            time.sleep(timings.ACTION_SETTLE_WAIT)

            if not self.ocr.wait_for_text(
                    ["Please Enter Password", "Enter Password"], region,
                    timeout=8, description="password login form"):
                self.logger.error("Password login form did not appear")
                return False

        # Step 2: email field (click its placeholder, then type)
        email_field = self.ocr.detect_text_position(["Email Address", "Email"], region)
        if not email_field:
            self.logger.error("Could not find the email input field")
            return False

        self.bluestacks.click(email_field['x'], email_field['y'], self.click_delay_ms)
        self.logger.info(f"Typing email: {email}")
        if not self.bluestacks.type_text(email):
            return False
        time.sleep(timings.ACTION_SETTLE_WAIT)

        # Step 3: password field. Match only the placeholder - bare
        # "password" would also hit the "Forgot password" link.
        password_field = self.ocr.detect_text_position(
            ["Please Enter Password", "Enter Password"], region)
        if not password_field:
            self.logger.error("Could not find the password input field")
            return False

        self.bluestacks.click(password_field['x'], password_field['y'], self.click_delay_ms)
        self.logger.info("Typing password")
        if not self.bluestacks.type_text(password):
            return False
        time.sleep(timings.ACTION_SETTLE_WAIT)

        # Step 4: press the red Login button (template/color based - plain
        # OCR here can hit the "Verification Code Login" link instead)
        return self._press_login_button(f"sign in as {email}")

    def wait_for_game_ready(self):
        """
        Wait until the game has loaded back into the world after login.

        Polls the loading screen away, then confirms home village or map is
        visible (dismissing any popups with escape along the way).

        Returns:
            bool: True if the game reached a known in-world state
        """
        deadline = time.time() + self.game_load_wait_seconds

        # Phase 1: wait for the loading screen to pass
        while time.time() < deadline:
            if self.check_stop_requested():
                return False
            if not self.screen.is_loading_screen():
                break
            self.logger.info("Game still loading after login...")
            time.sleep(timings.POLL_INTERVAL)

        # Phase 2: reach a known state (also dismisses event popups)
        if self.recovery.return_to_home(max_attempts=6):
            self.logger.info("Game is ready after account switch")
            return True

        self.logger.error("Game did not reach a known state after account login")
        return False

    def switch_to_account(self, email, password, force_manual_login=False):
        """
        Full account switch: log out and log in as the given account.

        Args:
            email: Account email address
            password: Account password
            force_manual_login: Always use the email+password form instead of
                the saved-account dropdown

        Returns:
            bool: True if the game is running under the new account
        """
        self.logger.info(f"=== Switching to account {email} ===")

        # Settings -> Account -> User Center
        if not self.open_account_screen():
            return False

        # User Center -> Switch Accounts dialog
        if not self.open_switch_accounts_dialog():
            return False

        # Pick the target account (saved dropdown or manual login) and Login
        if not self.select_account_in_dialog(email, password,
                                             force_manual_login=force_manual_login):
            return False

        if not self.wait_for_game_ready():
            return False

        self.logger.info(f"=== Now logged in as {email} ===")
        return True
