"""Tests for ProgressManager — session lifecycle, resume, and skip logic."""
import pytest

from progress_manager import ProgressManager

TASK_CFG = {"build": True, "expedition": True, "territory": True, "donation": True}
TASK_CFG_PARTIAL = {"build": True, "expedition": False, "territory": False, "donation": True}


@pytest.fixture(autouse=True)
def _isolated_progress(tmp_path, monkeypatch):
    """Redirect the progress dir to a temp folder for every test."""
    monkeypatch.setattr("progress_manager.PROGRESS_DIR", str(tmp_path))


def _make(iid="test-inst"):
    return ProgressManager(iid)


class TestNewSession:
    def test_start_creates_file(self):
        pm = _make()
        pm.start_session(None, 3, TASK_CFG)
        assert pm._data is not None
        assert pm._data["status"] == "in_progress"
        assert len(pm._data["accounts"]) == 1
        assert len(pm._data["accounts"][0]["characters"]) == 3

    def test_start_with_accounts(self):
        accounts = [{"email": "a@x.com", "password": "pw"}, {"email": "b@x.com", "password": "pw"}]
        pm = _make()
        pm.start_session(accounts, 2, TASK_CFG)
        assert len(pm._data["accounts"]) == 2
        assert pm._data["accounts"][0]["email"] == "a@x.com"
        assert len(pm._data["accounts"][1]["characters"]) == 2

    def test_disabled_tasks_are_skipped(self):
        pm = _make()
        pm.start_session(None, 1, TASK_CFG_PARTIAL)
        tasks = pm._data["accounts"][0]["characters"][0]["tasks"]
        assert tasks["build"] == "pending"
        assert tasks["expedition"] == "skipped"
        assert tasks["territory"] == "skipped"
        assert tasks["donation"] == "pending"


class TestCharacterTracking:
    def test_mark_completed_and_query(self):
        pm = _make()
        pm.start_session(None, 3, TASK_CFG)
        assert not pm.is_character_completed(0, 0)
        pm.mark_character_completed(0, 0)
        assert pm.is_character_completed(0, 0)
        assert not pm.is_character_completed(0, 1)

    def test_resume_character_index_skips_completed(self):
        pm = _make()
        pm.start_session(None, 5, TASK_CFG)
        pm.mark_character_completed(0, 0)
        pm.mark_character_completed(0, 1)
        assert pm.get_resume_character_index(0) == 2

    def test_resume_character_index_all_done(self):
        pm = _make()
        pm.start_session(None, 2, TASK_CFG)
        pm.mark_character_completed(0, 0)
        pm.mark_character_completed(0, 1)
        assert pm.get_resume_character_index(0) is None


class TestAccountTracking:
    def test_resume_account_skips_completed(self):
        accounts = [{"email": "a@x.com", "password": "p"}, {"email": "b@x.com", "password": "p"}]
        pm = _make()
        pm.start_session(accounts, 1, TASK_CFG)
        pm.mark_account_completed(0)
        assert pm.get_resume_account_index() == 1

    def test_resume_account_all_done(self):
        accounts = [{"email": "a@x.com", "password": "p"}]
        pm = _make()
        pm.start_session(accounts, 1, TASK_CFG)
        pm.mark_account_completed(0)
        assert pm.get_resume_account_index() is None


class TestSessionLifecycle:
    def test_complete_session(self):
        pm = _make()
        pm.start_session(None, 1, TASK_CFG)
        pm.complete_session()
        assert pm._data["status"] == "completed"
        assert not pm.has_resumable_session()

    def test_interrupted_session_is_resumable(self):
        pm = _make()
        pm.start_session(None, 3, TASK_CFG)
        pm.mark_character_completed(0, 0)
        pm.mark_interrupted()
        assert pm.has_resumable_session()

    def test_resume_loads_previous_state(self):
        pm1 = _make()
        pm1.start_session(None, 3, TASK_CFG)
        pm1.mark_character_completed(0, 0)
        pm1.mark_character_completed(0, 1)
        pm1.mark_interrupted()

        pm2 = _make()
        assert pm2.resume_session()
        assert pm2.is_character_completed(0, 0)
        assert pm2.is_character_completed(0, 1)
        assert not pm2.is_character_completed(0, 2)
        assert pm2.get_resume_character_index(0) == 2

    def test_clear_removes_file(self):
        pm = _make()
        pm.start_session(None, 1, TASK_CFG)
        pm.clear()
        assert not pm.has_resumable_session()

    def test_summary_text(self):
        pm = _make()
        pm.start_session(None, 5, TASK_CFG)
        pm.mark_character_completed(0, 0)
        pm.mark_character_completed(0, 1)
        summary = pm.get_session_summary()
        assert summary is not None
        assert "2/5" in summary

    def test_no_summary_when_completed(self):
        pm = _make()
        pm.start_session(None, 1, TASK_CFG)
        pm.complete_session()
        assert pm.get_session_summary() is None


class TestTaskTracking:
    def test_mark_task_completed(self):
        pm = _make()
        pm.start_session(None, 1, TASK_CFG)
        pm.mark_task_completed(0, 0, "build")
        tasks = pm._data["accounts"][0]["characters"][0]["tasks"]
        assert tasks["build"] == "completed"
        assert tasks["donation"] == "pending"

    def test_mark_task_failed(self):
        pm = _make()
        pm.start_session(None, 1, TASK_CFG)
        pm.mark_task_failed(0, 0, "expedition")
        tasks = pm._data["accounts"][0]["characters"][0]["tasks"]
        assert tasks["expedition"] == "failed"
