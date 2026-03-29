{{ config(alias='addresses') }}

WITH labeled_addresses AS (
    SELECT DISTINCT
        ac.address,
        ac.cluster_id,
        ac.cluster_label,
        ac.cluster_label_source,
        ac.confidence_score,
        ac.risk_score AS cluster_risk_score,
        ac.is_change_address,
        ac.first_seen_blockheight,
        ac.last_seen_blockheight
    FROM {{ ref('btc_address_clusters') }} AS ac
),

sanctioned_addresses AS (
    SELECT DISTINCT address
    FROM {{ ref('btc_sanctioned') }}
),

vin_labels AS (
    SELECT DISTINCT address, label AS indexer_label
    FROM {{ ref('btc_vins') }}
    WHERE label IS NOT NULL AND label != ''
),

vout_labels AS (
    SELECT DISTINCT address, label AS indexer_label
    FROM {{ ref('btc_vouts') }}
    WHERE label IS NOT NULL AND label != ''
),

all_labels AS (
    SELECT * FROM vin_labels
    UNION
    SELECT * FROM vout_labels
)

SELECT
    la.address,
    la.cluster_id,
    la.cluster_label,
    la.cluster_label_source,
    la.confidence_score,
    la.cluster_risk_score,
    la.is_change_address,
    la.first_seen_blockheight,
    la.last_seen_blockheight,
    al.indexer_label,
    CASE WHEN sa.address IS NOT NULL THEN TRUE ELSE FALSE END AS is_sanctioned,
    COALESCE(la.cluster_label, al.indexer_label, 'unknown') AS display_label
FROM labeled_addresses AS la
LEFT JOIN sanctioned_addresses AS sa ON la.address = sa.address
LEFT JOIN all_labels AS al ON la.address = al.address
