"""Shared command line and load logic behind the three load_*.py scripts.

For one source it works out how far back to start, pulls the rows from EIA, checks the
natural key, and merges them into the raw table. Re-running gives the same result.

    python ingestion/load_spot_prices.py                 # incremental: trailing window
    python ingestion/load_spot_prices.py --full          # everything from the first period
    python ingestion/load_spot_prices.py --dry-run       # fetch and check only; no Snowflake
"""

import argparse
import hashlib
import json
import logging
import pathlib
import sys
import uuid
from datetime import date, timedelta

from eia_client import EiaClient, EiaError
from sources import SOURCES

log = logging.getLogger("loader")
FLUSH_EVERY = 50_000


class KeyError_(ValueError):
    """The natural key is missing from a row, or two rows share it."""


def load_env():
    """Read .env if python-dotenv is installed; warn (not fail silently) if it is not."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        if pathlib.Path(".env").exists():
            log.warning(".env exists but python-dotenv is not installed, so it was not read")
        return
    load_dotenv()


def window_start(source, newest_loaded, window=None):
    """First period to reload: the newest loaded period minus the trailing window."""
    window = source.window if window is None else window
    if newest_loaded is None:
        return source.first_period
    if source.window_unit == "months":
        year, month = int(newest_loaded[:4]), int(newest_loaded[5:7])
        index = year * 12 + (month - 1) - window
        return f"{index // 12:04d}-{index % 12 + 1:02d}"
    return (date.fromisoformat(newest_loaded[:10]) - timedelta(days=window)).isoformat()


def prepare(source, row):
    """Return (key values, row hash, row JSON) for one API row, checking its key fields."""
    missing = [f for f in source.key_fields if row.get(f) in (None, "")]
    if missing:
        raise KeyError_(f"key field(s) {missing} missing or empty; the row has fields "
                        f"{sorted(row)}. Fix key_fields in sources.py.")
    text = json.dumps(row, sort_keys=True, separators=(",", ":"))
    key = tuple(str(row[f]) for f in source.key_fields)
    return key, hashlib.sha256(text.encode()).hexdigest(), text


def run(source, *, start, dry_run, max_pages, client, conn=None):
    """Fetch, check and (unless dry_run) merge. Returns a summary dict."""
    batch_id = uuid.uuid4().hex
    seen, buffer = set(), []
    fetched = inserted = updated = 0
    first_period = last_period = first_row = None
    duplicates = []

    def flush():
        nonlocal inserted, updated, buffer
        if buffer and conn is not None:
            ins, upd = merge_rows(conn, source, buffer, batch_id)
            inserted, updated = inserted + ins, updated + upd
        buffer = []

    for row in client.fetch_rows(source.route, source.frequency, source.data_cols,
                                 source.facets, source.sort_cols, start=start,
                                 max_pages=max_pages,
                                 allow_shortfall=source.allow_shortfall):
        key, row_hash, text = prepare(source, row)
        if key in seen:
            duplicates.append(key)
        seen.add(key)
        fetched += 1
        first_row = first_row or row
        first_period = first_period or row["period"]
        last_period = row["period"]
        buffer.append((key, row_hash, text))
        if len(buffer) >= FLUSH_EVERY and not duplicates:
            flush()

    if duplicates:
        raise KeyError_(f"{len(duplicates)} rows share a natural key "
                        f"{source.key_fields}, for example {duplicates[0]}. "
                        "Nothing from this batch was merged after the first duplicate; "
                        "choose a key that is unique.")
    flush()
    reported = client.last_total
    return {"source": source.name, "batch_id": batch_id, "start": start,
            "fetched": fetched, "api_reported_total": reported,
            "shortfall": None if max_pages or reported is None else reported - fetched, "first_period": first_period, "last_period": last_period,
            "inserted": inserted, "updated": updated, "dry_run": dry_run,
            "example_row": first_row if dry_run else None}


def main(source_name, argv=None):
    source = SOURCES[source_name]
    parser = argparse.ArgumentParser(description=f"Load EIA {source.route} into Snowflake.")
    parser.add_argument("--full", action="store_true", help="load everything, ignoring the watermark")
    parser.add_argument("--start", help="override the first period (e.g. 2026-01 or 2026-01-15)")
    parser.add_argument("--window", type=int, help=f"trailing window to reload "
                        f"(default {source.window} {source.window_unit})")
    parser.add_argument("--max-pages", type=int, help="stop after this many pages (testing)")
    parser.add_argument("--dry-run", action="store_true",
                        help="fetch and check the key only; do not touch Snowflake")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_env()

    conn = None
    try:
        client = EiaClient()
        if args.dry_run:
            start = args.start or source.first_period
        else:
            from snowflake_io import connect, ensure_table, max_period
            conn = connect()
            ensure_table(conn, source)
            if args.full:
                start = args.start or source.first_period
            elif args.start:
                start = args.start
            else:
                start = window_start(source, max_period(conn, source), args.window)
        summary = run(source, start=start, dry_run=args.dry_run, max_pages=args.max_pages,
                      client=client, conn=conn)
    except (EiaError, KeyError_, ValueError, RuntimeError) as exc:
        log.error("%s", exc)
        return 1
    finally:
        if conn is not None:
            conn.close()
    log.info("done: %s", json.dumps(summary, default=str))
    return 0


# imported late so a dry run does not need the Snowflake connector installed
def merge_rows(*args, **kwargs):
    from snowflake_io import merge_rows as _merge
    return _merge(*args, **kwargs)