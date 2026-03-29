{{ config(
    alias='sanctioned',
    pre_hook="DROP TABLE IF EXISTS {{ this.database }}.{{ this.schema }}.sanctioned__dbt_tmp"
) }}

SELECT *
FROM postgres_scan(
    {{ labels_db_conn() }},
    'sanctions',
    'sanctioned'
)
