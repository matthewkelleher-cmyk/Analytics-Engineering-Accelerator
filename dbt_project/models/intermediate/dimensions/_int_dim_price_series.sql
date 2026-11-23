with price as (
    SELECT *
    FROM {{ref('_stg_eia_spot_prices')}}
)
, 
final as (
    SELECT DISTINCT
    series, 
    series_description, 
    product_name, 
    area_name, 
    units,
    CASE    
        WHEN series = 'RWTC' THEN 'WTI'
        WHEN series = 'RBRTE' THEN 'Brent'
        ELSE series 
    END benchmark 
    FROM price 
)
SELECT * 
FROM final 