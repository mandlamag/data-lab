{{ config(alias='entity_summary') }}

WITH entity_flows AS (
    SELECT
        a.display_label AS entity,
        a.cluster_id,
        a.is_sanctioned,
        COUNT(DISTINCT pf.tx_hash) AS tx_count,
        COUNT(DISTINCT pf.sender_address) AS unique_senders,
        COUNT(DISTINCT pf.receiver_address) AS unique_receivers,
        SUM(pf.output_amount_btc) AS total_volume_btc,
        MIN(pf.blockheight) AS first_block,
        MAX(pf.blockheight) AS last_block
    FROM {{ ref('btc_addresses') }} AS a
    JOIN {{ ref('btc_payment_flows') }} AS pf
        ON a.address = pf.sender_address OR a.address = pf.receiver_address
    GROUP BY a.display_label, a.cluster_id, a.is_sanctioned
)

SELECT
    entity,
    cluster_id,
    is_sanctioned,
    tx_count,
    unique_senders,
    unique_receivers,
    ROUND(total_volume_btc, 8) AS total_volume_btc,
    first_block,
    last_block,
    last_block - first_block AS block_span
FROM entity_flows
ORDER BY total_volume_btc DESC
