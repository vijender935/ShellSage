import os

import pytest

from core import workspace as w
from core.workspace import PathEscapeError, rel_to_workspace, safe_path

symlinks = pytest.mark.skipif(
    os.name == "nt", reason="symlinks need privileges on Windows"
)


def test_relative_path_inside(ws):
    assert safe_path("a/b.txt") == ws / "a" / "b.txt"


@pytest.mark.parametrize("empty", [None, "", "   ", "."])
def test_empty_means_workspace_root(ws, empty):
    assert safe_path(empty) == ws


@pytest.mark.parametrize("bad", ["..", "../x", "a/../../x", "a/b/../../../x"])
def test_dotdot_escape_blocked(ws, bad):
    with pytest.raises(PathEscapeError):
        safe_path(bad)


def test_dotdot_that_stays_inside_is_ok(ws):
    assert safe_path("a/../b.txt") == ws / "b.txt"


def test_absolute_outside_blocked(ws, tmp_path):
    with pytest.raises(PathEscapeError):
        safe_path(str(tmp_path / "elsewhere" / "x"))


def test_absolute_inside_ok(ws):
    assert safe_path(str(ws / "x.txt")) == ws / "x.txt"


def test_sibling_with_same_prefix_blocked(ws):
    evil = str(ws) + "-evil/x"
    with pytest.raises(PathEscapeError):
        safe_path(evil)


def test_null_byte_stripped(ws):
    assert safe_path("a\x00.txt").parent == ws


@symlinks
def test_symlink_to_outside_dir_blocked(ws, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("top secret")
    (ws / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PathEscapeError):
        safe_path("link/secret.txt")


@symlinks
def test_symlink_to_outside_file_blocked(ws, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret")
    (ws / "sneaky.txt").symlink_to(secret)
    with pytest.raises(PathEscapeError):
        safe_path("sneaky.txt")


@symlinks
def test_symlink_inside_workspace_rejected(ws):
    (ws / "real").mkdir()
    (ws / "alias").symlink_to(ws / "real", target_is_directory=True)
    with pytest.raises(PathEscapeError):
        safe_path("alias/f.txt")


def test_extra_root_allowed(ws, tmp_path, monkeypatch):
    extra = (tmp_path / "extra").resolve()
    extra.mkdir()
    monkeypatch.setattr(w, "ALLOWED_ROOTS", [ws, extra])
    assert safe_path(str(extra / "f.txt")) == extra / "f.txt"
    with pytest.raises(PathEscapeError):
        safe_path(str(tmp_path / "other"))


def test_rel_to_workspace(ws):
    assert rel_to_workspace(ws) == "."
    assert rel_to_workspace(ws / "a" / "b.txt") == os.path.join("a", "b.txt")
