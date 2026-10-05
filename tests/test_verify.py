import shutil

import pytest

from agent.verify import DIRTY_MESSAGE, FAILED_MESSAGE, VerifyTracker
from core import safety
from core.tools import shell
from core.tools import verify as tools_verify

OK = {"success": True}
TESTS_PASS = {"success": True, "returncode": 0, "no_tests": False}
TESTS_FAIL = {"success": False, "returncode": 1, "no_tests": False}


# ---- VerifyTracker -------------------------------------------------------

def test_no_changes_no_nudge():
    t = VerifyTracker()
    t.observe("read_file", OK)
    t.observe("list_files", OK)
    assert t.pending_message() is None


def test_edit_without_tests_nudges():
    t = VerifyTracker()
    t.observe("write_file", OK)
    assert t.pending_message() == DIRTY_MESSAGE


def test_failed_edit_does_not_dirty():
    t = VerifyTracker()
    t.observe("write_file", {"success": False, "error": "nope"})
    assert t.pending_message() is None


def test_edit_then_passing_tests_is_clean():
    t = VerifyTracker()
    t.observe("create_file", OK)
    t.observe("run_tests", TESTS_PASS)
    assert t.pending_message() is None


def test_failing_tests_nudge_to_fix_then_clean():
    t = VerifyTracker()
    t.observe("write_file", OK)
    t.observe("run_tests", TESTS_FAIL)
    assert t.pending_message() == FAILED_MESSAGE
    t.observe("write_file", OK)            # attempted fix
    assert t.pending_message() == DIRTY_MESSAGE
    t.observe("run_tests", TESTS_PASS)
    assert t.pending_message() is None


def test_nudges_are_capped():
    t = VerifyTracker(max_nudges=2)
    t.observe("write_file", OK)
    assert t.pending_message() is not None
    assert t.pending_message() is not None
    assert t.pending_message() is None     # never loops forever


def test_no_tests_or_blocked_runner_does_not_nag():
    t = VerifyTracker()
    t.observe("write_file", OK)
    t.observe("run_tests", {"success": False, "returncode": 5, "no_tests": True})
    assert t.pending_message() is None

    t.observe("write_file", OK)
    t.observe("run_tests", {"success": False, "error": "Blocked by shell policy: x"})
    assert t.pending_message() is None


def test_disabled_never_nudges():
    t = VerifyTracker(enabled=False)
    t.observe("write_file", OK)
    assert t.pending_message() is None


def test_new_turn_resets():
    t = VerifyTracker()
    t.observe("write_file", OK)
    t.new_turn()
    assert t.pending_message() is None


def test_from_env(monkeypatch):
    monkeypatch.setenv("AUTO_VERIFY", "0")
    monkeypatch.setenv("VERIFY_MAX_NUDGES", "5")
    t = VerifyTracker.from_env()
    assert t.enabled is False and t.max_nudges == 5

    monkeypatch.setenv("AUTO_VERIFY", "1")
    monkeypatch.setenv("VERIFY_MAX_NUDGES", "abc")
    t = VerifyTracker.from_env()
    assert t.enabled is True and t.max_nudges == 2


# ---- pytest output parsing ----------------------------------------------

def test_parse_failed_run():
    out = (
        "F.\n"
        "=== FAILURES ===\n"
        "___ test_bad ___\n"
        "E   assert 1 == 2\n"
        "=== short test summary info ===\n"
        "FAILED test_x.py::test_bad - assert 1 == 2\n"
        "1 failed, 1 passed in 0.03s\n"
    )
    p = tools_verify.parse_pytest_output(out)
    assert p["summary"] == "1 failed, 1 passed in 0.03s"
    assert p["counts"] == {"failed": 1, "passed": 1}
    assert p["failed_tests"] == ["FAILED test_x.py::test_bad - assert 1 == 2"]


def test_parse_decorated_summary_and_errors():
    p = tools_verify.parse_pytest_output("=== 2 passed, 1 error, 3 warnings in 0.1s ===")
    assert p["counts"] == {"passed": 2, "errors": 1, "warnings": 3}


def test_parse_no_tests():
    p = tools_verify.parse_pytest_output("no tests ran in 0.01s")
    assert "no tests ran" in p["summary"]
    assert p["counts"] == {}


def test_run_tests_rejects_option_like_path():
    assert not tools_verify.run_tests(path="--collect-only")["success"]


# ---- real pytest run -----------------------------------------------------

@pytest.mark.skipif(shutil.which("pytest") is None, reason="pytest executable not on PATH")
def test_run_tests_integration(ws, monkeypatch):
    monkeypatch.setattr(safety, "SHELL_UNRESTRICTED", False)
    monkeypatch.setattr(shell, "WORKSPACE", ws)
    (ws / "test_x.py").write_text(
        "def test_ok():\n    assert True\n\n"
        "def test_bad():\n    assert 1 == 2\n"
    )

    r = tools_verify.run_tests()
    assert r["success"] is False
    assert r["counts"].get("failed") == 1 and r["counts"].get("passed") == 1
    assert any("test_bad" in t for t in r["failed_tests"])

    r2 = tools_verify.run_tests(keyword="test_ok")
    assert r2["success"] is True
