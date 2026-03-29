{{ config(alias='kyt_responses') }}

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
