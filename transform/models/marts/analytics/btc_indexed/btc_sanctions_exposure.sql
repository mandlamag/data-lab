{{ config(alias='sanctions_exposure') }}

WITH sanctioned AS (
    SELECT address, display_label
    FROM {{ ref('btc_addresses') }}
    WHERE is_sanctioned = TRUE
),

exposed_via_send AS (
    SELECT
        pf.sender_address AS exposed_address,
        sa.address AS sanctioned_address,
        sa.display_label AS sanctioned_entity,
        pf.tx_hash,
        pf.blockheight,
        pf.output_amount_btc AS amount_btc,
        'sent_to_sanctioned' AS exposure_type
    FROM {{ ref('btc_payment_flows') }} AS pf
    JOIN sanctioned AS sa ON pf.receiver_address = sa.address
),

exposed_via_receive AS (
    SELECT
        pf.receiver_address AS exposed_address,
        sa.address AS sanctioned_address,
        sa.display_label AS sanctioned_entity,
        pf.tx_hash,
        pf.blockheight,
        pf.output_amount_btc AS amount_btc,
        'received_from_sanctioned' AS exposure_type
    FROM {{ ref('btc_payment_flows') }} AS pf
    JOIN sanctioned AS sa ON pf.sender_address = sa.address
),

all_exposures AS (
    SELECT * FROM exposed_via_send
    UNION ALL
    SELECT * FROM exposed_via_receive
)

SELECT
    a.display_label AS exposed_entity,
    e.exposed_address,
    e.sanctioned_entity,
    e.sanctioned_address,
    e.exposure_type,
    COUNT(DISTINCT e.tx_hash) AS tx_count,
    ROUND(SUM(e.amount_btc), 8) AS total_amount_btc,
    MIN(e.blockheight) AS first_block,
    MAX(e.blockheight) AS last_block
FROM all_exposures AS e
LEFT JOIN {{ ref('btc_addresses') }} AS a ON e.exposed_address = a.address
GROUP BY a.display_label, e.exposed_address, e.sanctioned_entity, e.sanctioned_address, e.exposure_type
ORDER BY total_amount_btc DESC
