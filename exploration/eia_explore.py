"""Exploratory script for the EIA API v2 (throwaway, not the final ingestion).

Answers three questions before the real ingestion script is designed:
  1. What routes exist under petroleum and crude-oil-imports?
  2. What frequencies does each data route offer, and what period range does it cover?
  3. How does the raw JSON look (columns, facets, units, row shape)?

Usage (in the Codespace terminal):
    python eia_explore.py            # catalog the route tree, then sample the leaves below
    python eia_explore.py --catalog  # route catalog only

Output goes to data/raw_samples/ (add it to .gitignore).
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

BASE = "https://api.eia.gov/v2"
OUT_DIR = Path("data/raw_samples")

# Top-level routes to walk.
ROOT_ROUTES = ["petroleum", "crude-oil-imports"]

# Data routes to sample once you have seen the catalog. Adjust after the first run.
SAMPLE_ROUTES = [
    "petroleum/move/imp",   # petroleum imports (check the catalog for the exact path)
    "crude-oil-imports",    # crude imports by origin, destination and grade
    # "petroleum/pri/spt",  # spot prices (WTI / Brent), if wanted from EIA
]
SAMPLE_ROWS = 5

# The key lives in a Codespaces secret. The name used so far is EAI_API_KEY;
# EIA_API_KEY is accepted as a fallback in case the secret gets renamed.
API_KEY = os.environ.get("EAI_API_KEY") or os.environ.get("EIA_API_KEY")


def get(path: str, **params) -> dict:
    """GET one EIA endpoint and return the parsed JSON. Never prints the key."""
    params["api_key"] = API_KEY
    resp = requests.get(f"{BASE}/{path.strip('/')}", params=params, timeout=30)
    if not resp.ok:
        sys.exit(f"HTTP {resp.status_code} for /{path}: {resp.text[:300]}")
    time.sleep(0.2)  # be polite; the catalog walk makes many small calls
    return resp.json()


def walk(route: str, catalog: dict, depth: int = 0) -> None:
    """Recursively walk the route tree, recording the metadata of each data (leaf) route."""
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


def sample(route: str, catalog: dict) -> None:
    """Pull a few rows at each available frequency and save the raw responses."""
    meta = catalog.get(route) or get(route)["response"]
    if meta.get("routes"):
        print(f"\n{route} is not a data route; it has children: "
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
    parser.add_argument("--catalog", action="store_true", help="only build the route catalog")
    args = parser.parse_args()

    if not API_KEY:
        sys.exit("No API key found. Expected the EAI_API_KEY Codespaces secret as an "
                 "environment variable. If you just added the secret, rebuild or reload "
                 "the Codespace so it is picked up.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    catalog: dict = {}
    for root in ROOT_ROUTES:
        walk(root, catalog)
    (OUT_DIR / "route_catalog.json").write_text(json.dumps(catalog, indent=2))
    print(f"\nSaved metadata for {len(catalog)} data routes to {OUT_DIR / 'route_catalog.json'}")

    if not args.catalog:
        for route in SAMPLE_ROUTES:
            sample(route, catalog)


if __name__ == "__main__":
    main()