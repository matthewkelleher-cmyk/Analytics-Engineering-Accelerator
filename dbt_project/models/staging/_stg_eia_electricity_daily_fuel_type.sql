with source as (
SELECT * 
FROM {{source('mk_raw', 'raw_eia_electricity_daily_fuel_type')}}
)
, parsed as (
    SELECT 
        to_date(period, 'YYYY-MM-DD') as period, 
        respondent,
        fueltype fuel_type,
        timezone time_zone,
        raw_row:"respondent-name"::string respondent_name,
        raw_row:"timezone-description"::string time_zone_description,
        raw_row:"type-name"::string type_name,
        raw_row:"value"::int value,
        raw_row:"value-units"::string value_units
    FROM source
)
SELECT * FROM parsed 