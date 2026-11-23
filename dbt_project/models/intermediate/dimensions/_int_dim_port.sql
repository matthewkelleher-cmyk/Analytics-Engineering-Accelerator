with final as (
    SELECT 
        destination_id, 
        port_name, 
        state, 
        longitude, 
        latitude, 
        coordinate_basis
    FROM {{ref('_stg_port_coordinates')}}
)
SELECT * 
FROM final