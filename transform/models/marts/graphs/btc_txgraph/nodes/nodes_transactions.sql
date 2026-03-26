SELECT
    row_number() OVER () AS node_id,
    tx_id,
    tx_class,
    time_step
FROM {{ ref('ebtc_transactions') }}
