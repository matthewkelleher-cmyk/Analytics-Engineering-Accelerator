with source as (
SELECT * 
FROM {{source('mk_raw', 'raw_eia_crude_imports')}}
)
,
parsed as (
    SELECT 
        to_date(period, 'YYYY-MM') as period,
        originid,
        raw_row:"destinationId"::varchar destination_id,
        raw_row:"destinationName"::string destination_name,
        raw_row:"destinationType"::string destination_type,
        raw_row:"destinationTypeName"::string destination_type_name,
        raw_row:"gradeId"::varchar grade_id,
        raw_row:"gradeName"::string grade_name,
        raw_row:"originId"::varchar origin_id,
        raw_row:"originName"::string origin_name,
        raw_row:"originType"::string origin_type,
        raw_row:"originTypeName"::string origin_type_name,
        raw_row:"quantity"::int quantity,
        raw_row:"quantity-units"::string quantity_units,
        row_hash,
        _batch_id,
        _loaded_at
    FROM source
)
SELECT * FROM parsed