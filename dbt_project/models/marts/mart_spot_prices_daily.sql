with prices as (
    SELECT date_day, series, price
    FROM {{ ref('_int_fct_spot_prices') }}
)
, price_series as (
    SELECT series, benchmark
    FROM {{ ref('_int_dim_price_series') }}
)
, dates as (
    SELECT
        date_day,
        month_start_date,
        date_year,
        date_quarter,
        month_num,
        month_name
    FROM {{ ref('_int_dim_date') }}
)
, pivoted as (
    SELECT
        prices.date_day,
        max(iff(price_series.benchmark = 'WTI', prices.price, null)) as wti_price,
        max(iff(price_series.benchmark = 'Brent', prices.price, null)) as brent_price
    FROM prices
    INNER JOIN price_series ON prices.series = price_series.series
    GROUP BY prices.date_day
)
, final as (
    SELECT
        dates.date_day,
        dates.month_start_date,
        dates.date_year,
        dates.date_quarter,
        dates.month_num,
        dates.month_name,
        pivoted.wti_price,
        pivoted.brent_price,
        pivoted.brent_price - pivoted.wti_price as brent_wti_spread
    FROM pivoted
    INNER JOIN dates ON pivoted.date_day = dates.date_day
)
SELECT * FROM final