with generation as (
    SELECT
        date_day,
        respondent,
        fuel_type,
        generation,
        value_units
    FROM {{ ref('_int_fct_electricity_daily') }}
)
, respondents as (
    SELECT
        respondent,
        respondent_name,
        is_reference
    FROM {{ ref('_int_dim_respondent') }}
)
, fuel_types as (
    SELECT
        fuel_type,
        type_name as fuel_type_name
    FROM {{ ref('_int_dim_fuel_type') }}
)
, dates as (
    SELECT
        date_day,
        month_start_date,
        date_year,
        date_quarter,
        month_num,
        month_name
    FROM {{ ref('_int_dim_date') }}
)
, final as (
    SELECT
        dates.date_day,
        dates.month_start_date,
        dates.date_year,
        dates.date_quarter,
        dates.month_num,
        dates.month_name,
        generation.respondent,
        respondents.respondent_name,
        respondents.is_reference,
        generation.fuel_type,
        fuel_types.fuel_type_name,
        generation.generation,
        generation.value_units
    FROM generation
    INNER JOIN dates ON generation.date_day = dates.date_day
    INNER JOIN respondents ON generation.respondent = respondents.respondent
    INNER JOIN fuel_types ON generation.fuel_type = fuel_types.fuel_type
)
SELECT * FROM final