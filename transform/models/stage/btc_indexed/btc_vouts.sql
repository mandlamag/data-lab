{{ config(alias='vouts') }}

SELECT hash, idx, vout, blockheight, address, amount, label
FROM postgres_scan(
    {{ btc_db_conn() }},
    'public',
    'vouts'
)
WHERE label IS NOT NULL AND label != ''
LIMIT 500000
