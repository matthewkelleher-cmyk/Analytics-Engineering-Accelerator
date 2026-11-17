with crude as (
    SELECT * 
    FROM {{ref('_stg_eia_crude_imports')}}
)
,
final as (
    SELECT DISTINCT
    grade_id,
    grade_name
    FROM crude 
)
SELECT * 
FROM final 