SELECT
    sn.node_id AS source_id,
    tn.node_id AS target_id
FROM {{ ref('ebtc_edges') }} AS e
JOIN {{ ref('nodes_transactions') }} AS sn
    ON e.source_tx_id = sn.tx_id
JOIN {{ ref('nodes_transactions') }} AS tn
    ON e.target_tx_id = tn.tx_id
ORDER BY source_id, target_id
