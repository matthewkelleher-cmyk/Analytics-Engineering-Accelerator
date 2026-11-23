with imports as (
    SELECT
        date_day,
        grade_id,
        destination_id,
        origin_id,
        quantity,
        units
    FROM {{ ref('_int_fct_crude_imports') }}
)
, dates as (
    SELECT
        date_day,
        date_year,
        date_quarter,
        month_num,
        month_name
    FROM {{ ref('_int_dim_date') }}
)
, grades as (
    SELECT grade_id, grade_name
    FROM {{ ref('_int_dim_grade') }}
)
, origins as (
    SELECT
        origin_id,
        origin_name,
        iso2,
        iso3,
        continent,
        is_known,
        longitude as origin_longitude,
        latitude as origin_latitude
    FROM {{ ref('_int_dim_origin_country') }}
)
, ports as (
    SELECT
        destination_id,
        port_name,
        state as port_state,
        longitude as port_longitude,
        latitude as port_latitude,
        coordinate_basis
    FROM {{ ref('_int_dim_port') }}
)
, final as (
    SELECT
        imports.date_day as month_start_date,
        dates.date_year,
        dates.date_quarter,
        dates.month_num,
        dates.month_name,
        imports.origin_id,
        origins.origin_name,
        origins.iso2,
        origins.iso3,
        origins.continent,
        origins.is_known,
        origins.origin_longitude,
        origins.origin_latitude,
        imports.destination_id,
        ports.port_name,
        ports.port_state,
        ports.port_longitude,
        ports.port_latitude,
        ports.coordinate_basis,
        imports.grade_id,
        grades.grade_name,
        imports.quantity,
        imports.units
    FROM imports
    INNER JOIN dates ON imports.date_day = dates.date_day
    INNER JOIN grades ON imports.grade_id = grades.grade_id
    LEFT JOIN origins ON imports.origin_id = origins.origin_id
    LEFT JOIN ports ON imports.destination_id = ports.destination_id
)
SELECT * FROM final