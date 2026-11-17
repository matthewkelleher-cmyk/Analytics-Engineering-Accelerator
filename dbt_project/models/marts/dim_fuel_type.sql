with electricity as (
    SELECT * 
    FROM {{ref(_stg_eia_electricty_daily_fuel_type)}}
)
, final as (
    SELECT 
    
    FROM electricity
)
SELECT * 
FROM final 