{{ config(alias='vins') }}

SELECT hash, idx, vin, blockheight, txid, vout, address, amount, label
FROM postgres_scan(
    {{ btc_db_conn() }},
    'public',
    'vins',
    filter_pushdown := true
)
WHERE label IS NOT NULL AND label != ''
LIMIT 500000
