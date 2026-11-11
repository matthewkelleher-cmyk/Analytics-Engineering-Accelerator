"""Snowflake side of the loader: connect, create the raw table, merge a batch.

Each raw table holds the natural-key columns as text, the full API row as a VARIANT whose
values are the API's own text values (decision 8), a hash of the row to spot revisions, and
load metadata. Loading merges on the natural key, so running a load twice gives the same
result (decision 10).
"""

import os

DEFAULT_DATABASE = "TIL_DATA_ENGINEERING"
DEFAULT_RAW_SCHEMA = "MK_RAW"
INSERT_CHUNK = 10_000


class ConfigError(RuntimeError):
    """Missing or unusable connection settings."""


def column_name(field):
    return field.replace("-", "_").lower()


def qualified(table):
    database = os.environ.get("SNOWFLAKE_DATABASE") or DEFAULT_DATABASE
    schema = os.environ.get("SNOWFLAKE_RAW_SCHEMA") or DEFAULT_RAW_SCHEMA
    return f"{database}.{schema}.{table}"


def connect():
    """Open a connection from environment variables. Needs snowflake-connector-python."""
    required = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_ROLE", "SNOWFLAKE_WAREHOUSE"]
    key_path = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH")
    if not key_path:
        required.append("SNOWFLAKE_PASSWORD")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise ConfigError("Missing environment variables: " + ", ".join(missing))

    import snowflake.connector  # imported here so dry runs work without it

    settings = {
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        "role": os.environ["SNOWFLAKE_ROLE"],
        "warehouse": os.environ["SNOWFLAKE_WAREHOUSE"],
        "database": os.environ.get("SNOWFLAKE_DATABASE") or DEFAULT_DATABASE,
        "session_parameters": {"TIMEZONE": "UTC"},  # so every timestamp we write is UTC
    }
    if key_path:
        settings["private_key_file"] = key_path
        if os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"):
            settings["private_key_file_pwd"] = os.environ["SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"]
    else:
        settings["password"] = os.environ["SNOWFLAKE_PASSWORD"]
    return snowflake.connector.connect(**settings)


def ensure_table(conn, source):
    key_columns = ",\n  ".join(f"{column_name(f)} VARCHAR NOT NULL" for f in source.key_fields)
    conn.cursor().execute(f"""
CREATE TABLE IF NOT EXISTS {qualified(source.table)} (
  {key_columns},
  raw_row VARIANT NOT NULL,
  row_hash VARCHAR NOT NULL,
  _batch_id VARCHAR NOT NULL,
  _loaded_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
)""")


def max_period(conn, source):
    """Newest period already loaded, or None for an empty table (the load watermark)."""
    cur = conn.cursor()
    cur.execute(f"SELECT MAX(period) FROM {qualified(source.table)}")
    return cur.fetchone()[0]


def merge_rows(conn, source, prepared, batch_id):
    """Merge prepared rows (key values, row hash, row JSON) into the raw table.

    Returns (inserted, updated). A row already loaded with an identical hash is left alone.
    """
    keys = [column_name(f) for f in source.key_fields]
    target = qualified(source.table)
    stage = f"{target}_STAGE"
    cur = conn.cursor()
    cur.execute(f"CREATE OR REPLACE TEMPORARY TABLE {stage} "
                f"({', '.join(k + ' VARCHAR' for k in keys)}, row_hash VARCHAR, row_json VARCHAR)")
    placeholders = ", ".join(["%s"] * (len(keys) + 2))
    insert_sql = f"INSERT INTO {stage} VALUES ({placeholders})"
    for i in range(0, len(prepared), INSERT_CHUNK):
        cur.executemany(insert_sql, [(*k, h, j) for k, h, j in prepared[i:i + INSERT_CHUNK]])

    on = " AND ".join(f"t.{k} = s.{k}" for k in keys)
    cols = ", ".join(keys)
    cur.execute(f"""
MERGE INTO {target} t
USING (SELECT {cols}, row_hash, PARSE_JSON(row_json) AS raw_row FROM {stage}) s
ON {on}
WHEN MATCHED AND t.row_hash <> s.row_hash THEN UPDATE SET
  raw_row = s.raw_row, row_hash = s.row_hash,
  _batch_id = %s, _loaded_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT ({cols}, raw_row, row_hash, _batch_id)
  VALUES ({', '.join('s.' + k for k in keys)}, s.raw_row, s.row_hash, %s)""",
                (batch_id, batch_id))
    inserted, updated = cur.fetchone()
    cur.execute(f"DROP TABLE IF EXISTS {stage}")
    return inserted, updated


LOG_TABLE = "pipeline_run_log"


def ensure_log_table(conn):
    """The run log: one row per source per probe run, including runs that found nothing new."""
    conn.cursor().execute(f"""
CREATE TABLE IF NOT EXISTS {qualified(LOG_TABLE)} (
  run_id VARCHAR NOT NULL,
  run_at TIMESTAMP_NTZ NOT NULL DEFAULT SYSDATE(),
  source VARCHAR NOT NULL,
  route VARCHAR NOT NULL,
  newest_at_source VARCHAR,
  newest_loaded VARCHAR,
  decision VARCHAR NOT NULL,
  status VARCHAR NOT NULL,
  rows_fetched NUMBER,
  rows_inserted NUMBER,
  rows_updated NUMBER,
  shortfall NUMBER,
  batch_id VARCHAR,
  message VARCHAR,
  duration_seconds FLOAT
)""")


def write_log(conn, run_id, record):
    conn.cursor().execute(
        f"""INSERT INTO {qualified(LOG_TABLE)}
(run_id, source, route, newest_at_source, newest_loaded, decision, status, rows_fetched,
 rows_inserted, rows_updated, shortfall, batch_id, message, duration_seconds)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (run_id, record["source"], record["route"], record["newest_at_source"],
         record["newest_loaded"], record["decision"], record["status"],
         record["rows_fetched"], record["rows_inserted"], record["rows_updated"],
         record["shortfall"], record["batch_id"], record["message"],
         record["duration_seconds"]))