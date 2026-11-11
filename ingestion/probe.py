"""Freshness probe: ask EIA what is newest, load only the sources that have something new.

For each source this asks the data endpoint for its newest period (one small call), compares
it with the newest period already in Snowflake, and runs that source's load only when EIA is
ahead. Every decision, including "nothing new", is written to the run log table
(MK_RAW.PIPELINE_RUN_LOG). One source failing does not stop the others; the exit code is 1
if any failed.

    python ingestion/probe.py                    # probe every source, load what is newer
    python ingestion/probe.py --dry-run          # decide only: no loads, no log rows
    python ingestion/probe.py --source spot_prices --force   # load even if nothing is newer

The probe sees only a newer maximum period. A respondent that lags behind the others is
picked up the next time any load runs, because each load re-reads a trailing window.
"""

import argparse
import json
import logging
import os
import sys
import time
import uuid

from eia_client import EiaClient
from loader import load_env, run as run_load, window_start
from snowflake_io import connect, ensure_log_table, ensure_table, max_period, write_log
from sources import SOURCES

log = logging.getLogger("probe")
LOAD_DECISIONS = {"initial_load", "load", "forced_load"}


def run_context(env=None):
    """Where this run came from: (triggered_by, run_url). The URL is set on GitHub only."""
    env = os.environ if env is None else env
    if env.get("GITHUB_ACTIONS") == "true":
        event = env.get("GITHUB_EVENT_NAME", "unknown")
        triggered_by = {"schedule": "github_actions_schedule",
                        "workflow_dispatch": "github_actions_manual"}.get(
                            event, f"github_actions_{event}")
        server = env.get("GITHUB_SERVER_URL", "https://github.com")
        url = f"{server}/{env.get('GITHUB_REPOSITORY')}/actions/runs/{env.get('GITHUB_RUN_ID')}"
        return triggered_by, url
    if env.get("CODESPACES") == "true":
        return "codespaces", None
    return "local", None


def decide(newest_at_source, newest_loaded, force=False):
    """What to do for one source. Periods compare as text: they share a format per source."""
    if newest_at_source is None:
        return "no_data_at_source"
    if newest_loaded is None:
        return "initial_load"
    if force:
        return "forced_load"
    return "load" if newest_at_source > newest_loaded else "skip"


def probe_source(source, client, conn, *, dry_run=False, force=False):
    """Probe one source and (unless dry_run) load it. Returns the run-log record."""
    started = time.monotonic()
    record = {"source": source.name, "route": source.route, "newest_at_source": None,
              "newest_loaded": None, "decision": "error", "status": "error",
              "rows_fetched": None, "rows_inserted": None, "rows_updated": None,
              "shortfall": None, "batch_id": None, "message": None,
              "duration_seconds": None}
    try:
        ensure_table(conn, source)
        record["newest_at_source"] = client.newest_period(
            source.route, source.frequency, source.data_cols, source.facets)
        record["newest_loaded"] = max_period(conn, source)
        record["decision"] = decide(record["newest_at_source"], record["newest_loaded"], force)

        if record["decision"] not in LOAD_DECISIONS:
            record["status"] = "skipped"
            if record["decision"] == "no_data_at_source":
                record["message"] = "EIA returned no rows for this filter"
        elif dry_run:
            record["status"] = "dry_run"
        else:
            start = window_start(source, record["newest_loaded"])
            summary = run_load(source, start=start, dry_run=False, max_pages=None,
                               client=client, conn=conn)
            record.update(status="success", rows_fetched=summary["fetched"],
                          rows_inserted=summary["inserted"], rows_updated=summary["updated"],
                          shortfall=summary["shortfall"], batch_id=summary["batch_id"])
    except Exception as exc:  # one failing source must not stop the others
        record["status"] = "error"
        record["message"] = f"{type(exc).__name__}: {exc}"[:500]
        log.error("%s failed: %s", source.name, record["message"])
    record["duration_seconds"] = round(time.monotonic() - started, 1)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description="Probe EIA for new data and load what is newer.")
    parser.add_argument("--source", action="append", choices=sorted(SOURCES),
                        help="probe only this source (repeatable); default is all")
    parser.add_argument("--dry-run", action="store_true",
                        help="decide only: no loads and no run-log rows")
    parser.add_argument("--force", action="store_true",
                        help="load even if EIA has nothing newer")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_env()

    run_id = uuid.uuid4().hex
    triggered_by, run_url = run_context()
    names = args.source or list(SOURCES)
    conn = None
    try:
        client = EiaClient()
        conn = connect()
        if not args.dry_run:
            ensure_log_table(conn)
        records = []
        for name in names:
            record = probe_source(SOURCES[name], client, conn,
                                  dry_run=args.dry_run, force=args.force)
            record.update(triggered_by=triggered_by, run_url=run_url)
            records.append(record)
            if not args.dry_run:
                write_log(conn, run_id, record)
            log.info("%s", json.dumps(record))
    except Exception as exc:
        log.error("probe could not run: %s: %s", type(exc).__name__, exc)
        return 1
    finally:
        if conn is not None:
            conn.close()
    failed = [r["source"] for r in records if r["status"] == "error"]
    log.info("run %s finished: %s", run_id,
             ", ".join(f"{r['source']}={r['decision']}/{r['status']}" for r in records))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())