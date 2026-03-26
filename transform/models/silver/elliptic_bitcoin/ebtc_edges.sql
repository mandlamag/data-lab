{{ config(alias='edges') }}

SELECT
    e.source_tx_id,
    e.target_tx_id
FROM {{ ref('ebtc_txs_edgelist') }} AS e
INNER JOIN {{ ref('ebtc_txs_features') }} AS sf
    ON e.source_tx_id = sf.tx_id
INNER JOIN {{ ref('ebtc_txs_features') }} AS tf
    ON e.target_tx_id = tf.tx_id
