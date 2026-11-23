with ports as ( 
    SELECT 
        destination_id, 
        port_name, 
        state, 
        latitude, 
        longitude, 
        coordinate_basis
    FROM {{ref('port_coordinates')}}
)
SELECT * FROM ports 