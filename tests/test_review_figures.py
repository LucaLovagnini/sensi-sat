"""The figure review's attestation must record a named reviewer and three judgements.

Everything here writes to a temporary copy: the real `docs/figures-review.json` is
never touched, and the figure set is stubbed so the test does not depend on the
documents or on a build.
"""

from __future__ import annotations

import json
import sys

import pytest

from sensisat.config import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import review_figures as rf  # noqa: E402

FULL = {k: "read, and it holds" for k in rf.JUDGEMENTS}


@pytest.fixture
def record(tmp_path, monkeypatch):
    path = tmp_path / "figures-review.json"
    monkeypatch.setattr(rf, "REVIEW", path)
    monkeypatch.setattr(rf, "figure_set", lambda: {"tokens": {}, "sections": {}, "generated": {},
                                                   "declarations": {}, "registry": [], "live": None})
    monkeypatch.setattr(rf, "fingerprint", lambda: "f" * 64)
    return path


def test_complete_attestation_is_current(record):
    assert rf.attest("Luca", FULL) == 0
    assert rf.check() == 0


@pytest.mark.parametrize("reviewer, judgements", [
    ("", FULL),
    ("   ", FULL),
    ("Luca", {**FULL, "registry_holds_no_live_claim": ""}),
    ("Luca", {**FULL, "declarations_plausible": None}),
    ("Luca", {k: v for k, v in FULL.items() if k != "generated_from_right_fact"}),
])
def test_attest_refuses_an_incomplete_review(record, reviewer, judgements):
    assert rf.attest(reviewer, judgements) == 5
    assert not record.exists()


def test_check_reports_an_incomplete_record_as_stale(record):
    """A matching fingerprint is not enough: the record must say who judged what."""
    assert rf.attest("Luca", FULL) == 0
    rec = json.loads(record.read_text())
    rec["judgements"]["declarations_plausible"] = " "
    record.write_text(json.dumps(rec))
    assert rf.check() == 5
