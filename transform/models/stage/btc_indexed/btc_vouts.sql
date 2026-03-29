{{ config(alias='vouts') }}

SELECT
    hash,
    idx,
    vout,
    blockheight,
    address,
    amount,
    label
FROM postgres_scan(
    {{ btc_db_conn() }},
    'public',
    'vouts'
)
WHERE address IN (
    SELECT address
    FROM postgres_scan(
        {{ labels_db_conn() }},
        'clustering',
        'address_clusters'
    )
    WHERE cluster_label IS NOT NULL
)
