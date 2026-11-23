with crude as (
    SELECT
        'crude_imports' as source_name,
        'month' as grain,
        min(period) as first_period,
        max(period) as last_period,
        max(_loaded_at) as last_loaded_at,
        count(*) as row_count
    FROM {{ ref('_stg_eia_crude_imports') }}
)
, spot as (
    SELECT
        'spot_prices' as source_name,
        'day' as grain,
        min(period) as first_period,
        max(period) as last_period,
        max(_loaded_at) as last_loaded_at,
        count(*) as row_count
    FROM {{ ref('_stg_eia_spot_prices') }}
)
, electricity as (
    SELECT
        'electricity_daily' as source_name,
        'day' as grain,
        min(period) as first_period,
        max(period) as last_period,
        max(_loaded_at) as last_loaded_at,
        count(*) as row_count
    FROM {{ ref('_stg_eia_electricity_daily_fuel_type') }}
)
, combined as (
    SELECT * FROM crude
    UNION ALL
    SELECT * FROM spot
    UNION ALL
    SELECT * FROM electricity
)
, final as (
    SELECT
        source_name,
        grain,
        first_period,
        last_period,
        last_loaded_at,
        row_count,
        datediff(day, last_period, current_date()) as days_since_last_period,
        datediff(day, last_period, max(last_period) over ()) as days_behind_newest_source
    FROM combined
)
SELECT * FROM final