"""Exploratory script for the EIA API v2: electricity / RTO (grid operating data).

Throwaway exploration, not part of the pipeline. Answers:
  1. What routes exist under electricity/rto?
  2. What frequencies does each offer, and what period range does it cover?
  3. How does the raw JSON look?

Usage (from anywhere; paths are anchored to this file):
    python eia_explore_electricity.py                      # walk the route tree, save the catalog
    python eia_explore_electricity.py --sample ROUTE ...   # sample chosen leaf routes

Example after reading the catalog:
    python eia_explore_electricity.py --sample electricity/rto/daily-fuel-type-data

Output goes to raw_samples_electricity/ next to this file (gitignored).
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://api.eia.gov/v2"
OUT_DIR = Path(__file__).parent / "raw_samples_electricity"

ROOT_ROUTES = ["electricity/rto"]
SAMPLE_ROWS = 5

# The key lives in a Codespaces secret (EAI_API_KEY); EIA_API_KEY is accepted as a fallback.
API_KEY = os.environ.get("EAI_API_KEY") or os.environ.get("EIA_API_KEY")


def get(path: str, **params) -> dict:
    """GET one EIA endpoint and return the parsed JSON. Never prints the key."""
    params["api_key"] = API_KEY
    resp = requests.get(f"{BASE}/{path.strip('/')}", params=params, timeout=30)
    if not resp.ok:
        sys.exit(f"HTTP {resp.status_code} for /{path}: {resp.text[:300]}")
    time.sleep(0.2)  # EIA throttles heavy callers; keep a short pause between calls
    return resp.json()


def walk(route: str, catalog: dict, depth: int = 0) -> None:
    """Recursively walk the route tree, recording each data (leaf) route's metadata."""
    meta = get(route)["response"]
    indent = "  " * depth
    children = meta.get("routes")
    if children:
        print(f"{indent}{route}/  ({len(children)} child routes)")
        for child in children:
            walk(f"{route}/{child['id']}", catalog, depth + 1)
    else:
        freqs = [f["id"] for f in meta.get("frequency", [])]
        print(
            f"{indent}{route}  freq={freqs}  "
            f"{meta.get('startPeriod')} -> {meta.get('endPeriod')}"
        )
        catalog[route] = meta


def sample(route: str) -> None:
    """Pull a few rows at each available frequency and save the raw responses."""
    meta = get(route)["response"]
    if meta.get("routes"):
        print(f"\n{route} is not a data route; its children: "
              f"{[c['id'] for c in meta['routes']]}")
        return

    columns = list(meta.get("data", {}).keys())
    print(f"\n=== {route} ===")
    print(f"data columns : {columns}")
    print(f"facets       : {[f['id'] for f in meta.get('facets', [])]}")
    print(f"default freq : {meta.get('defaultFrequency')}")

    for freq in meta.get("frequency", []):
        params = {
            "frequency": freq["id"],
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "offset": 0,
            "length": SAMPLE_ROWS,
        }
        for i, col in enumerate(columns):
            params[f"data[{i}]"] = col

        body = get(f"{route}/data", **params)
        resp = body["response"]
        print(f"\n-- frequency '{freq['id']}': total rows available = {resp.get('total')}, "
              f"dateFormat = {resp.get('dateFormat')}")
        if resp.get("warnings"):
            print(f"   warnings: {resp['warnings']}")
        for row in resp.get("data", []):
            print(f"   {row}")

        fname = OUT_DIR / f"{route.replace('/', '__')}__{freq['id']}.json"
        fname.write_text(json.dumps(body, indent=2))
        print(f"   saved {fname}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", nargs="+", metavar="ROUTE",
                        help="sample these leaf routes instead of walking the tree")
    args = parser.parse_args()

    if not API_KEY:
        sys.exit("No API key found. Expected the EAI_API_KEY Codespaces secret as an "
                 "environment variable. If you just added the secret, reload or rebuild "
                 "the Codespace so it is picked up.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Run at {datetime.now(timezone.utc).isoformat(timespec='seconds')} UTC")

    if args.sample:
        for route in args.sample:
            sample(route)
        return

    catalog: dict = {}
    for root in ROOT_ROUTES:
        walk(root, catalog)
    (OUT_DIR / "route_catalog.json").write_text(json.dumps(catalog, indent=2))
    print(f"\nSaved metadata for {len(catalog)} data routes to {OUT_DIR / 'route_catalog.json'}")


if __name__ == "__main__":
    main()