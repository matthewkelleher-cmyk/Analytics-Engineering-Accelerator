"""A small client for the EIA open data API v2.

Pages through results 5,000 rows at a time with a stable sort, pauses between calls, retries
rate-limit and server errors with backoff, and never prints or logs the API key. Error
messages deliberately leave out the request URL, because the URL contains the key.
"""

import logging
import os
import time

import requests

BASE = "https://api.eia.gov/v2"
PAGE_SIZE = 5000          # the API's maximum rows per call
PAUSE_SECONDS = 0.3       # EIA bans keys that call too heavily
MAX_ATTEMPTS = 5
RETRY_STATUSES = {429, 500, 502, 503, 504}

log = logging.getLogger(__name__)


class EiaError(RuntimeError):
    """A failure talking to the EIA API."""


class EiaClient:
    def __init__(self, api_key=None, session=None, pause=PAUSE_SECONDS, sleep=time.sleep):
        self._key = api_key or os.environ.get("EIA_API_KEY")
        if not self._key:
            raise EiaError("EIA_API_KEY is not set. In Codespaces it is a secret; "
                           "locally put it in .env (see .env.example).")
        self._session = session or requests.Session()
        self._pause = pause
        self._sleep = sleep
        self.last_total = None  # the API's reported total for the most recent fetch_rows

    def _get(self, path, params):
        """GET one endpoint with retries; returns parsed JSON."""
        url = f"{BASE}/{path.strip('/')}"
        query = {**params, "api_key": self._key}
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                resp = self._session.get(url, params=query, timeout=60)
            except requests.RequestException as exc:
                reason = type(exc).__name__  # not str(exc): it can contain the URL
            else:
                if resp.status_code == 200:
                    body = resp.json()
                    if "error" in body:
                        raise EiaError(f"/{path} returned an error: {str(body['error'])[:200]}")
                    self._sleep(self._pause)
                    return body
                if resp.status_code not in RETRY_STATUSES:
                    raise EiaError(f"HTTP {resp.status_code} for /{path}: {resp.text[:200]}")
                reason = f"HTTP {resp.status_code}"
            if attempt == MAX_ATTEMPTS:
                raise EiaError(f"/{path} failed after {MAX_ATTEMPTS} attempts ({reason})")
            wait = 2 ** attempt
            log.warning("/%s: %s, retrying in %ss (attempt %s of %s)",
                        path, reason, wait, attempt, MAX_ATTEMPTS)
            self._sleep(wait)

    @staticmethod
    def _data_params(frequency, data_cols, facets, sort_cols, start, end, offset, length):
        params = {"frequency": frequency, "offset": offset, "length": length}
        for i, col in enumerate(data_cols):
            params[f"data[{i}]"] = col
        for facet, values in facets.items():
            params[f"facets[{facet}][]"] = list(values)
        for i, col in enumerate(sort_cols):
            params[f"sort[{i}][column]"] = col
            params[f"sort[{i}][direction]"] = "asc"
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        return params

    def fetch_rows(self, route, frequency, data_cols, facets, sort_cols,
                   start=None, end=None, max_pages=None, allow_shortfall=False):
        """Yield every matching row, oldest first, one page of 5,000 at a time.

        Raises if fewer rows arrive than the API reported, unless allow_shortfall is set,
        in which case the gap is logged. The reported total is kept in self.last_total.
        """
        offset, total, pages, fetched = 0, None, 0, 0
        while True:
            params = self._data_params(frequency, data_cols, facets, sort_cols,
                                       start, end, offset, PAGE_SIZE)
            response = self._get(f"{route}/data", params)["response"]
            if total is None:
                total = int(response["total"])
                self.last_total = total
                log.info("%s: %s rows match (start=%s)", route, total, start)
            for warning in response.get("warnings") or []:
                log.warning("%s: API warning: %s", route, warning)
            rows = response.get("data") or []
            expected = min(PAGE_SIZE, total - offset)
            if len(rows) < expected:
                log.warning("%s: the page at offset %s returned %s of %s expected rows",
                            route, offset, len(rows), expected)
            yield from rows
            fetched += len(rows)
            pages += 1
            offset += PAGE_SIZE
            if not rows or offset >= total or (max_pages and pages >= max_pages):
                break
        if not max_pages and fetched < total and allow_shortfall:
            log.warning("%s: received %s rows but the API reported %s (%s fewer); "
                        "continuing because this source tolerates a shortfall",
                        route, fetched, total, total - fetched)
        elif not max_pages and fetched < total:
            raise EiaError(f"{route}: received {fetched} rows in {pages} pages but the API "
                           f"reported {total}; see the short-page warnings above")

    def newest_period(self, route, frequency, data_cols, facets):
        """The newest period the data endpoint holds for this filter, or None.

        This is the freshness probe: ask the data itself, not the route metadata, whose
        endPeriod can mislead (forecast rows, differing frequencies).
        """
        params = {"frequency": frequency, "offset": 0, "length": 1,
                  "sort[0][column]": "period", "sort[0][direction]": "desc"}
        for i, col in enumerate(data_cols):
            params[f"data[{i}]"] = col
        for facet, values in facets.items():
            params[f"facets[{facet}][]"] = list(values)
        data = self._get(f"{route}/data", params)["response"].get("data") or []
        return data[0]["period"] if data else None