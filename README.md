# 🧪 Data Lab

Tooling for a minimalist data lab running on top of DuckLake.

## 📋 Requirements

Minimum requirements:

- [uv](https://docs.astral.sh/uv/getting-started/installation/) with [Python 3.13](https://docs.astral.sh/uv/guides/install-python/#installing-a-specific-version) installed.
- Access to [RustFS](https://rustfs.com/), [MinIO](https://min.io/), or any [S3](https://aws.amazon.com/s3/)-compatible object storage.

> [!TIP]
> I keep a RustFS instance on my tiny home lab, made of an old laptop running Proxmox, but you can easily spin up a RustFS instance using the `rustfs` service using the `dev` profile under `infra/services/docker/compose.yml`, after setting up your `.env` (see below).

To run your own infrastructure, you'll also need:

- [Proxmox VE 9.x](https://proxmox.com/en/products/proxmox-virtual-environment/get-started)
- [Terraform 1.13.x](https://developer.hashicorp.com/terraform/install) (see [tfswitch](https://tfswitch.warrensbox.com/Installation/))
- [Docker 28.4.x](https://docs.docker.com/engine/install/)

> [!TIP]
> Most workflows are saved as [just](https://just.systems/man/en/) commands, which are available after you install `uv` dependencies and load the virtual environment. Run `just -l` to list all available commands (more details below).

## 🚀 Quick Start

### 1. Prerequisites

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and [Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Optionally install the [DuckDB CLI](https://duckdb.org/docs/installation/) for direct lakehouse access:

```bash
brew install duckdb
```

### 2. Clone and install

```bash
git clone git@github.com:mandlamag/data-lab.git
cd data-lab
uv sync
source .venv/bin/activate
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` — for **local development**, update these values:

```bash
# Point to localhost (Docker runs locally, not on a remote VM)
S3_ENDPOINT=localhost:9000
PSQL_CATALOG_HOST=localhost
MLFLOW_TRACKING_URI=http://localhost:5000
KAFKA_BROKER_ENDPOINT=localhost:9092

# Set your S3 credentials (these become your RustFS admin login)
S3_ACCESS_KEY_ID=admin
S3_SECRET_ACCESS_KEY=supersecret
```

> [!TIP]
> If you're having trouble connecting to your S3-compatible store, make sure you're using the correct zone, which you set via the `S3_REGION` variable in `.env`.

### 4. Start all services

Spin up the full local infrastructure (RustFS, PostgreSQL, Ollama, Open WebUI, MLflow, Kafka, Portainer):

```bash
just infra-provision-local
```

Or start just the S3 store if that's all you need:

```bash
docker compose -p datalab -f infra/services/docker/compose.yml \
    --profile dev up rustfs rustfs-init -d
```

Wait for all services to be healthy:

```bash
docker compose -p datalab -f infra/services/docker/compose.yml --profile dev ps
```

### 5. Provision PostgreSQL for DuckLake

DuckLake uses PostgreSQL to store catalog metadata. Run this once to create the database and user:

```bash
docker exec datalab-postgres-1 psql -U root -c "CREATE USER lakehouse WITH PASSWORD 'lakehouse';"
docker exec datalab-postgres-1 psql -U root -c "CREATE DATABASE lakehouse;"
docker exec datalab-postgres-1 psql -U root -c "GRANT ALL PRIVILEGES ON DATABASE lakehouse TO lakehouse;"
docker exec datalab-postgres-1 psql -U root -c "ALTER DATABASE lakehouse OWNER TO lakehouse;"
```

> [!NOTE]
> This step is automated via CI/CD on the on-premise infrastructure, but needs to be done manually for local development. You only need to run it once.

### 6. Verify lakehouse connection

Generate the `init.sql` and open the DuckLake REPL:

```bash
just lakehouse
```

You should see a DuckDB REPL with all catalogs attached (stage, silver, graphs, analytics). Type `.quit` to exit.

### 7. Service URLs

Once everything is running, you can access:

| Service | URL |
|---------|-----|
| RustFS Console | http://localhost:9001 |
| MLflow | http://localhost:5000 |
| Open WebUI (Ollama) | http://localhost:8080 |
| Portainer | http://localhost:9080 |

The general workflow you're expected to follow for data engineering is illustrated in the following diagram:

![Data Lab Architecture Diagram](docs/datalab-architecture.png)

You're expected to implement your own [dbt](https://docs.getdbt.com/) models to power `dlctl transform`. We provide an example of this under `transform/models/`, based on the following Kaggle datasets:

- [andreagarritano/deezer-social-networks](https://www.kaggle.com/datasets/andreagarritano/deezer-social-networks)
- [undefinenull/million-song-dataset-spotify-lastfm](https://www.kaggle.com/datasets/undefinenull/million-song-dataset-spotify-lastfm)

A few datasets are already supported and pipelines are encoded using `just` commands (e.g., `econ-compnet-etl`, `graphrag-etl`, `mlops-etl`, `btc-txgraph-etl`, which correspond to projects with their own YouTube videos).

### Bitcoin Transaction Graph (Quick Start)

The Bitcoin transaction graph pipeline uses the [Elliptic dataset](https://www.kaggle.com/datasets/ellipticco/elliptic-data-set) (~203K transactions, ~234K edges, labeled illicit/licit/unknown) and demonstrates the **medallion architecture** (bronze → silver → gold):

```bash
# Run the full ETL pipeline (ingest → bronze → silver → gold → export → graph)
just btc-txgraph-etl

# Or run each medallion layer individually
just btc-txgraph-ingest            # Download Elliptic dataset from Kaggle
just btc-txgraph-transform-bronze  # Bronze: raw CSV → DuckLake stage tables
just btc-txgraph-transform-silver  # Silver: enriched transactions, validated edges, illicit network
just btc-txgraph-transform-gold    # Gold: graph-ready nodes/edges + risk scores & analytics

# Export and load into KuzuDB
just btc-txgraph-export
just btc-txgraph-load

# Compute node embeddings and launch GraphRAG REPL
just btc-txgraph-embeddings
just btc-txgraph-rag

# Or run everything end-to-end
just btc-txgraph-all
```

Once loaded, you can query the medallion layers in the DuckLake:

```sql
-- Bronze: raw ingested data
SELECT * FROM stage.ebtc.txs_features LIMIT 5;

-- Silver: enriched with labels
SELECT * FROM silver.ebtc.transactions WHERE tx_class = 'illicit' LIMIT 5;

-- Silver: 1-hop illicit neighborhood
SELECT * FROM silver.ebtc.illicit_network WHERE illicit_proximity = 'neighbor' LIMIT 10;

-- Gold: risk scores for unknown transactions
SELECT * FROM analytics.ebtc.risk_scores WHERE tx_class = 'unknown' ORDER BY risk_score DESC LIMIT 10;

-- Gold: temporal activity distribution
SELECT * FROM analytics.ebtc.time_step_summary;
```

And in the GraphRAG REPL (`just btc-txgraph-rag`):

```cypher
-- Transactions within 2 hops of illicit activity
MATCH (t:Transaction)-[*1..2]-(n:Transaction {tx_class: 'illicit'})
RETURN DISTINCT t.tx_id, t.tx_class, t.time_step
LIMIT 100;

-- Top unknown transactions by illicit exposure
MATCH (t:Transaction {tx_class: 'unknown'})-[:Pays*1..2]-(i:Transaction {tx_class: 'illicit'})
RETURN t.tx_id, count(DISTINCT i) AS illicit_neighbors
ORDER BY illicit_neighbors DESC LIMIT 20;
```

You can learn all other details below.

## 🧩 Components

### dlctl/

This is where the `dlctl` command lives—standing for 'Data Lab Control'. This helps you run all the tasks supported by the data lab package. It is available as a script under [pyproject.toml](pyproject.toml#L31) and it can be accessed via:

```bash
uv sync
source .venv/bin/activate
dlctl ...
```

> [!NOTE]
> A few `torch` dependencies, like `torch_sparse` require `UV_FIND_LINKS` to be set when adding or removing any dependencies, but not during install, where `uv.lock` already has all the required information. We currently don't rely on this, but, if we do in the future, here's how to approach it:
>
> ```bash
> export UV_FIND_LINKS="https://data.pyg.org/whl/torch-2.7.0+cu126.html"
> uv add --no-build-isolation pyg_lib torch_scatter torch_sparse \
>   torch_cluster torch_spline_conv
> ```

### infra/

Implements a 4-layer infrastructure architecture to help you deploy a data stack on-premise using Proxmox, Terraform, and Docker.

![Infrastructure Architecture](./docs/infra-architecture.png)

- Layer 1 (`foundation/`) is a Terraform project that will provision object storage (MinIO/RustFS) on an LXC running on Proxmox.
- Layer 2 (`platform/`) is a Terraform project, with state storage on the object store from Layer 1, that will provision three Docker VMs and a GitLab VM. GitLab will provide a container registry and come preconfigured with a GitLab Runner that executes on top of one of the Docker VMs.
- Layer 3 (`services/`) contains a Terraform project (`gitlab/`) to optionally initialize CI/CD variables/secrets from the local `.env`, and a Docker Compose project (`docker/`) to provision the data stack services.
- Layer 4 (`applications/`) contains local application deployments via Dockerized services (e.g., `ml.server`) and CI/CD integration to provision the required resources (e.g., postgres database and credentials).

### ingest/

Helps manage ingestion from difference data sources, creating the proper directory structure (see [Storage Layout](#%EF%B8%8F-storage-layout)) consisting of the retrieval for raw data and the creation proper directory structure creation. Raw data might be dropped manually, from Kaggle, Hugging Face, or some other source. This will make it easy to load it and keep it organized.

### transform/

This is the core of the data lakehouse, using [dbt](https://docs.getdbt.com/) to transform raw data into usable data, with [DuckLake](https://ducklake.select/) as the underlying catalog backed by PostgreSQL. Data follows a **medallion architecture**: bronze (stage) → silver (enriched) → gold (marts).

The dbt models are organized under `transform/models/` into `stage/` (bronze), `silver/`, and `marts/` (gold) layers, each backed by its own DuckLake catalog with data stored in S3.

### export/

Gold tier datasets under your data marts are only usable externally after you export them. This component manages exports, creating them for a specific data mart catalog and schema, listing them, or purging old versions.

### graph/

Graph loading and computation on top of KùzuDB. We support operations like graph loading from S3 parquet files, and node embedding via FRP (Fast Random Projection), which is implemented using node batching with input/output from/to KùzuDB and training on top of PyTorch.

### ml/

Complete ML Engineering lifecycle implementation, including feature extraction, and model training and testing, with MLflow experiment tracking and evaluation. It also provides a REST API endpoint for inference, prediction logging, and user feedback tracking, implemented using an even-driven architecture based on Kafka topics. This optionally serves models using an A/B/n testing approach. Finally, we also implement several methods for simulating inference requests and user feedback, based on a monitoring dataset, that we use to compute monitoring metrics over time, like prediction drift, feature drift, estimated performance, or user evaluation.

### shared/

Includes the following modules:

- `settings` – loads and provides access to environment variables and other relevant constants;
- `storage` – handles mid-level S3 storage operations, like creating a dated directory structure, uploading and downloading files and directories, or managing the manifest files;
- `cache` – provides utilities to manage filesystem-based caching based on a user data directory (usually `~/.cache/datalab`);
- `lakehouse` – connects the DuckDB engine and helps with tasks like exporting datasets, or loading the latest snapshot for an export;
- `templates` – contains helper functions and `string.Template` instances to produce files like `init.sql`;
- `color` – palette and color processing utilities, mostly used to support plotting;
- `logging` – interceptor logger to replace inconsistent logging utilities (e.g., from `uvicorn`).
- `tools` – provides a function per CLI tool (callable via `dlctl tools`), for example to generate the `init.sql` file described in the `templates` module;
- `utils` – provides a `@timed` annotator to print run time, and function name sanitization code.

### notebooks/

Jupyter notebook for prototyping or standalone analyzes. Notebooks are dropped directly on the root path, since all data is loaded and saved to the DuckLake instance.

### scripts/

Individual Bash or Python scripts for generic tasks (e.g., launching KùzuDB Explorer).

### local/

Untracked directory where all your local files will live. This includes the DuckDB engine database (`engine.duckdb`), which you can restore from a [backup](#backup) or create from scratch. KùzuDB databases will also live here, under `graphs/`, as well as the `init.sql` script for CLI access to the lakehouse. DuckLake catalog metadata is stored in PostgreSQL (not locally).


## 🗃️ Storage Layout

All data is stored in a single S3 bucket (e.g., `s3://lakehouse`, tested with RustFS and MinIO), with directory structure:

```
s3://lakehouse/
├── backups/
│   └── catalog/
│       ├── YYYY_MM_DD/
│       │   └── HH_mm_SS_sss/
│       │       └── lakehouse.dump
│       └── manifest.json
├── raw/                              ← Bronze: raw ingested data
│   └── <dataset-name>/
│       ├── YYYY_MM_DD/
│       │   └── HH_mm_SS_sss/
│       │       ├── *.csv
│       │       ├── *.json
│       │       └── *.parquet
│       └── manifest.json
├── stage/                            ← Bronze: DuckLake staged tables
│   └── ducklake-*.parquet
├── silver/                           ← Silver: enriched, validated data
│   └── ducklake-*.parquet
├── marts/                            ← Gold: domain-specific marts
│   └── <domain>/
│           └── ducklake-*.parquet
└── exports/
    └── <domain>/
        └── <dataset-name>/
            ├── YYYY_MM_DD/
            │   └── HH_mm_SS_sss/
            │       ├── *.csv
            │       ├── *.json
            │       └── *.parquet
            └── manifest.json
```

> [!NOTE]
> Date/time entries should be always UTC.

## ⚙️ Configuration

Configuration for data lab is all done through the environment variables defined in `.env`.

This will also support the generation of an `init.sql` file, which contains the DuckLake configurations, including the S3 secret and all attached catalogs (including the silver medallion layer).

### Environment Variables

#### S3 Configurations

```bash
S3_ENDPOINT=localhost:9000
S3_USE_SSL=false
S3_URL_STYLE=path
S3_ACCESS_KEY_ID=your_access_key
S3_SECRET_ACCESS_KEY=your_secret_key
S3_REGION=eu-west-1
```

`S3_ENDPOINT` and `S3_URL_STYLE` are only required if you're using a non-AWS object store like RustFS or MinIO.

`S3_REGION` must match your object store's region (explicitly setting one is recommended).

#### PostgreSQL

```bash
PSQL_ROOT_PASSWORD=datalabtech
```

Set this to the `root` user password of your PostgreSQL database—only used when deploying your on-premise infrastructure, so that databases and credentials can be provisioned at a later stage. Otherwise not accessed.

#### Data Lab Specifics

```bash
S3_BUCKET=lakehouse
S3_INGEST_PREFIX=raw
S3_STAGE_PREFIX=stage
S3_SILVER_PREFIX=silver
S3_SECURE_STAGE_PREFIX=secure-stage
S3_GRAPHS_MART_PREFIX=marts/graphs
S3_ANALYTICS_MART_PREFIX=marts/analytics
S3_EXPORTS_PREFIX=exports
S3_BACKUPS_PREFIX=backups
```

You can use the defaults here. Everything will live under the `S3_BUCKET`. Each stage has its own prefix under that bucket. The `S3_SILVER_PREFIX` is used for the silver medallion layer (enriched, validated data). The mart prefixes are special—any environment variable that ends with `*_MART_PREFIX` will be associated with its own `*_MART_DB`, as shown in the next section.

#### DuckLake Configurations

```bash
ENGINE_DB=engine.duckdb

PSQL_CATALOG_HOST=docker-shared
PSQL_CATALOG_PORT=5432
PSQL_CATALOG_DB=lakehouse
PSQL_CATALOG_USER=lakehouse
PSQL_CATALOG_PASSWORD=lakehouse
PSQL_CATALOG_STAGE_SCHEMA=stage
PSQL_CATALOG_SILVER_SCHEMA=silver
PSQL_CATALOG_SECURE_STAGE_SCHEMA=secure_stage
PSQL_CATALOG_GRAPHS_MART_SCHEMA=graphs
PSQL_CATALOG_ANALYTICS_MART_SCHEMA=analytics
```

The DuckDB `ENGINE_DB` lives under `local/` and is used for querying. DuckLake catalog metadata is stored in PostgreSQL, with one schema per catalog layer (stage, silver, graphs, analytics). All data is stored in S3 at the corresponding prefixes. `SECURE_STAGE` can be used if you need to encrypt your data (e.g., for sensitive user data).

#### Kuzu Configurations

```bash
MUSIC_TASTE_GRAPH_DB=graphs/music_taste.kuzu
ECON_COMP_GRAPH_DB=graphs/econ_comp.kuzu
BTC_TXGRAPH_GRAPH_DB=graphs/btc_txgraph.kuzu
```

The data lab also leverages [Kuzu](https://kuzudb.com/) for graph data science tasks. The path for each graph database can be set here as `*_GRAPH_DB`.

#### Ollama Configurations

```bash
OLLAMA_MODELS=gemma3:latest,phi4:latest
```

Here you can preconfigure the Ollama models you want to download when running your local or on-premise infrastructure, as comma-separated `model:version` entries.

#### MLflow Configurations

```bash
MLFLOW_TRACKING_URI=http://docker-shared:5000
MLFLOW_TRACKING_USERNAME=datalabtech
S3_MLFLOW_BUCKET=mlflow
S3_MLFLOW_ARTIFACTS_PREFIX=artifacts
```

The `MLFLOW_TRACKING_*` variables configure how you interact with the MLflow server, while the `S3_MLFLOW_*` variables configure the S3 bucket where artifacts (e.g., serialized models) will be dropped into.

#### Kafka Configurations

```bash
KAFKA_BROKER_ENDPOINT=docker-shared:9092
KAFKA_GROUP_TOPIC_LIST=ml_inference_results:lakehouse-inference-result-consumer,ml_inference_feedback:lakehouse-inference-feedback-consumer
```

You can configure your Kafka endpoint here, as well as any required topics. We initialize each topic via comma-separated list of `topic:group`, so that consumers can be initialized and no warning is printed when first connecting to a topic from that consumer—this is likely overkill, but it feels cleaner.

### Generating init.sql

You can generate an `init.sql` once you setup your `.env`, so you can access your DuckLake from the CLI using `duckdb`:

```bash
dlctl tools generate-init-sql
duckdb -init local/init.sql local/engine.duckdb
```

## 📖 Usage

### Ingestion

As a rule of thumb, ingestion will be done via the `dlctl ingest` command. If a version for the current date already exists, it will output an error and do nothing—just wait a millisecond.

#### Manual

For manually uploaded datasets, you can create a directory in S3 by giving it the dataset name:

```bash
dlctl ingest dataset --manual "Your Dataset Name"
```

This will create a directory like `s3://lakehouse/raw/your_dataset_name/2025_06_03/19_56_03_000`, update `s3://lakehouse/raw/your_dataset_name/manifest.json` to point to it, and print the path to stdout.

#### From Kaggle or Hugging Face

```bash
dlctl ingest dataset \
    "https://www.kaggle.com/datasets/<username>/<dataset>"

dlctl ingest dataset \
    "https://huggingface.co/datasets/<username>/<dataset>"
```

The dataset name will be automatically extracted from the `<dataset>` slug and transformed into snake case for storage. Then, a directory like `s3://lakehouse/raw/your_dataset_name/2025_06_03/19_56_03_000` will be created, `s3://lakehouse/raw/your_dataset_name/manifest.json` updated to point to it, and the final path printed to stdout.

#### Listing Ingested Datasets

You can also list existing dataset paths for the most recent version, to be used for transformation:

```bash
dlctl ingest ls
```

Or all of them:

```bash
dlctl ingest ls -a
```

#### Pruning Empty Datasets

Sometimes you'll manually create a dataset and never upload data into the directory, or an ingestion process from a URL will fail and leave an empty directory behind. You can prune those directories using:

```bash
dlctl ingest prune
```

### Transformation

Transformations can be done via `dlctl transform`, which will call `dbt` with the appropriate arguments:

```bash
dlctl transform "<dataset-name>"
```

You can also run data tests using:

```bash
dlctl test
dlctl test -m test_type:singular
```

Or generate or serve dbt documentation using:

```bash
dlctl docs generate
dlctl docs serve
```

### Export

#### Exporting to Parquet

In order to externally use a dataset from the Lakehouse, you first need to export it. This can be done for any data mart catalog, over a selected schema. Exported datasets will be kept in dated directories with their own `manifest.json`.

```bash
dlctl export dataset "<data-mart-catalog>" "<schema>"
```

#### Listing Exported Datasets

You can list the most recent versions of exported datasets:

```bash
dlctl export ls
```

Or all of them:

```bash
dlctl export ls -a
```

#### Pruning Empty Datasets

After a few exports, you might want to remove old versions to claim space. You can prune those directories using:

```bash
dlctl export prune
```

### Backup

Since we rely on S3 object storage and PostgreSQL for DuckLake catalog metadata, we provide backup/restore utilities for the local DuckDB engine database.

#### Create

You can create a backup by running:

```bash
dlctl backup create
```

#### Restore

In order to restore a backup, just run:

```bash
dlctl backup restore --source "<YYYY-mm-ddTHH:MM:SS.sss>"
```

Omitting `--source` will restore the latest backup.

> [!CAUTION]
> Omitting `--target` will restore to `local/` by default, so take care not to overwrite your working version by mistake!

#### List

You can list all backups using:

```bash
dlctl backup ls
```

And you can list all files in all backups using:

```bash
dlctl backup ls -a
```

### Graph

#### Load

This will load nodes and edges into a KùzuDB database stored under `local/graphs/<schema>`, where `schema` is a schema containing nodes and edges under the `graphs` data mart catalog. Table names for nodes or edges are usually prefixed with `<dataset>_nodes_` or `<dataset>_edges_`, respectively, and should follow the format described on KùzuDB's docs.

```bash
dlctl graph load "<schema>"
```

#### Compute

A collection of graph computation calls will live here. These can be wrappers to native KùzuDB computations, or external computations. Currently, we just include the `embeddings` computation, which runs in Python using PyTorch. This will compute FRP embeddings with dimension 256, over batches of 9216 nodes, trained using 5 epochs, for the `<schema>` graph:

```bash
dlctl graph compute embeddings "<schema>" -d 256 -b 9216 -e 5
```

### ML

#### Train

Train and evaluate a model using the `dataset` table under the provided `<schema>`, while tracking the experiment using MLflow:

```bash
dlctl ml train <schema> --method logreg --features embeddings
```

The `--method` can be one of the supported algorithms (e.g., `logreg` or `xgboost`), and `--features` follows a similar approach for supported features (e.g., `tfidf` or `embeddings`). Currently only text-based datasets are supported, but the schema and training code has been generalized to support tabular data as well.

#### Server

A REST API endpoint can be run to provide an inference service with optional A/B/n testing and event-based logging, or to receive user feedback on the predictions:

```bash
dlctl ml server
dlctl ml server -h 0.0.0.0 -p 8000
```

#### Simulate

In order to help us implement and test monitoring statistics, we implemented a request simulation framework, where feedback is provided based on a monitoring dataset, which is completely separate from the dataset using for training, validation and testing. For example, to use a 1% sample of the `monitor` table from `<schema>` for A/B testing with the `dd_xgboost_embeddings` and `dd_logreg_tfidf` latest models, we can use:

```bash
dlctl ml simulate <schema> \
    --sample-fraction 0.01 \
    --model-uri "models:/dd_xgboost_embeddings/latest" \
    --model-uri "models:/dd_logreg_tfidf/latest"
```

The `models:/` URIs correspond to models trained and logged within MLflow. For production, we usually replace `latest` with a particular tag that we assign to our production models (e.g., a version).

There are several other options to help you control the simulation as well, which you can check under:

```bash
dlctl ml simulate --help
```

These include the number of passes, the batch size, the decision threshold, and several ranges to help control the fraction of feedback to provide, the fraction of wrong feedback, or the date range to simulate.

#### Monitor

This will let you compute and plot monitor statistics over time for a specific `<schema>`, optionally specifying a date range and a window size:

```bash
dlctl ml monitor compute <schema>
dlctl ml monitor compute <schema> \
    --since <start> \
    --until <end> \
    --window-size 7
```

For plotting, you must also specify one or several model URIs:

```bash
dlctl ml monitor plot <schema> \
    --model-uri "models:/dd_xgboost_embeddings/latest" \
    --model-uri "models:/dd_logreg_tfidf/latest"
```

This will produce several PNG plots under `local/monitor/`.

## 🧾 Just Commands

We provide several `just` commands, both for convenience and to keep track of data pipelines (e.g., ETL) for specific datasets. Below we provide an overview on these commands, excluding most secondary commands.

### Common

We provide a `check binary` command that will look for a specific binary in the path and check whether it's executable—the command will fail otherwise, causing any depending commands to fail as well. We implement specific check commands per binary, since we cannot use parameters in dependencies. For example:

```bash
just check duckdb
just check-terraform
```

We also provide a `confirm` command, to add as a dependency of critical commands (e.g., `terraform destroy`). This will display a confirmation message and require user input to continue:

```bash
just confirm
```

```
Are you sure? [y/N] n
error: Recipe `confirm` failed with exit code 1
```

### DuckLake

**Related video:** https://youtu.be/zn69Q7FiFfo?si=tiG4DT_apbR_-sVC

In order to run a REPL for the datalab's DuckLake instance, you can simply run:

```bash
just lakehouse
```

This will take care of the `init.sql` generation for you, but you might want to regenerate it later as well:

```bash
just generate-init-sql
```

### GraphRAG with Kuzu

**Related video:** https://youtu.be/m61u3mqu1qY?si=kmjmPHTY5-8M8Q81

| Command | Description |
| ------- | ----------- |
| `graphrag-etl` | Ingest [DSN](https://www.kaggle.com/datasets/andreagarritano/deezer-social-networks) and [MSDSL](https://www.kaggle.com/datasets/undefinenull/million-song-dataset-spotify-lastfm) datasets, run DuckLake transformations, export to Parquet, and load graph into Kuzu. |
| `graphrag-embeddings` | Compute node embeddings of dimension 256 using 5 epochs and batches of size 9216, and create vector index. |
| `graphrag` | Launch REPL for graph RAG. |
| `graphrag-all` | Run all of the above, in order. |

### Economic Competition Networks

**Related video:** https://youtu.be/pIwN7oe54i4?si=-nB0upswBGacklh4

| Command | Description |
| ------- | ----------- |
| `econ-compnet-ingest` | Ingest [The Atlas of Economic Complexity](https://atlas.hks.harvard.edu/data-downloads). |
| `econ-compnet-transform` | Run DuckLake transformations on the dataset, to produce a knowledge graph. |
| `econ-compnet-export` | Export the graph data to Parquet. |
| `econ-compnet-load` | Load the graph into Kuzu. |
| `econ-compnet-etl` | Run all of the above, in order. |
| `econ-compnet-scoring` | Computes the Common Out-Neighbor (CON) score for the Country-CompetesWith-Country graph projection. |
| `econ-compnet-all` | Run ETL and scoring commands. |

### MLOps: A/B Testing with MLflow, Kafka, and DuckLake

**Related video:** https://youtu.be/MGuj13NcdjE?si=i56T6updcLE-NFC3

#### Training

| Command | Description |
| ------- | ----------- |
| `mlops-ingest` | Ingest the depression dataset for [training](https://huggingface.co/datasets/ShreyaR/DepressionDetection) and [monitoring](https://huggingface.co/datasets/joangaes/depression). |
| `mlops-transform` | Run DuckLake transformations on the datasets, normalizing into a common format for the ML pipelines, including a train/test split and fixed folds on the training set for validation. |
| `mlops-etl` | Run all of the above, in order. |
| `mlops-train-logreg-tfidf` | Train a model using logistic regression and TF-IDF features. |
| `mlops-train-logreg-embeddings` | Train a model using logistic regression and text embedding features. |
| `mlops-train-logreg` | Train all logistic regression models. |
| `mlops-train-xgboost-tfidf` | Train a model using XGBoost and TF-IDF features. |
| `mlops-train-xgboost-embeddings` | Train a model using XGBoost and text embedding features. |
| `mlops-train-xgboost` | Train all XGBoost models. |
| `mlops-train` | Train all models. |
| `mlops-all` | Run ETL and training. |

#### Inference

| Command | Description |
| ------- | ----------- |
| `mlops-serve` | Run ML server listening on 0.0.0.0 and port 8000. |
| `mlops-test-inference` | Use `curl` to test the inference endpoint. |
| `mlops-test-feedback` | Use `curl` to test the feedback endpoint. |

#### Monitoring

| Command | Description |
| ------- | ----------- |
| `mlops-simulate-inference` | Run inference simulation for XGBoost with text embedding features, and logistic regression with TF-IDF features, using the monitor set to produce feedback. |
| `mlops-monitor-compute` | Compute monitoring statistics for the two models. |
| `mlops-monitor-plot` | Plot monitoring statistics for the two models. |

### Bitcoin Transaction Graph (Elliptic)

This pipeline uses the [Elliptic dataset](https://www.kaggle.com/datasets/ellipticco/elliptic-data-set) to build a labeled Bitcoin transaction graph, showcasing the **medallion architecture** (bronze → silver → gold) end-to-end.

| Command | Description |
| ------- | ----------- |
| `btc-txgraph-ingest` | Ingest the [Elliptic Bitcoin dataset](https://www.kaggle.com/datasets/ellipticco/elliptic-data-set) (~203K transactions, ~234K edges). |
| `btc-txgraph-transform-bronze` | Bronze layer: stage raw CSVs into DuckLake (features, classes, edgelist). |
| `btc-txgraph-transform-silver` | Silver layer: enrich transactions with labels, validate edges, compute illicit 1-hop network. |
| `btc-txgraph-transform-gold` | Gold layer: produce graph-ready nodes/edges, risk scores, and time step analytics. |
| `btc-txgraph-transform` | Run all three medallion layers in order. |
| `btc-txgraph-export` | Export the graph mart to Parquet. |
| `btc-txgraph-load` | Load the graph into KuzuDB. |
| `btc-txgraph-etl` | Run full ETL: ingest → bronze → silver → gold → export → graph load. |
| `btc-txgraph-embeddings` | Compute node embeddings (dim 128, batch 4096, 5 epochs) and create vector index. |
| `btc-txgraph-rag` | Launch interactive GraphRAG REPL for Cypher queries over the Bitcoin graph. |
| `btc-txgraph-all` | Run ETL, embeddings, and launch RAG. |

### Data Lab Infra

**Related videos:** https://www.youtube.com/playlist?list=PLeKtvIdgbljMyhjPgJeoXwa_7J9DTx3Fo

#### Config Checks

| Command | Description |
| ------- | ----------- |
| `infra-config-check-foundation` | Look for `terraform.tfvars` under `infra/foundation`. |
| `infra-config-check-platform` | Look for `terraform.tfvars` and `state.config` under `infra/platform`. |
| `infra-config-check-services` | Look for the `docker-shared` context, that should point to the corresponding Docker VM. |
| `infra-config-check-all` | Run all of the above, in order. |

#### Initializations

| Command | Description |
| ------- | ----------- |
| `infra-foundation-init` | Run `terraform init` for `infra/foundation`. |
| `infra-platform-init` | Run `terraform init` for `infra/platform`. |
| `infra-init` | Run all of the above, in order. |

#### Provisioning

| Command | Description |
| ------- | ----------- |
| `infra-provision-foundation` | Run `terraform apply` for `infra/foundation`. |
| `infra-provision-platform` | Run `terraform apply` for `infra/platform`. |
| `infra-provision-services` | Run `terraform apply` for `infra/services/gitlab` (required a configured `.env`), and `docker compose up` under the appropriate `docker-shared` context, using `infra/services/docker/compose.yml`. |
| `infra-provision-all` | Run all of the above, in order. |
| `infra-provision-local` | Run `docker compose up` with the `dev` profile enabled (includes RustFS + init), using `infra/services/docker/compose.yml`. |

#### Destruction

| Command | Description |
| ------- | ----------- |
| `infra-destroy-foundation` | Run `terraform destroy` for `infra/foundation`. |
| `infra-destroy-platform` | Run `terraform destroy` for `infra/platform`. |
| `infra-destroy-services` | Run `docker compose down` and `terraform destroy` for `infra/services`. |
| `infra-destroy-all` | Run all of the above, in reversed order. |
| `infra-destroy-local` | Run `docker compose down` with the `dev` profile enabled for `infra/services`. |

#### Utilities

| Command | Description |
| ------- | ----------- |
| `infra-show-tf-credentials` `<layer>` | Print the credentials for a specific `layer` (`foundation` or `platform`). |
| `infra-show-credentials` | Print all credentials. |
