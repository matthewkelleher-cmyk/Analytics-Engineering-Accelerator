"""Offline tests for the freshness probe: no network, no Snowflake."""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ingestion"))

import probe  # noqa: E402
from eia_client import EiaError  # noqa: E402
from sources import SOURCES  # noqa: E402

SPOT = SOURCES["spot_prices"]
CRUDE = SOURCES["crude_imports"]


class FakeClient:
    def __init__(self, newest):
        self.newest = newest

    def newest_period(self, *args):
        if isinstance(self.newest, Exception):
            raise self.newest
        return self.newest


@pytest.fixture
def stubs(monkeypatch):
    """Replace the Snowflake calls; record whether a load ran."""
    state = {"loaded": None, "calls": []}
    monkeypatch.setattr(probe, "ensure_table", lambda conn, source: None)
    monkeypatch.setattr(probe, "max_period", lambda conn, source: state["loaded"])

    def fake_run(source, **kwargs):
        state["calls"].append(kwargs)
        return {"fetched": 22, "inserted": 4, "updated": 1, "shortfall": 0, "batch_id": "b1"}

    monkeypatch.setattr(probe, "run_load", fake_run)
    return state


@pytest.mark.parametrize("at_source, loaded, force, expected", [
    (None, "2026-10-27", False, "no_data_at_source"),
    ("2026-11-03", None, False, "initial_load"),
    ("2026-11-03", "2026-10-27", False, "load"),
    ("2026-11-03", "2026-11-03", False, "skip"),
    ("2026-10-27", "2026-11-03", False, "skip"),
    ("2026-11-03", "2026-11-03", True, "forced_load"),
])
def test_decide(at_source, loaded, force, expected):
    assert probe.decide(at_source, loaded, force) == expected


def test_nothing_newer_is_skipped_and_nothing_is_loaded(stubs):
    stubs["loaded"] = "2026-11-03"
    record = probe.probe_source(SPOT, FakeClient("2026-11-03"), conn=None)
    assert (record["decision"], record["status"]) == ("skip", "skipped")
    assert stubs["calls"] == []


def test_newer_data_triggers_a_load_from_the_trailing_window(stubs):
    stubs["loaded"] = "2026-10-27"
    record = probe.probe_source(SPOT, FakeClient("2026-11-03"), conn=None)
    assert (record["decision"], record["status"]) == ("load", "success")
    assert stubs["calls"][0]["start"] == "2026-10-13"       # 14 days before the newest loaded
    assert (record["rows_fetched"], record["rows_inserted"], record["rows_updated"]) == (22, 4, 1)
    assert record["batch_id"] == "b1"


def test_empty_table_gets_an_initial_load(stubs):
    record = probe.probe_source(CRUDE, FakeClient("2026-08"), conn=None)
    assert record["decision"] == "initial_load"
    assert stubs["calls"][0]["start"] == "2009-01"


def test_dry_run_decides_but_does_not_load(stubs):
    stubs["loaded"] = "2026-10-27"
    record = probe.probe_source(SPOT, FakeClient("2026-11-03"), conn=None, dry_run=True)
    assert (record["decision"], record["status"]) == ("load", "dry_run")
    assert stubs["calls"] == []


def test_a_failing_probe_is_recorded_not_raised(stubs):
    record = probe.probe_source(SPOT, FakeClient(EiaError("HTTP 500 for /x")), conn=None)
    assert record["status"] == "error" and "HTTP 500" in record["message"]
    assert stubs["calls"] == []


def test_a_failing_load_is_recorded_not_raised(stubs, monkeypatch):
    stubs["loaded"] = "2026-10-27"

    def boom(source, **kwargs):
        raise RuntimeError("merge failed")

    monkeypatch.setattr(probe, "run_load", boom)
    record = probe.probe_source(SPOT, FakeClient("2026-11-03"), conn=None)
    assert record["status"] == "error" and "merge failed" in record["message"]