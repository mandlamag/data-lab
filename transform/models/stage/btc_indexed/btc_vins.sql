{{ config(alias='vins') }}

SELECT *
FROM postgres_query(
    {{ btc_db_conn() }},
    '
    SELECT hash, idx, vin, blockheight, txid, vout, address, amount, label
    FROM vins
    WHERE label IS NOT NULL AND label != ''''
    ORDER BY blockheight DESC
    LIMIT 500000
    '
)
