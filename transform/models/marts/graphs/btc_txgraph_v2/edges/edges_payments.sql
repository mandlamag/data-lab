SELECT
    sn.node_id AS source_id,
    tn.node_id AS target_id,
    pf.tx_hash,
    pf.blockheight,
    pf.output_amount_btc AS amount_btc,
    COUNT(*) AS tx_count
FROM {{ ref('btc_payment_flows') }} AS pf
JOIN {{ ref('nodes_addresses') }} AS sn ON pf.sender_address = sn.address
JOIN {{ ref('nodes_addresses') }} AS tn ON pf.receiver_address = tn.address
GROUP BY sn.node_id, tn.node_id, pf.tx_hash, pf.blockheight, pf.output_amount_btc
ORDER BY source_id, target_id
