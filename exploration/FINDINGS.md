# Exploration findings: EIA open data

Run on 2026-11-03 against the EIA API v2, using the scripts in this folder:

| Script | Covers | Output folder (gitignored) |
|---|---|---|
| `eia_explore_oil.py` | `petroleum` and `crude-oil-imports` | `raw_samples_oil/` |
| `eia_explore_electricity.py` | `electricity/rto` | `raw_samples_electricity/` |
| `eia_explore_natgas.py` | `natural-gas/pri` | `raw_samples_natgas/` |

Each script has a catalog mode (route metadata only) and a sample mode (the 5 newest rows per frequency). Nothing here is loaded into Snowflake. Row counts and "newest period" dates are as of the run and will change; rerun the scripts to refresh them.

## Summary

- **Monthly sources (oil).** `crude-oil-imports` and `petroleum/move/imp` update monthly with about a two-month lag (newest period 2026-08 on Nov 3). They hold repeated rows that would double count if summed as they come.
- **Weekly-batch sources (prices).** Spot prices carry daily values, but they seem to arrive in weekly batches about a week late. The newest daily Henry Hub price on Nov 3 was 2026-10-27. Petroleum spot prices (`petroleum/pri/spt`) are not sampled yet.
- **Daily source (electricity).** `electricity/rto` is the only source found that gets new data almost every day (daily routes 0 to 2 days behind, hourly routes 9 to 32 hours behind). It repeats every row once per timezone.
- **Natural gas** is not used (see below).

## Catalog

| Tree | Data routes | Notes |
|---|---|---|
| `petroleum` | 112 | 7 groups (`sum`, `pri`, `crd`, `pnp`, `move`, `stoc`, `cons`), frequencies from daily to annual |
| `crude-oil-imports` | 1 | monthly and annual, 2009-01 to 2026-08 |
| `electricity/rto` | 8 | 4 hourly routes and 4 daily routes, 2019-01-01 onward |
| `natural-gas/pri` | 3 | `sum`, `rescom` (monthly, annual) and `fut` (monthly, weekly, annual, daily) |

Routes of interest from the petroleum catalog (route-level newest period, as printed by the catalog):

| Route | Frequencies | Newest period |
|---|---|---|
| `petroleum/move/imp` | monthly, annual | 2026-08 |
| `petroleum/move/wimpc` (weekly imports, not sampled) | weekly, four-week average | 2026-10-23 |
| `petroleum/pri/spt` (spot prices) | daily, weekly, monthly, annual | 2026-10-23 |
| `petroleum/pri/fut` | daily, weekly, monthly, annual | 2024-04-05 (stale) |
| `petroleum/pri/gnd` (retail gasoline and diesel) | weekly, monthly, annual | 2026-11-02 |

## Freshness by source

Latest periods as of about 16:45 UTC on 2026-11-03.

| Route | Frequency | Newest period | Behind the run |
|---|---|---|---|
| `crude-oil-imports` | monthly | 2026-08 | about 2 months |
| `petroleum/move/imp` | monthly | 2026-08 | about 2 months |
| `petroleum/pri/spt` | daily (not sampled yet) | 2026-10-23 at route level | to check |
| `natural-gas/pri/fut` | daily | 2026-10-27 | 7 days |
| `natural-gas/pri/fut` | weekly | 2026-10-23 | 11 days |
| `electricity/rto/daily-region-data` | daily | 2026-11-03 | current day (forecast rows only) |
| `electricity/rto/daily-fuel-type-data` | daily | 2026-11-02 | about 1 day |
| `electricity/rto/daily-region-sub-ba-data` | daily | 2026-11-02 | about 1 day |
| `electricity/rto/daily-interchange-data` | daily | 2026-11-01 | about 2 days |
| `electricity/rto/fuel-type-data` | hourly | 2026-11-03T07 | about 10 hours |
| `electricity/rto/region-sub-ba-data` | hourly | 2026-11-03T08 | about 9 hours |
| `electricity/rto/interchange-data` | hourly | 2026-11-02T08 | about 32 hours |

Release rhythm, from EIA's own pages and one Reuters schedule note:

- The Petroleum Supply Monthly (PSM) is normally released on the last business day of the month, and company-level imports (the source of `crude-oil-imports`) are released on the same dates.
- Releases slip: November 2025 data moved from Jan 30 to Feb 6, 2026 to wait for Census trade data, and June 2026 data was delayed from Aug 31 into September.
- Earlier months are revised: October 2025 data was republished on Jan 30, 2026 and flowed into the API.
- The weekly petroleum report comes out on Wednesdays.
- The API (v2) has no last-updated field, and EIA says it is updated constantly rather than at regular intervals. Freshness has to be measured by looking at the data.
- EIA temporarily bans keys that call too heavily, so scripts pause between calls.

