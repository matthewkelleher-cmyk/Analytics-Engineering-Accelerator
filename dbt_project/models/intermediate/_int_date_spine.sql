with bounds as (
    SELECT
        date_trunc('month', start_date) as start_date, 
        end_date 
    FROM {{ref('_int_period_start_end')}}
)
, days as (
    SELECT 
        dateadd(day, row_number() over(order by seq4()) -1, bounds.start_date) as date_day,
        bounds.end_date
    FROM TABLE(generator(rowcount => 30000))
    CROSS JOIN bounds 
)
SELECT date_day
FROM days
WHERE date_day <= end_date