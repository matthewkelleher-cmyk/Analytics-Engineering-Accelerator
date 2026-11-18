with spot_prices as (
    SELECT * 
    FROM {{ref('_stg_eia_spot_prices')}}
)
, final as (
    SELECT 
        period date_day,
        series, 
        value price
    FROM spot_prices 
)
SELECT * FROM final 