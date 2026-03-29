SELECT
    row_number() OVER () AS node_id,
    a.address,
    a.cluster_id,
    a.cluster_label,
    a.display_label,
    a.cluster_risk_score,
    a.is_sanctioned,
    a.is_change_address,
    a.first_seen_blockheight,
    a.last_seen_blockheight
FROM {{ ref('btc_addresses') }} AS a
WHERE a.address IN (
    SELECT sender_address FROM {{ ref('btc_payment_flows') }}
    UNION
    SELECT receiver_address FROM {{ ref('btc_payment_flows') }}
)
