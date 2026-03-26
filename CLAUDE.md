# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Data Lab is a minimalist data engineering and ML operations platform built on DuckLake (DuckDB-backed data lakehouse). It uses on-premise infrastructure via Proxmox, Terraform, and Docker. All data flows through a single S3 bucket (MinIO).

## Tech Stack

- **Python 3.13** with `uv` package manager
- **Task runner**: `just` (justfile at project root)
- **CLI**: `dlctl` (entry point: `dlctl/cli.py`, registered via `pyproject.toml` scripts)
- **Data transformation**: dbt-core + dbt-duckdb
- **Storage**: DuckDB + DuckLake, MinIO (S3), PostgreSQL (catalog)
- **Graph DB**: KùzuDB
- **ML**: PyTorch, scikit-learn, XGBoost, MLflow, sentence-transformers
- **LLM**: LangChain + Ollama
- **API**: FastAPI + Uvicorn
- **Streaming**: Kafka (aiokafka)
- **Infra**: Terraform (Proxmox provider), Docker Compose

## Common Commands

```bash
uv sync                    # Install dependencies
just                       # List all available tasks
dlctl --help               # CLI help

# Testing
uv run pytest              # Run all tests
uv run pytest tests/test_graph.py          # Run single test file
uv run pytest tests/test_graph.py::test_fn -k "pattern"  # Run specific test

# dbt (transformation layer)
dlctl transform            # Run dbt transformations
dlctl transform -m "+model_name"  # Run specific model

# Infrastructure
just infra-provision-local  # Start local dev services (Docker Compose with dev profile)
just infra-destroy-local    # Stop local dev services
just lakehouse              # Open DuckDB CLI with init.sql loaded
```

## Architecture

### Module Structure

All modules are Python packages registered in `pyproject.toml` under `tool.setuptools.packages.find`:

| Module | Purpose |
|--------|---------|
| `dlctl/` | CLI interface (Click-based). Routes to other modules' CLI commands. |
| `ingest/` | Data ingestion from Kaggle, HuggingFace, manual sources. Creates raw data + manifests. |
| `transform/` | dbt project. Models organized by stage (raw → cleaned) and marts (graphs, analytics). Profile name: `transform`. |
| `export/` | Exports gold-tier datasets from marts to S3. |
| `graph/` | KùzuDB operations: load from S3 parquet, node embeddings (FRP/PyTorch), RAG. |
| `ml/` | Full ML lifecycle: feature extraction, training, MLflow tracking, FastAPI inference server, A/B testing, monitoring (drift detection). |
| `shared/` | Shared utilities: `settings.py` (env config), `storage.py` (S3 ops), `lakehouse.py` (DuckDB engine), `cache.py`, `logging.py`, `templates.py`. |

### Infrastructure Layers (infra/)

4-layer Terraform + Docker architecture:
1. **Foundation** (`infra/foundation/`) — MinIO on Proxmox LXC
2. **Platform** (`infra/platform/`) — Docker VMs + GitLab VM on Proxmox (state in MinIO)
3. **Services** (`infra/services/`) — Docker Compose (MinIO, PostgreSQL, Ollama, MLflow, etc.) + GitLab CI/CD vars
4. **Applications** (`infra/apps/`) — Docker-based apps (ML server)

### S3 Storage Layout

```
s3://lakehouse/
├── backups/catalog/   # DuckLake catalog backups
├── raw/               # Raw ingested data
├── stage/             # Staged/cleaned data (DuckLake parquet)
├── marts/             # Domain-specific marts (graphs/, analytics/)
└── exports/           # Exported datasets
```

### Data Pipelines

Three main pipelines, each following ingest → transform → export → consume:
- **GraphRAG**: Deezer social networks + Million Song Dataset → KùzuDB graph → embeddings → RAG
- **Economic Competition Networks**: Atlas of Economic Complexity → graph → competition scoring
- **MLOps**: Depression detection datasets → dbt staging → ML training → FastAPI inference → Kafka logging → monitoring

## CI/CD

- **GitHub Actions** (`.github/workflows/release.yml`): Semantic release on push to main (conventional commits)
- **GitLab CI** (`.gitlab-ci.yml`): Docker-based deployment, PostgreSQL provisioning, Kafka topics, Ollama models. Modular configs in `.ci/`.

## Configuration

- Environment variables defined in `.env.example` (S3, PostgreSQL, DuckLake paths, KùzuDB, Ollama, MLflow, Kafka)
- `just` auto-loads `.env` (via `set dotenv-load` in justfile)
- Pytest config in `pyproject.toml`: `--capture=no --maxfail=1 --disable-warnings`

## Conventions

- Conventional commits required (parsed by python-semantic-release)
- When adding/removing Python dependencies: `export UV_FIND_LINKS="https://data.pyg.org/whl/torch-2.7.0+cu126.html"` before running uv commands (for PyTorch Geometric wheels)
