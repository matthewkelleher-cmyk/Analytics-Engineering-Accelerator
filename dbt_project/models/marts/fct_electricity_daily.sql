with electricity as (
    SELECT * 
    FROM {{ref('_stg_eia_electricity_daily_fuel_type')}}
)
, final as (
    SELECT 
        period date_day, 
        respondent, 
        fuel_type, 
        value generation, 
        value_units
    FROM electricity 
)
SELECT * FROM final 