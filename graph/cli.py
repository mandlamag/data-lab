import os
from typing import Optional

import click
from loguru import logger as log

from graph.analytics import GraphAnalytics
from graph.embedding import NodeEmbedding, NodeEmbeddingAlgo
from graph.ops import GraphOps
from graph.rag import ContextAssemblerException, GraphRAG, GraphRetrievalException
from shared.lakehouse import Lakehouse
from shared.settings import env


@click.group(help="Load, manage, and run graph computations on trueno-graph")
def graph():
    pass


@graph.command(help="Load a graph from the lakehouse export")
@click.argument("schema", type=click.STRING)
@click.option("--overwrite", is_flag=True, help="Overwrite existing graph")
def load(schema: str, overwrite: bool):
    graph_catalog = os.path.splitext(os.path.split(env.str("GRAPHS_MART_DB"))[-1])[0]

    log.info("Loading {}.{} into trueno-graph", graph_catalog, schema)

    lh = Lakehouse()
    s3_path = lh.latest_export(graph_catalog, schema)

    if s3_path is None:
        log.error("Export not found for {}.{}", graph_catalog, schema)
        return

    log.info("Latest export: {}", s3_path)

    try:
        ops = GraphOps(schema, overwrite=overwrite)

        match schema:
            case "btc_txgraph":
                ops.load_btc_txgraph(s3_path)
            case _:
                raise click.UsageError(f"{schema}: graph not supported")
    except Exception as e:
        log.error(e)


@graph.group(help="Run graph computations")
def compute():
    pass


@compute.command(help="Compute node embeddings")
@click.argument("schema", type=click.STRING)
@click.option("-d", "--dimension", default=128, type=click.INT)
@click.option("-b", "--batch-size", default=512, type=click.INT)
@click.option("-e", "--epochs", default=1, type=click.INT)
@click.option(
    "-a",
    "--algo",
    type=click.Choice(algo.name for algo in NodeEmbeddingAlgo),
    default=NodeEmbeddingAlgo.FRP.name,
)
def embeddings(schema: str, dimension: int, batch_size: int, epochs: int, algo: str):
    try:
        e = NodeEmbedding(
            schema,
            dim=dimension,
            batch_size=batch_size,
            epochs=epochs,
            algo=NodeEmbeddingAlgo[algo],
        )
        e.train()
    except Exception as e:
        log.exception(e)


@compute.command(help="Compute risk scores for all transactions")
@click.argument("schema", type=click.STRING)
def risk_scores(schema: str):
    ga = GraphAnalytics(schema)
    df = ga.risk_summary()
    log.info("Top 20 high-risk transactions:\n{}", df.head(20).to_string())


@compute.command(help="Run community detection and analyze illicit concentration")
@click.argument("schema", type=click.STRING)
def communities(schema: str):
    ga = GraphAnalytics(schema)
    result = ga.community_analysis()
    log.info("Modularity: {}", result["modularity"])
    log.info("Communities: {}", result["num_communities"])
    for c in result["communities"][:10]:
        log.info(
            "  Community {}: {} nodes, {} illicit ({:.1f}%)",
            c["community_id"],
            c["size"],
            c["illicit_count"],
            c["illicit_pct"],
        )


@compute.command(help="Compute PageRank importance scores")
@click.argument("schema", type=click.STRING)
@click.option("-n", "--top-n", default=20, type=click.INT)
def pagerank(schema: str, top_n: int):
    ga = GraphAnalytics(schema)
    df = ga.pagerank_analysis(top_n=top_n)
    log.info("Top {} transactions by PageRank:\n{}", top_n, df.to_string())


@graph.command(help="Reindex embedding property")
@click.argument("schema", type=click.STRING)
def reindex(schema: str):
    try:
        ops = GraphOps(schema)
        ops.reindex_embeddings()
    except Exception as e:
        log.error(e)


@graph.command(help="Run GraphRAG pipeline on Bitcoin transaction graph")
@click.argument("schema", type=click.STRING)
@click.option("-i", "--interactive", is_flag=True, help="Interactive REPL mode")
@click.option("-q", "--query", type=click.STRING, help="Single query")
def rag(schema: str, interactive: bool, query: Optional[str]):
    gr = GraphRAG(schema)

    if interactive and query is not None:
        raise click.UsageError("--interactive and --query cannot be used together")

    if query is not None:
        try:
            response = gr.invoke(dict(user_query=query))
            log.info("Response:\n{}", response.content)
        except GraphRetrievalException as e:
            log.error("{}\n{}", e, e.query)
        except ContextAssemblerException as e:
            log.error(e)
    else:
        gr.interactive()


if __name__ == "__main__":
    graph()
