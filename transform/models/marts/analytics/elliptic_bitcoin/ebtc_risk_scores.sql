{{ config(alias='risk_scores') }}

WITH illicit_txs AS (
    SELECT tx_id
    FROM {{ ref('ebtc_transactions') }}
    WHERE tx_class = 'illicit'
),

direct_illicit_neighbors AS (
    SELECT
        e.target_tx_id AS tx_id,
        COUNT(DISTINCT e.source_tx_id) AS inbound_illicit_count
    FROM {{ ref('ebtc_edges') }} AS e
    WHERE e.source_tx_id IN (SELECT tx_id FROM illicit_txs)
    GROUP BY e.target_tx_id

    UNION ALL

    SELECT
        e.source_tx_id AS tx_id,
        COUNT(DISTINCT e.target_tx_id) AS inbound_illicit_count
    FROM {{ ref('ebtc_edges') }} AS e
    WHERE e.target_tx_id IN (SELECT tx_id FROM illicit_txs)
    GROUP BY e.source_tx_id
),

illicit_neighbor_counts AS (
    SELECT
        tx_id,
        SUM(inbound_illicit_count) AS illicit_neighbor_count
    FROM direct_illicit_neighbors
    GROUP BY tx_id
),

total_neighbor_counts AS (
    SELECT tx_id, COUNT(*) AS total_neighbors FROM (
        SELECT source_tx_id AS tx_id FROM {{ ref('ebtc_edges') }}
        UNION ALL
        SELECT target_tx_id AS tx_id FROM {{ ref('ebtc_edges') }}
    )
    GROUP BY tx_id
)

SELECT
    t.tx_id,
    t.tx_class,
    t.time_step,
    COALESCE(ic.illicit_neighbor_count, 0) AS illicit_neighbor_count,
    COALESCE(tc.total_neighbors, 0) AS total_neighbors,
    CASE
        WHEN t.tx_class = 'illicit' THEN 1.0
        WHEN tc.total_neighbors = 0 THEN 0.0
        ELSE ROUND(ic.illicit_neighbor_count * 1.0 / tc.total_neighbors, 4)
    END AS risk_score
FROM {{ ref('ebtc_transactions') }} AS t
LEFT JOIN illicit_neighbor_counts AS ic ON t.tx_id = ic.tx_id
LEFT JOIN total_neighbor_counts AS tc ON t.tx_id = tc.tx_id
WHERE t.tx_class != 'illicit'
ORDER BY risk_score DESC
