{{ config(alias='sanctioned') }}

SELECT *
FROM postgres_scan(
    {{ labels_db_conn() }},
    'sanctions',
    'sanctioned'
)
