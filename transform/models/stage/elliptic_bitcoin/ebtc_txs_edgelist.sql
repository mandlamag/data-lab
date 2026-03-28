{{ config(alias='txs_edgelist') }}

SELECT
    CAST(txId1 AS VARCHAR) AS source_tx_id,
    CAST(txId2 AS VARCHAR) AS target_tx_id
FROM read_csv(
    '{{ env_var("RAW__ELLIPTIC_DATA_SET__ELLIPTIC_BITCOIN_DATASET__ELLIPTIC_TXS_EDGELIST", "NOT_FOUND") }}',
    delim = ',',
    header = true,
    columns = {
        'txId1': 'VARCHAR',
        'txId2': 'VARCHAR'
    }
)
