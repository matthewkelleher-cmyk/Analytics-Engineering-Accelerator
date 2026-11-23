with electricity as (
    SELECT * 
    FROM {{ref('_stg_eia_electricity_daily_fuel_type')}}
)
, latest_codes as (
    SELECT 
        fuel_type,
        row_number() over (partition by fuel_type order by period desc, type_name) as row_num,
        type_name,
    FROM electricity
    qualify row_num = 1
)

, final as (
    SELECT 
        fuel_type,
        type_name
    FROM latest_codes
)
SELECT * 
FROM final 