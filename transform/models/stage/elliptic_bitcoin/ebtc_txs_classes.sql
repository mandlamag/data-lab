{{ config(alias='txs_classes') }}

SELECT
    CAST(txId AS VARCHAR) AS tx_id,
    CASE class
        WHEN '1' THEN 'illicit'
        WHEN '2' THEN 'licit'
        ELSE 'unknown'
    END AS tx_class
FROM read_csv(
    '{{ env_var("RAW__ELLIPTIC_DATA_SET__ELLIPTIC_BITCOIN_DATASET__ELLIPTIC_TXS_CLASSES", "NOT_FOUND") }}',
    delim = ',',
    header = true,
    columns = {
        'txId': 'VARCHAR',
        'class': 'VARCHAR'
    }
)
