{{ config(alias='payment_flows') }}

WITH inputs AS (
    SELECT
        hash AS tx_hash,
        blockheight,
        address AS sender_address,
        ABS(amount) AS amount_btc
    FROM {{ ref('btc_vins') }}
),

outputs AS (
    SELECT
        hash AS tx_hash,
        blockheight,
        address AS receiver_address,
        amount AS amount_btc
    FROM {{ ref('btc_vouts') }}
),

known_addresses AS (
    SELECT address FROM {{ ref('btc_addresses') }}
)

SELECT DISTINCT
    i.tx_hash,
    i.blockheight,
    i.sender_address,
    o.receiver_address,
    i.amount_btc AS input_amount_btc,
    o.amount_btc AS output_amount_btc
FROM inputs AS i
JOIN outputs AS o ON i.tx_hash = o.tx_hash
WHERE i.sender_address != o.receiver_address
    AND (
        i.sender_address IN (SELECT address FROM known_addresses)
        OR o.receiver_address IN (SELECT address FROM known_addresses)
    )
