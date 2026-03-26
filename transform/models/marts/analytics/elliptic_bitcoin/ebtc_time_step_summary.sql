{{ config(alias='time_step_summary') }}

WITH tx_counts AS (
    SELECT
        time_step,
        COUNT(*) AS total_txs,
        COUNT(*) FILTER (WHERE tx_class = 'illicit') AS illicit_txs,
        COUNT(*) FILTER (WHERE tx_class = 'licit') AS licit_txs,
        COUNT(*) FILTER (WHERE tx_class = 'unknown') AS unknown_txs
    FROM {{ ref('ebtc_transactions') }}
    GROUP BY time_step
),

edge_counts AS (
    SELECT
        t.time_step,
        COUNT(*) AS total_edges,
        COUNT(*) FILTER (WHERE sc.tx_class = 'illicit' OR tc.tx_class = 'illicit') AS illicit_edges
    FROM {{ ref('ebtc_edges') }} AS e
    JOIN {{ ref('ebtc_transactions') }} AS t ON e.source_tx_id = t.tx_id
    JOIN {{ ref('ebtc_txs_classes') }} AS sc ON e.source_tx_id = sc.tx_id
    JOIN {{ ref('ebtc_txs_classes') }} AS tc ON e.target_tx_id = tc.tx_id
    GROUP BY t.time_step
)

SELECT
    tc.time_step,
    tc.total_txs,
    tc.illicit_txs,
    tc.licit_txs,
    tc.unknown_txs,
    ROUND(tc.illicit_txs * 100.0 / tc.total_txs, 2) AS illicit_pct,
    ec.total_edges,
    ec.illicit_edges,
    ROUND(ec.illicit_edges * 100.0 / NULLIF(ec.total_edges, 0), 2) AS illicit_edge_pct
FROM tx_counts AS tc
LEFT JOIN edge_counts AS ec ON tc.time_step = ec.time_step
ORDER BY tc.time_step
