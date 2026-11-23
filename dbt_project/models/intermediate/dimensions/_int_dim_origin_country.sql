with final as (
    SELECT 
      origin_id, 
      origin_name, 
      iso2, 
      iso3, 
      continent, 
      is_known, 
      longitude, 
      latitude 
    FROM {{ref('_stg_country_coordinates')}}
)
SELECT * 
FROM final