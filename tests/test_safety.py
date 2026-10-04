import os

import pytest

from core import safety
from core.safety import evaluate_command

symlinks = pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")


@pytest.fixture(autouse=True)
def _policy(ws, monkeypatch):
    monkeypatch.setattr(safety, "SHELL_UNRESTRICTED", False)
    monkeypatch.setattr(
        safety, "SHELL_ALLOWLIST",
        frozenset({"ls", "cat", "head", "grep", "find", "pwd", "echo", "git",
                   "pytest", "python", "python3"}),
    )
    monkeypatch.setattr(
        safety, "GIT_ALLOWED_SUBCOMMANDS",
        frozenset({"status", "diff", "log", "show", "branch", "rev-parse", "add",
                   "commit", "restore", "checkout", "stash"}),
    )


@pytest.mark.parametrize("cmd", [
    "ls", "ls -la", "pwd", "cat a.txt", "head -n 5 a.txt", "grep -rn foo .",
    "find . -name x.py", "pytest -q", "python script.py", "python -m pytest",
    "echo hello", "git status", "git diff --stat", "git log --oneline -5",
    "git commit -m 'fix: thing'", "git add .",
    "echo 'a && b'", "grep -E 'a|b' a.txt",   # operators inside quotes are literals
])
def test_allowed(cmd):
    d = evaluate_command(cmd)
    assert d.allowed, d.reason
    assert d.argv  # runs with shell=False


@pytest.mark.parametrize("cmd", [
    "ls; rm -rf /", "ls && rm -rf x", "ls || true", "cat a | sh", "echo hi > f",
    "echo hi >> f", "cat < f", "echo $(whoami)", "echo `id`", "echo ${HOME}", "ls &",
    "ls 2>&1",
])
def test_shell_operators_blocked(cmd):
    d = evaluate_command(cmd)
    assert not d.allowed
    assert "operators" in d.reason


@pytest.mark.parametrize("cmd", [
    "rm -rf x", "curl http://x", "wget http://x", "bash -c ls", "sh -c ls", "sudo ls",
    "/bin/ls", "./script.sh", "../x", "pip install x", "chmod 777 x", "env", "nc -l 1",
])
def test_not_in_allowlist_blocked(cmd):
    assert not evaluate_command(cmd).allowed


@pytest.mark.parametrize("cmd", ["", "   ", "echo 'unterminated"])
def test_empty_or_unparseable_blocked(cmd):
    assert not evaluate_command(cmd).allowed


@pytest.mark.parametrize("cmd", [
    "python -c 'import os'", "python3 -c 'print(1)'", "python -",
    "find . -exec rm {} ;", "find . -delete", "find . -fprint out.txt",
])
def test_dangerous_args_blocked(cmd):
    assert not evaluate_command(cmd).allowed


@pytest.mark.parametrize("cmd", [
    "git push origin main", "git config user.name x", "git clean -fd",
    "git reset --hard", "git remote add x y", "git clone http://x",
    "git -c core.pager=x status", "git -C / status", "git",
    "git checkout -f main", "git branch -D x", "git add -f x", "git log --output=out",
])
def test_git_restrictions(cmd):
    assert not evaluate_command(cmd).allowed


def test_git_gets_safe_prefix():
    d = evaluate_command("git status")
    assert d.argv[0] == "git"
    assert "core.fsmonitor=false" in d.argv
    assert "core.hooksPath=/dev/null" in d.argv
    assert d.argv[-1] == "status"
    assert d.env_extra["GIT_TERMINAL_PROMPT"] == "0"


@pytest.mark.parametrize("cmd", [
    "cat /etc/passwd", "cat ../x", "cat a/../../x", "cat ~/x", "ls /", "find / -name x",
    "grep -r foo /app", "head --file=/etc/passwd",
])
def test_paths_outside_workspace_blocked(cmd):
    d = evaluate_command(cmd)
    assert not d.allowed
    assert "outside" in d.reason or "allowed" in d.reason


def test_absolute_path_inside_workspace_ok(ws):
    assert evaluate_command(f"cat {ws}/a.txt").allowed


@symlinks
def test_symlink_escape_blocked(ws, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("x")
    (ws / "link").symlink_to(secret)
    assert not evaluate_command("cat link").allowed


def test_dot_git_paths_blocked(ws):
    (ws / ".git").mkdir()
    assert not evaluate_command("cat .git/config").allowed


def test_unrestricted_mode(monkeypatch):
    monkeypatch.setattr(safety, "SHELL_UNRESTRICTED", True)
    d = evaluate_command("ls; echo hi | cat")
    assert d.allowed and d.argv == ()  # empty argv => caller uses shell=True


def test_custom_allowlist(monkeypatch):
    monkeypatch.setattr(safety, "SHELL_ALLOWLIST", frozenset({"ls"}))
    assert evaluate_command("ls").allowed
    assert not evaluate_command("cat a.txt").allowed
