"""Unit tests for stubs_utils — including the None-safety fix."""
import os
import tempfile
import pytest


def test_save_stub_none_path():
    """save_stub(None, ...) must NOT crash (it should silently return)."""
    from utils.stubs_utils import save_stub
    save_stub(None, {"data": [1, 2, 3]})  # must not raise


def test_save_and_read_stub():
    from utils.stubs_utils import save_stub, read_stub
    data = [{"player": 1, "bbox": [0, 0, 10, 10]}, {"player": 2, "bbox": [20, 20, 30, 30]}]
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "test_stub.pkl")
        save_stub(path, data)
        loaded = read_stub(True, path)
    assert loaded == data


def test_read_stub_disabled():
    """read_stub with read_from_stub=False must return None."""
    from utils.stubs_utils import read_stub
    result = read_stub(False, "/nonexistent/path.pkl")
    assert result is None


def test_read_stub_missing_file():
    """read_stub with read_from_stub=True but missing file must return None."""
    from utils.stubs_utils import read_stub
    result = read_stub(True, "/nonexistent/path.pkl")
    assert result is None


def test_save_stub_creates_parent_dirs():
    from utils.stubs_utils import save_stub, read_stub
    with tempfile.TemporaryDirectory() as tmp:
        deep_path = os.path.join(tmp, "a", "b", "c", "stub.pkl")
        save_stub(deep_path, [1, 2, 3])
        assert os.path.exists(deep_path)
