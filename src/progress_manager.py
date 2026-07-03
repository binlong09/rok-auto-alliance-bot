#!/usr/bin/env python3
"""
Progress Manager — persists per-instance run progress so the bot can
resume after an interruption without redoing completed accounts/characters.

Progress files live in ``%APPDATA%/RoK Automation/progress/`` (one JSON
file per instance).  The file is updated after every significant step so
that a crash or manual stop always leaves a usable checkpoint.
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone

from instance_manager import get_appdata_dir

PROGRESS_DIR = os.path.join(get_appdata_dir(), "progress")


class ProgressManager:
    """Track and persist automation progress for one instance."""

    def __init__(self, instance_id):
        self.logger = logging.getLogger(__name__)
        self.instance_id = instance_id
        self._path = os.path.join(PROGRESS_DIR, f"{instance_id}_progress.json")
        self._data = None

    # ── file I/O ────────────────────────────────────────────────

    def _save(self):
        if self._data is None:
            return
        os.makedirs(PROGRESS_DIR, exist_ok=True)
        self._data["updated_at"] = datetime.now(timezone.utc).isoformat()
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self._path)

    def _load(self):
        """Load progress from disk.  Returns the dict or *None*."""
        if not os.path.exists(self._path):
            return None
        try:
            with open(self._path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            self.logger.warning("Corrupt progress file, ignoring: %s", exc)
            return None

    # ── query ───────────────────────────────────────────────────

    def has_resumable_session(self):
        """Return *True* if there is an incomplete (in_progress) session."""
        data = self._load()
        return data is not None and data.get("status") == "in_progress"

    def get_session_summary(self):
        """Return a human-readable summary of the saved session (for the
        resume dialog).  Returns *None* when there is nothing to resume."""
        data = self._load()
        if data is None or data.get("status") != "in_progress":
            return None

        accounts = data.get("accounts", [])
        total_chars = sum(len(a.get("characters", [])) for a in accounts)
        done_chars = sum(
            1
            for a in accounts
            for c in a.get("characters", [])
            if c.get("status") == "completed"
        )
        started = data.get("started_at", "?")
        try:
            dt = datetime.fromisoformat(started)
            started = dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            pass

        n_accounts = len(accounts)
        done_accounts = sum(1 for a in accounts if a.get("status") == "completed")

        lines = [f"Started: {started}"]
        if n_accounts > 1:
            lines.append(f"Accounts: {done_accounts}/{n_accounts} completed")
        lines.append(f"Characters: {done_chars}/{total_chars} completed")
        return "\n".join(lines)

    # ── session lifecycle ───────────────────────────────────────

    def start_session(self, accounts, num_chars, task_config):
        """Begin a brand-new session, overwriting any old progress.

        Parameters
        ----------
        accounts : list[dict] | None
            List of ``{"email": ..., "password": ...}`` dicts, or *None* /
            empty for character-only mode (current login).
        num_chars : int
            Number of characters per account.
        task_config : dict
            ``{"build": bool, "expedition": bool, "territory": bool,
            "donation": bool}``
        """
        if not accounts:
            accounts_data = [self._make_account_entry(None, num_chars, task_config)]
        else:
            accounts_data = [
                self._make_account_entry(a["email"], num_chars, task_config)
                for a in accounts
            ]

        self._data = {
            "session_id": str(uuid.uuid4())[:8],
            "instance_id": self.instance_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "status": "in_progress",
            "accounts": accounts_data,
        }
        self._save()
        self.logger.info("Progress session started: %s", self._data["session_id"])

    def resume_session(self):
        """Load the existing session into memory for continued tracking.

        Returns *True* if a session was loaded, *False* otherwise.
        """
        data = self._load()
        if data is None or data.get("status") != "in_progress":
            return False
        self._data = data
        self.logger.info("Resuming progress session: %s", data.get("session_id"))
        return True

    def complete_session(self):
        if self._data is None:
            return
        self._data["status"] = "completed"
        self._save()
        self.logger.info("Progress session completed")

    def mark_interrupted(self):
        """Mark the current session as interrupted (still resumable)."""
        if self._data is None:
            return
        # Keep status as in_progress so it can be resumed
        self._save()

    def clear(self):
        """Delete the progress file entirely."""
        self._data = None
        try:
            os.remove(self._path)
        except FileNotFoundError:
            pass

    # ── account-level tracking ──────────────────────────────────

    def get_resume_account_index(self):
        """Return the 0-based index of the first account that is not yet
        completed, or *None* if all are done."""
        if self._data is None:
            return 0
        for idx, acct in enumerate(self._data.get("accounts", [])):
            if acct.get("status") != "completed":
                return idx
        return None

    def mark_account_started(self, account_index):
        acct = self._get_account(account_index)
        if acct and acct["status"] == "pending":
            acct["status"] = "in_progress"
            self._save()

    def mark_account_completed(self, account_index):
        acct = self._get_account(account_index)
        if acct:
            acct["status"] = "completed"
            self._save()

    def mark_account_skipped(self, account_index):
        acct = self._get_account(account_index)
        if acct:
            acct["status"] = "skipped"
            self._save()

    # ── character-level tracking ────────────────────────────────

    def get_resume_character_index(self, account_index):
        """Return the 0-based character index to resume from within an
        account.  Completed characters are skipped."""
        acct = self._get_account(account_index)
        if acct is None:
            return 0
        for ch in acct.get("characters", []):
            if ch.get("status") != "completed":
                return ch["index"]
        return None

    def is_character_completed(self, account_index, char_index):
        ch = self._get_character(account_index, char_index)
        return ch is not None and ch.get("status") == "completed"

    def mark_character_started(self, account_index, char_index):
        ch = self._get_character(account_index, char_index)
        if ch:
            ch["status"] = "in_progress"
            self._save()

    def mark_character_completed(self, account_index, char_index):
        ch = self._get_character(account_index, char_index)
        if ch:
            ch["status"] = "completed"
            self._save()

    def mark_character_failed(self, account_index, char_index):
        ch = self._get_character(account_index, char_index)
        if ch:
            ch["status"] = "failed"
            self._save()

    # ── task-level tracking (for UI display) ────────────────────

    def mark_task_completed(self, account_index, char_index, task_name):
        ch = self._get_character(account_index, char_index)
        if ch and task_name in ch.get("tasks", {}):
            ch["tasks"][task_name] = "completed"
            self._save()

    def mark_task_failed(self, account_index, char_index, task_name):
        ch = self._get_character(account_index, char_index)
        if ch and task_name in ch.get("tasks", {}):
            ch["tasks"][task_name] = "failed"
            self._save()

    # ── internals ───────────────────────────────────────────────

    def _get_account(self, index):
        if self._data is None:
            return None
        accounts = self._data.get("accounts", [])
        if 0 <= index < len(accounts):
            return accounts[index]
        return None

    def _get_character(self, account_index, char_index):
        acct = self._get_account(account_index)
        if acct is None:
            return None
        for ch in acct.get("characters", []):
            if ch["index"] == char_index:
                return ch
        return None

    @staticmethod
    def _make_account_entry(email, num_chars, task_config):
        return {
            "email": email,
            "status": "pending",
            "characters": [
                {
                    "index": i,
                    "status": "pending",
                    "tasks": {
                        "build": "pending" if task_config.get("build") else "skipped",
                        "expedition": "pending" if task_config.get("expedition") else "skipped",
                        "territory": "pending" if task_config.get("territory") else "skipped",
                        "donation": "pending" if task_config.get("donation") else "skipped",
                    },
                }
                for i in range(num_chars)
            ],
        }
