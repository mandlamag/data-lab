{% macro btc_db_conn() %}
'host={{ env_var("BTC_DB_HOST") }} port={{ env_var("BTC_DB_PORT") }} dbname={{ env_var("BTC_DB_NAME") }} user={{ env_var("BTC_DB_USER") }} password={{ env_var("BTC_DB_PASSWORD") }}'
{% endmacro %}

{% macro labels_db_conn() %}
'host={{ env_var("LABELS_DB_HOST") }} port={{ env_var("LABELS_DB_PORT") }} dbname={{ env_var("LABELS_DB_NAME") }} user={{ env_var("LABELS_DB_USER") }} password={{ env_var("LABELS_DB_PASSWORD") }}'
{% endmacro %}
