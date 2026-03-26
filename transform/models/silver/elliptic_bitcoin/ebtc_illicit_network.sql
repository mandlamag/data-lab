{{ config(alias='illicit_network') }}

WITH illicit_txs AS (
    SELECT tx_id
    FROM {{ ref('ebtc_transactions') }}
    WHERE tx_class = 'illicit'
),

direct_neighbors AS (
    SELECT DISTINCT target_tx_id AS tx_id
    FROM {{ ref('ebtc_edges') }} AS e
    WHERE e.source_tx_id IN (SELECT tx_id FROM illicit_txs)

    UNION

    SELECT DISTINCT source_tx_id AS tx_id
    FROM {{ ref('ebtc_edges') }} AS e
    WHERE e.target_tx_id IN (SELECT tx_id FROM illicit_txs)
),

network_tx_ids AS (
    SELECT tx_id FROM illicit_txs
    UNION
    SELECT tx_id FROM direct_neighbors
)

SELECT
    t.tx_id,
    t.tx_class,
    t.time_step,
    CASE
        WHEN t.tx_class = 'illicit' THEN 'direct'
        ELSE 'neighbor'
    END AS illicit_proximity
FROM {{ ref('ebtc_transactions') }} AS t
WHERE t.tx_id IN (SELECT tx_id FROM network_tx_ids)
