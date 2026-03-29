{{ config(alias='sanctioned', materialized='view') }}

SELECT *
FROM postgres_scan(
    {{ labels_db_conn() }},
    'sanctions',
    'sanctioned'
)
