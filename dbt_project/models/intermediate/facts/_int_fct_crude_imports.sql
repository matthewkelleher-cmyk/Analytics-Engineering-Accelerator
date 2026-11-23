with crude as (
    SELECT *
    FROM {{ref('_stg_eia_crude_imports')}}
)
, final as (
    SELECT 
        period date_day,
        grade_id, 
        destination_id, 
        origin_id, 
        quantity, 
        quantity_units units
    FROM crude 
)
SELECT * FROM final 