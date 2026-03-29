{{ config(alias='address_clusters') }}

SELECT
    address,
    cluster_id,
    first_seen_blockheight,
    last_seen_blockheight,
    is_change_address,
    change_of_cluster,
    cluster_label,
    cluster_label_source,
    confidence_score,
    risk_score
FROM postgres_scan(
    {{ labels_db_conn() }},
    'clustering',
    'address_clusters'
)
WHERE cluster_label IS NOT NULL