Sources: [PSM release notice](https://www.eia.gov/petroleum/supply/monthly/notice.php), [EIA What's New](https://www.eia.gov/about/new/?r=40), [EIA open data FAQ](https://www.eia.gov/opendata/faqs.php), [Reuters energy data schedule, Sept 4 2026](https://boereport.com/2026/09/04/schedule-for-us-energy-data-in-holiday-week/amp/).

## Raw data shapes and traps

### `crude-oil-imports` (monthly: 561,178 rows; annual: 92,057 rows)

- One row per period, origin, destination and grade. The value column is `quantity` in thousand barrels, as text.
- **The same quantity is repeated at five destination levels** (`destinationType`): Port PADD (`PP`), Port State (`PS`), Port (`PT`), Refinery (`RF`) and Refinery PADD (`RP`). For August 2026, UAE light sour crude shows 1,578 at all five. For 2025, California (9,716) plus Washington (416) equals PADD 5 (10,132). Summing the table as it comes overcounts about fivefold.
- The origin has a type too (`originType`, for example `CTY` for country), which probably needs the same treatment. Not checked yet.

### `petroleum/move/imp` (monthly: 233,720 rows; annual: 21,346 rows)

- Facets: `duoarea`, `product`, `process`, `series`. The value column is `value`, as text, with a `units` field.
- **The same measure appears in two units in one column**: `MAPIMP11` in thousand barrels (`MBBL`) and `MAPIMP12` in thousand barrels per day (`MBBL/D`). They must not be summed together.

### `electricity/rto/daily-fuel-type-data` (5,766,693 rows)

- Facets: `respondent`, `fueltype`, `timezone`. The value is in `megawatthours`, as text.
- **Every respondent, fuel and day appears once per timezone** (Arizona, Central, Eastern, Mountain, Pacific), with different values, because each timezone draws the day boundary differently. One timezone must be chosen.
- **Fuel types:** 20 entries but only 16 distinct ids (`NUC`, `BAT`, `UES`, `PS`, `GEO`, `WNB`, `UNK`, `OIL`, `WAT`, `WND`, `COL`, `SNB`, `NG`, `OES`, `OTH`, `SUN`). Four ids appear twice with different names (`BAT`, `UES`, `PS`, `SNB`), so a dimension has to key on the id and pick one name.
- **Respondents:** 83, at mixed levels: the lower 48 total (`US48`), regional and state aggregates (for example `CAL`, `TEX`, `NY`, `FLA`, `MIDA`, `NE`, `SE`, `NW`), large grid operators (for example `ERCO`, `CISO`, `PJM`, `MISO`, `NYIS`, `ISNE`, `SWPP`) and single utilities or plants. The aggregates appear to contain the operators beneath them, so summing across respondents would double count.
- **Filter sizes** (daily frequency, Eastern timezone, newest day 2026-11-02 in both cases): `US48` alone is 28,191 rows; `US48` plus `ERCO`, `CISO`, `PJM`, `MISO`, `NYIS` and `ISNE` is 163,029 rows. A full load of the larger filter is 33 pages of 5,000.

### `electricity/rto/daily-region-data` (4,057,740 rows)

- Facets: `respondent`, `type`, `timezone`. The newest rows (2026-11-03) are all type `DF`, the day-ahead demand forecast, which is why the route reaches the current day. The `type` facet has four values: `D` (demand), `DF` (day-ahead demand forecast), `NG` (net generation) and `TI` (total interchange). How far behind the actual types run has not been checked.

### `natural-gas/pri/fut` (daily 37,872 rows; weekly 7,868; monthly 2,026; annual 169)

- Despite the name, the rows are mostly the Henry Hub spot price (`RNGWHHD`), plus a monthly and annual NGL composite price (`NGM_EPG0_PLC_NUS_DMMBTU`). The futures series (`RNGC1`, `RNGC2`) show up only in 2024.

### Common to all routes

- Values arrive as text (`'950'`, `'1578'`, `'2.95'`).
- The period format depends on the frequency: `YYYY`, `YYYY-MM`, `YYYY-MM-DD`, and hourly `YYYY-MM-DDTHH`.
- The unit field is named differently on each route (`units`, `quantity-units`, `value-units`).
- Rows repeat descriptive names next to their ids (`area-name`, `product-name`, `originName`, `respondent-name`).
- The route-level `endPeriod` in the metadata can mislead. `natural-gas/pri/fut` reported 2026-10-23 while its daily data ran to 2026-10-27, and `daily-region-data` reaches today only through forecasts. A probe has to ask the data endpoint for the newest row at each frequency instead.

## What follows from this

These are written up in the INTENTIONAL_DESIGN_DECISIONS doc (decisions 4 to 12):

- Use the EIA API for every source, and load monthly data, never monthly and annual together.
- Pick one level, one unit and one timezone for each fact table.
- Keep raw rows as they arrive and type them in staging.
- Run a probe daily and load only when something is newer, with a watermark per route and frequency and a run log.
- Reload a trailing window and merge on the natural key, to catch revisions.
- Use filtered electricity data as the daily source: `US48` as a reference series plus `ERCO`, `CISO`, `PJM`, `MISO`, `NYIS` and `ISNE`, Eastern time, all fuel types (163,029 rows, decision 11).
- Do not use natural gas: its daily data arrives in weekly batches, its futures stopped in 2024, and it adds little beyond oil prices and electricity.

## Open questions

- Which crude import level (port or refinery) and origin level to keep, and which unit for petroleum imports.
- Whether the spot price routes follow the weekly-batch pattern. Check the newest daily date today and again on Wednesday afternoon, Nov 4.
- How far behind the actual types (`D`, `NG`, `TI`) run on `daily-region-data`, if that route is added.
- How large the revisions to earlier months are, which sets the reload window.
- Whether a daily probe that loads when new data appears satisfies the brief's request for a daily refresh.