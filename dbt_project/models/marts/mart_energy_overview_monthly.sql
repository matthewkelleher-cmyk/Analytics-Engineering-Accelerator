with months as (
    SELECT
        month_start_date,
        date_year,
        date_quarter,
        month_num,
        month_name,
        max(date_day) as last_day_in_spine
    FROM {{ ref('_int_dim_date') }}
    GROUP BY month_start_date, date_year, date_quarter, month_num, month_name
)
, crude as (
    SELECT
        date_day as month_start_date,
        sum(quantity) as total_import_quantity,
        count(distinct origin_id) as origin_count
    FROM {{ ref('_int_fct_crude_imports') }}
    GROUP BY date_day
)
, prices as (
    SELECT
        month_start_date,
        avg(wti_price) as avg_wti_price,
        avg(brent_price) as avg_brent_price,
        avg(brent_wti_spread) as avg_brent_wti_spread,
        count(*) as price_days
    FROM {{ ref('mart_spot_prices_daily') }}
    GROUP BY month_start_date
)
, electricity as (
    SELECT
        dates.month_start_date,
        sum(generation.generation) as us48_generation,
        count(distinct generation.date_day) as electricity_days
    FROM {{ ref('_int_fct_electricity_daily') }} generation
    INNER JOIN {{ ref('_int_dim_respondent') }} respondents
        ON generation.respondent = respondents.respondent
    INNER JOIN {{ ref('_int_dim_date') }} dates
        ON generation.date_day = dates.date_day
    WHERE respondents.is_reference
    GROUP BY dates.month_start_date
)
, final as (
    SELECT
        months.month_start_date,
        months.date_year,
        months.date_quarter,
        months.month_num,
        months.month_name,
        day(last_day(months.month_start_date)) as days_in_month,
        last_day(months.month_start_date) <= max(months.last_day_in_spine) over () as is_complete_month,
        crude.total_import_quantity,
        crude.origin_count,
        prices.avg_wti_price,
        prices.avg_brent_price,
        prices.avg_brent_wti_spread,
        prices.price_days,
        electricity.us48_generation,
        electricity.electricity_days
    FROM months
    LEFT JOIN crude ON months.month_start_date = crude.month_start_date
    LEFT JOIN prices ON months.month_start_date = prices.month_start_date
    LEFT JOIN electricity ON months.month_start_date = electricity.month_start_date
)
SELECT * FROM final