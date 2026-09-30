"""upload_r2.py's decisions, with the network call replaced.

`put()` is the only function that reaches R2 (through `wrangler`), so it is
patched out: these tests exercise which objects are chosen and when the
index.json guard refuses, and never contact a bucket.
"""

from __future__ import annotations

import json
import sys

import pytest

from sensisat.config import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import upload_r2  # noqa: E402


@pytest.fixture
def tree(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    (data / "index.json").write_text('{"v": 1}')
    (data / "a.tif").write_bytes(b"raster")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"index.json": upload_r2.digest(data / "index.json"),
                                    "a.tif": upload_r2.digest(data / "a.tif")}))
    monkeypatch.setattr(upload_r2, "DATA", data)
    monkeypatch.setattr(upload_r2, "MANIFEST", manifest)
    sent = []

    def fake_put(path, bucket, prefix=""):
        sent.append(path.name)
        return path, True, ""

    monkeypatch.setattr(upload_r2, "put", fake_put)
    return data, sent


def run(monkeypatch, *argv) -> int:
    monkeypatch.setattr(sys, "argv", ["upload_r2.py", *argv])
    return upload_r2.main()


def test_force_reuploads_an_unchanged_index(tree, monkeypatch):
    """--force alone must not trip the guard when index.json matches the record."""
    _, sent = tree
    assert run(monkeypatch, "--force") == 0
    assert sorted(sent) == ["a.tif", "index.json"]


def test_force_does_not_bypass_the_index_guard(tree, monkeypatch):
    """A changed index.json is refused under --force too; only --allow-index permits it."""
    data, sent = tree
    (data / "index.json").write_text('{"v": 2}')
    assert run(monkeypatch, "--force") == 3
    assert sent == []
    assert run(monkeypatch, "--force", "--allow-index") == 0
    assert "index.json" in sent


def test_unchanged_tree_uploads_nothing(tree, monkeypatch):
    _, sent = tree
    assert run(monkeypatch) == 0
    assert sent == []
