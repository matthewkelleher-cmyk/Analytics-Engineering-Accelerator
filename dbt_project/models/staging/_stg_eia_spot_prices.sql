with source as (
SELECT * 
FROM {{source('mk_raw','raw_eia_spot_prices')}}
)
, parsed as (
    SELECT 
        to_date(period, 'YYYY-MM-DD') as period, 
        series,
        raw_row:"area-name"::string area_name,
        raw_row:"duoarea"::string duoarea,
        raw_row:"process"::string process,
        raw_row:"process-name"::string process_name,
        raw_row:"product"::string product,
        raw_row:"product-name"::string product_name,
        raw_row:"series-description"::string series_description,
        raw_row:"units"::string,
        raw_row:"value"::int value, 
        row_hash,
        _batch_id,
        _loaded_at
    FROM source
)
SELECT * FROM parsed 