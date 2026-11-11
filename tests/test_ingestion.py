"""Offline tests for the ingestion code: a fake EIA session and a fake Snowflake connection."""

import pathlib
import sys

import pytest
import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ingestion"))

import loader  # noqa: E402
import snowflake_io  # noqa: E402
from eia_client import PAGE_SIZE, EiaClient, EiaError  # noqa: E402
from sources import SOURCES  # noqa: E402

SECRET = "SECRET-KEY-123"


class FakeResponse:
    def __init__(self, status=200, body=None, text=""):
        self.status_code, self._body, self.text = status, body or {}, text

    def json(self):
        return self._body


class FakeSession:
    """Serves `total` spot-price rows page by page, optionally failing first."""

    def __init__(self, total, failures=()):
        self.total, self.failures, self.calls = total, list(failures), []

    def get(self, url, params, timeout):
        self.calls.append(dict(params))
        if self.failures:
            outcome = self.failures.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return FakeResponse(outcome, text="busy")
        offset, length = params["offset"], params["length"]
        rows = [{"period": f"2026-01-{1 + i // 2:02d}", "series": "RWTC" if i % 2 == 0 else "RBRTE",
                 "value": str(i)} for i in range(offset, min(offset + length, self.total))]
        return FakeResponse(200, {"response": {"total": str(self.total), "data": rows}})


def client(session):
    return EiaClient(api_key=SECRET, session=session, pause=0, sleep=lambda s: None)


def test_pages_through_every_row_in_order():
    session = FakeSession(12_000)
    rows = list(client(session).fetch_rows("petroleum/pri/spt", "daily", ("value",),
                                           {"series": ["RWTC", "RBRTE"]}, ("period", "series")))
    assert len(rows) == 12_000
    assert [c["offset"] for c in session.calls] == [0, 5000, 10000]
    assert all(c["length"] == PAGE_SIZE for c in session.calls)
    first = session.calls[0]
    assert first["sort[0][column]"] == "period" and first["sort[1][column]"] == "series"
    assert first["facets[series][]"] == ["RWTC", "RBRTE"]


def test_retries_rate_limit_then_succeeds():
    session = FakeSession(10, failures=[429, requests.ConnectionError(SECRET)])
    rows = list(client(session).fetch_rows("r", "daily", ("value",), {}, ("period",)))
    assert len(rows) == 10 and len(session.calls) == 3


def test_gives_up_and_never_leaks_the_key():
    session = FakeSession(10, failures=[503] * 5)
    with pytest.raises(EiaError) as err:
        list(client(session).fetch_rows("r", "daily", ("value",), {}, ("period",)))
    assert SECRET not in str(err.value)
    session = FakeSession(10, failures=[requests.ConnectionError(f"url with {SECRET}")] * 5)
    with pytest.raises(EiaError) as err:
        list(client(session).fetch_rows("r", "daily", ("value",), {}, ("period",)))
    assert SECRET not in str(err.value)


def test_missing_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    with pytest.raises(EiaError, match="EIA_API_KEY"):
        EiaClient()


def test_window_start():
    crude, spot = SOURCES["crude_imports"], SOURCES["spot_prices"]
    assert loader.window_start(crude, None) == "2009-01"
    assert loader.window_start(crude, "2026-08") == "2026-05"
    assert loader.window_start(crude, "2026-02") == "2025-11"   # crosses a year
    assert loader.window_start(spot, "2026-10-27") == "2026-10-13"
    assert loader.window_start(spot, None) is None
    assert loader.window_start(spot, "2026-10-27", window=3) == "2026-10-24"


def test_row_missing_a_key_field_is_reported():
    with pytest.raises(loader.KeyError_, match="series"):
        loader.prepare(SOURCES["spot_prices"], {"period": "2026-01-01", "value": "1"})


