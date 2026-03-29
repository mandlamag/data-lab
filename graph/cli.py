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


@graph.command(help="Visualize a subgraph (illicit network or around a tx_id)")
@click.argument("schema", type=click.STRING)
@click.option("--tx-id", type=click.STRING, help="Center visualization on a transaction ID")
@click.option("--illicit", is_flag=True, help="Show the illicit subgraph (sampled)")
@click.option("--high-risk", is_flag=True, help="Show high-risk transactions and their neighbors")
@click.option("-n", "--max-nodes", default=100, type=click.INT, help="Max nodes to display")
def visualize(schema: str, tx_id: str, illicit: bool, high_risk: bool, max_nodes: int):
    import random

    from graph.visualization import plot

    ops = GraphOps(schema)

    if tx_id:
        node = ops.get_node_by_tx_id(tx_id)
        if node is None:
            log.error("Transaction {} not found", tx_id)
            return
        center_id = node["node_id"]
        reachable = ops.bfs(center_id)
        node_ids = reachable[:max_nodes]
    elif illicit:
        # Pick a random illicit node and BFS from it to get a connected subgraph
        illicit_ids = [
            props["node_id"]
            for props in ops._node_props.values()
            if props.get("tx_class") == "illicit"
        ]
        if not illicit_ids:
            log.error("No illicit transactions found")
            return
        seed = random.choice(illicit_ids)
        reachable = ops.bfs(seed)
        # Prioritize illicit nodes and their direct neighbors
        illicit_set = set(illicit_ids)
        node_ids = [n for n in reachable if n in illicit_set][:max_nodes]
        # Fill remaining with neighbors of included illicit nodes
        remaining = max_nodes - len(node_ids)
        included = set(node_ids)
        for nid in list(node_ids):
            if remaining <= 0:
                break
            idx = ops._id_to_idx.get(nid)
            if idx is None:
                continue
            for n in ops.graph.outgoing_neighbors(idx):
                neighbor_id = ops._idx_to_id.get(n)
                if neighbor_id and neighbor_id not in included:
                    node_ids.append(neighbor_id)
                    included.add(neighbor_id)
                    remaining -= 1
                    if remaining <= 0:
                        break
    elif high_risk:
        risk_df = ops.high_risk_transactions(threshold=0.5)
        seed_ids = risk_df["node_id"].head(max_nodes // 3).tolist()
        node_ids = set(seed_ids)
        for nid in seed_ids:
            idx = ops._id_to_idx.get(nid)
            if idx is None:
                continue
            for n in ops.graph.outgoing_neighbors(idx):
                node_ids.add(ops._idx_to_id.get(n, n))
            for n in ops.graph.incoming_neighbors(idx):
                node_ids.add(ops._idx_to_id.get(n, n))
        node_ids = list(node_ids)[:max_nodes]
    else:
        log.error("Specify --tx-id, --illicit, or --high-risk")
        return

    G = ops.to_networkx(node_ids)
    log.info("Visualizing {} nodes, {} edges", G.number_of_nodes(), G.number_of_edges())

    illicit_ids = [
        nid for nid, data in G.nodes(data=True) if data.get("tx_class") == "illicit"
    ]
    licit_ids = [
        nid for nid, data in G.nodes(data=True) if data.get("tx_class") == "licit"
    ]

    plot(
        G,
        name_prop="tx_id",
        node_classes={"illicit": illicit_ids, "licit": licit_ids},
        scale=0.5,
        font_size=6,
    )


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
