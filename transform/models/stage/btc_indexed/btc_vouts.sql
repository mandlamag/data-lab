{{ config(alias='vouts') }}

SELECT *
FROM postgres_query(
    {{ btc_db_conn() }},
    '
    SELECT hash, idx, vout, blockheight, address, amount, label
    FROM vouts
    WHERE address IN (
        SELECT DISTINCT address
        FROM vouts
        WHERE label IS NOT NULL AND label != ''''
        LIMIT 100000
    )
    LIMIT 500000
    '
)