def test_dry_run_reports_without_touching_snowflake():
    summary = loader.run(SOURCES["spot_prices"], start=None, dry_run=True, max_pages=None,
                         client=client(FakeSession(7_000)))
    assert summary["fetched"] == 7_000 and summary["inserted"] == 0
    assert summary["example_row"]["series"] == "RWTC"


def test_duplicate_natural_key_fails_loudly():
    class Dup(FakeSession):
        def get(self, url, params, timeout):
            row = {"period": "2026-01-01", "series": "RWTC", "value": "1"}
            return FakeResponse(200, {"response": {"total": "2", "data": [row, dict(row)]}})

    with pytest.raises(loader.KeyError_, match="share a natural key"):
        loader.run(SOURCES["spot_prices"], start=None, dry_run=True, max_pages=None,
                   client=client(Dup(2)))


class FakeCursor:
    def __init__(self, log):
        self.log = log

    def execute(self, sql, params=None):
        self.log.append(("execute", " ".join(sql.split()), params))

    def executemany(self, sql, rows):
        self.log.append(("executemany", sql, list(rows)))

    def fetchone(self):
        return (3, 1)


class FakeConn:
    def __init__(self):
        self.log = []

    def cursor(self):
        return FakeCursor(self.log)


def test_merge_sql_and_counts(monkeypatch):
    monkeypatch.delenv("SNOWFLAKE_DATABASE", raising=False)
    monkeypatch.delenv("SNOWFLAKE_RAW_SCHEMA", raising=False)
    conn = FakeConn()
    prepared = [(("2026-01-01", "RWTC"), "h1", "{}"), (("2026-01-01", "RBRTE"), "h2", "{}")]
    inserted, updated = snowflake_io.merge_rows(conn, SOURCES["spot_prices"], prepared, "batch1")
    assert (inserted, updated) == (3, 1)
    sql = [entry[1] for entry in conn.log if entry[0] == "execute"]
    assert "TIL_DATA_ENGINEERING.MK_RAW.raw_eia_spot_prices_STAGE" in sql[0]
    merge = next(s for s in sql if s.startswith("MERGE"))
    assert "ON t.period = s.period AND t.series = s.series" in merge
    assert "t.row_hash <> s.row_hash" in merge
    assert conn.log[1][0] == "executemany" and len(conn.log[1][2]) == 2


class ShortPageSession(FakeSession):
    """The API reports `total` rows but returns fewer on the last page."""

    def get(self, url, params, timeout):
        response = super().get(url, params, timeout)
        if params["offset"] == 5000:
            response._body["response"]["data"] = response._body["response"]["data"][:-3]
        return response


def test_short_page_is_logged_and_the_shortfall_reported(caplog):
    with pytest.raises(EiaError, match="received 5997 rows in 2 pages"):
        list(client(ShortPageSession(6_000)).fetch_rows("r", "daily", ("value",), {}, ("period",)))
    assert "offset 5000 returned 997 of 1000 expected rows" in caplog.text


def test_a_tolerant_source_reports_the_shortfall_instead_of_failing():
    session = ShortPageSession(6_000)
    c = client(session)
    rows = list(c.fetch_rows("r", "daily", ("value",), {}, ("period",), allow_shortfall=True))
    assert len(rows) == 5_997 and c.last_total == 6_000


def test_run_summary_includes_the_shortfall():
    source = SOURCES["crude_imports"]
    assert source.allow_shortfall is True

    class Crude(FakeSession):
        def get(self, url, params, timeout):
            rows = [{"period": "2026-01", "originId": f"o{i}", "destinationId": "d",
                     "gradeId": "g", "quantity": "1"} for i in range(3)]
            return FakeResponse(200, {"response": {"total": "5", "data": rows}})

    summary = loader.run(source, start="2026-01", dry_run=True, max_pages=None,
                         client=client(Crude(5)))
    assert summary["fetched"] == 3 and summary["api_reported_total"] == 5
    assert summary["shortfall"] == 2