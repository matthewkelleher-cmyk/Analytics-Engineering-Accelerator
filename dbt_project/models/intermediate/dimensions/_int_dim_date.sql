with dates as (
    SELECT * 
    FROM {{ref('_int_date_spine')}}
)
, add_join_keys as (
    SELECT 
        date_day, 
        date_trunc('month', date_day) month_start_date,
        date_part('year', date_day) date_year, 
        date_part('quarter', date_day) date_quarter,
        date_part('month', date_day) month_num, 
        monthname(date_day)month_name
    FROM dates 
)
SELECT * FROM add_join_keys