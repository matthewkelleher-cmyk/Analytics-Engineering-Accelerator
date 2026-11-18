with electricity as (
    SELECT DISTINCT
        respondent, 
        respondent_name, 
        iff(respondent = 'US48', TRUE, FALSE) is_reference
    FROM {{ref('_stg_eia_electricity_daily_fuel_type')}}
)
, final as (
    SELECT * 
    FROM electricity 
)
SELECT * 
FROM final