{{ config(
    alias='kyt_responses',
    pre_hook="DROP TABLE IF EXISTS {{ this.database }}.{{ this.schema }}.kyt_responses__dbt_tmp"
) }}

SELECT
    id,
    content,
    metadata,
    created_at
FROM postgres_scan(
    {{ labels_db_conn() }},
    'kyt',
    'responses'
)
