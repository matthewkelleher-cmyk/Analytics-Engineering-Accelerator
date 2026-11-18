with crude_period as (
    SELECT 
        min(period) min_period, 
        max(period) max_period
    FROM {{ref('_stg_eia_crude_imports')}}
)
, spot as (
    SELECT 
        min(period) min_period,
        max(period) max_period
    FROM {{ref('_stg_eia_spot_prices')}}
)
, electricity as (
    SELECT
        min(period) min_period,
        max(period) max_period
    FROM {{ref('_stg_eia_electricity_daily_fuel_type')}}
)
, all_periods as (
    SELECT * FROM crude_period
    UNION BY NAME  
    SELECT * FROM spot 
    UNION BY NAME
    SELECT * FROM electricity 
)
, final as (
    SELECT 
    max(max_period) as end_date,
    min(min_period) as start_date 
    FROM all_periods
)
SELECT * FROM final