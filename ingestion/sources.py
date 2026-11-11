"""What to pull from the EIA API and where it lands. The one place a source is defined.

Each source becomes one raw table in the MK_RAW schema. Filters here follow the design
decisions: 7 (one level, one unit, one timezone per fact table) and 11 (electricity filter).
Changing a filter means editing this file, not the loading code.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    name: str                  # short name, used on the command line and in logs
    table: str                 # raw table name inside the raw schema
    route: str                 # EIA route (the /data endpoint is appended)
    frequency: str             # one frequency only (decision 5)
    data_cols: tuple           # value columns to request
    facets: dict               # facet filters: facet id -> list of values
    key_fields: tuple          # row fields that form the natural key; period comes first
    sort_cols: tuple           # sort order for stable paging, ascending
    window: int                # trailing reload window for revisions (decision 10)
    window_unit: str           # "months" or "days"
    first_period: str | None = None  # earliest period for a full load; None = everything
    allow_shortfall: bool = False    # True if the API's total is known to overstate the rows it returns


SOURCES = {
    "crude_imports": Source(
        name="crude_imports",
        table="raw_eia_crude_imports",
        route="crude-oil-imports",
        frequency="monthly",
        data_cols=("quantity",),
        facets={"originType": ["CTY"], "destinationType": ["PT"]},
        key_fields=("period", "originId", "destinationId", "gradeId"),
        sort_cols=("period", "originId", "destinationId", "gradeId"),
        window=3,
        window_unit="months",
        first_period="2009-01",
        # The API's total is a few rows higher than what it returns (about 4% over the full
        # history, none since 2025-09), probably rows without a quantity. See FINDINGS.md.
        allow_shortfall=True,
    ),
    "spot_prices": Source(
        name="spot_prices",
        table="raw_eia_spot_prices",
        route="petroleum/pri/spt",
        frequency="daily",
        data_cols=("value",),
        facets={"series": ["RWTC", "RBRTE"]},
        key_fields=("period", "series"),
        sort_cols=("period", "series"),
        window=14,
        window_unit="days",
    ),
    "electricity": Source(
        name="electricity",
        table="raw_eia_electricity_daily_fuel_type",
        route="electricity/rto/daily-fuel-type-data",
        frequency="daily",
        data_cols=("value",),
        facets={
            "respondent": ["US48", "ERCO", "CISO", "PJM", "MISO", "NYIS", "ISNE"],
            "timezone": ["Eastern"],
        },
        key_fields=("period", "respondent", "fueltype", "timezone"),
        sort_cols=("period", "respondent", "fueltype"),
        window=14,
        window_unit="days",
    ),
}