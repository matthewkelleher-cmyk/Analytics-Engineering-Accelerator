with source as (
SELECT * 
FROM {{source('mk_raw', 'raw_eia_crude_imports')}}
)
,
parsed as (
    SELECT 
        to_date(period, 'YYYY-MM') as period,
        originid,
        raw_row:"destinationId"::varchar,
        raw_row:"destinationName"::string,
        raw_row:"destinationType"::string,
        raw_row:"destinationTypeName"::string,
        raw_row:"gradeId"::int,
        raw_row:"gradeName"::string,
        raw_row:"originId"::varchar,
        raw_row:"originName"::string,
        raw_row:"originType"::string,
        raw_row:"originTypeName"::string,
        raw_row:"quantity"::int,
        raw_row:"quantity-units"::string,
        row_hash,
        _batch_id,
        _loaded_at
    FROM source
)
SELECT * FROM parsed