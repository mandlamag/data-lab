import random
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from loguru import logger as log
from more_itertools import interleave_longest
from trueno_graph import Graph

from shared.settings import LOCAL_DIR, env
from shared.storage import Storage, StoragePrefix


class GraphOps:
    """Graph operations backed by trueno-graph (CSR).

    Loads transaction graph data from lakehouse parquet exports into a
    high-performance CSR representation. Currently supports btc_txgraph
    (Elliptic Bitcoin dataset), designed to extend to other blockchains.
    """

    def __init__(self, schema: str, overwrite: bool = False):
        dbname = env.str(f"{schema.upper()}_GRAPH_DB")
        db_path = Path(LOCAL_DIR) / dbname

        if db_path.exists() and overwrite:
            log.warning(f"Overwriting graph: {db_path}")
            if db_path.is_dir():
                shutil.rmtree(db_path)
            elif db_path.is_file():
                db_path.unlink()

        self.db_path = db_path
        self.schema = schema
        self.storage = Storage(prefix=StoragePrefix.EXPORTS)
        self.graph = Graph()

        # node_id (from parquet) <-> CSR index
        self._id_to_idx: dict[int, int] = {}
        self._idx_to_id: dict[int, int] = {}

        # Node properties: CSR index -> {tx_id, tx_class, time_step, ...}
        self._node_props: dict[int, dict[str, Any]] = {}

        # Embeddings stored separately for k-NN
        self._embedding_index: dict[int, np.ndarray] = {}

        if db_path.exists() and not overwrite:
            self._load_from_disk()

    # ── Data loading ─────────────────────────────────────────────────

    def _download_parquet(self, s3_path: str) -> pd.DataFrame:
        with tempfile.NamedTemporaryFile(suffix=".parquet") as tmp:
            self.storage.download_file(s3_path, tmp.name)
            return pd.read_parquet(tmp.name)

    def load_btc_txgraph(self, s3_path: str):
        """Load Bitcoin transaction graph from lakehouse export (Elliptic)."""
        try:
            self._load_btc_txgraph(s3_path)
            self._save_to_disk()
        except Exception as e:
            log.error("Failed to load btc_txgraph: {}", e)

    def load_btc_txgraph_v2(self, s3_path: str):
        """Load Bitcoin address graph from indexed blockchain data."""
        try:
            self._load_btc_txgraph_v2(s3_path)
            self._save_to_disk()
        except Exception as e:
            log.error("Failed to load btc_txgraph_v2: {}", e)

    def _load_btc_txgraph_v2(self, s3_path: str):
        log.info("Loading btc_txgraph_v2 address nodes")
        nodes_df = self._download_parquet(
            f"{s3_path}/nodes/nodes_addresses.parquet"
        )

        for _, row in nodes_df.iterrows():
            node_id = int(row["node_id"])
            idx = len(self._id_to_idx)
            self._id_to_idx[node_id] = idx
            self._idx_to_id[idx] = node_id
            self._node_props[idx] = {
                "node_id": node_id,
                "address": str(row.get("address", "")),
                "cluster_id": int(row["cluster_id"]) if pd.notna(row.get("cluster_id")) else None,
                "cluster_label": str(row.get("cluster_label", "")),
                "display_label": str(row.get("display_label", "")),
                "cluster_risk_score": float(row.get("cluster_risk_score", 0)),
                "is_sanctioned": bool(row.get("is_sanctioned", False)),
            }
            label = str(row.get("display_label", "") or row.get("address", ""))
            self.graph.set_node_name(idx, label)

        log.info("Loaded {} address nodes", len(self._id_to_idx))

        log.info("Loading btc_txgraph_v2 payment edges")
        edges_df = self._download_parquet(f"{s3_path}/edges/edges_payments.parquet")

        edge_count = 0
        for _, row in edges_df.iterrows():
            src_id = int(row["source_id"])
            dst_id = int(row["target_id"])
            src_idx = self._id_to_idx.get(src_id)
            dst_idx = self._id_to_idx.get(dst_id)
            weight = float(row.get("amount_btc", 1.0))
            if src_idx is not None and dst_idx is not None:
                self.graph.add_edge(src_idx, dst_idx, weight)
                edge_count += 1

        log.info(
            "Loaded graph: {} nodes, {} edges",
            self.graph.num_nodes,
            edge_count,
        )

    def _load_btc_txgraph(self, s3_path: str):
        log.info("Loading btc_txgraph nodes")
        nodes_df = self._download_parquet(
            f"{s3_path}/nodes/nodes_transactions.parquet"
        )

        for _, row in nodes_df.iterrows():
            node_id = int(row["node_id"])
            idx = len(self._id_to_idx)
            self._id_to_idx[node_id] = idx
            self._idx_to_id[idx] = node_id
            self._node_props[idx] = {
                "node_id": node_id,
                "tx_id": str(row["tx_id"]),
                "tx_class": str(row["tx_class"]),
                "time_step": int(row["time_step"]),
            }
            self.graph.set_node_name(idx, str(row["tx_id"]))

        log.info("Loaded {} transaction nodes", len(self._id_to_idx))

        log.info("Loading btc_txgraph edges")
        edges_df = self._download_parquet(f"{s3_path}/edges/edges_pays.parquet")

        edge_count = 0
        for _, row in edges_df.iterrows():
            src_id = int(row["source_id"])
            dst_id = int(row["target_id"])
            src_idx = self._id_to_idx.get(src_id)
            dst_idx = self._id_to_idx.get(dst_id)
            if src_idx is not None and dst_idx is not None:
                self.graph.add_edge(src_idx, dst_idx, 1.0)
                edge_count += 1

        log.info(
            "Loaded graph: {} nodes, {} edges",
            self.graph.num_nodes,
            edge_count,
        )

    # ── Persistence ──────────────────────────────────────────────────

    def _save_to_disk(self):
        self.db_path.mkdir(parents=True, exist_ok=True)

        records = []
        for idx, props in self._node_props.items():
            record = {**props, "_idx": idx}
            emb = self._embedding_index.get(idx)
            if emb is not None:
                record["embedding"] = emb.tolist()
            records.append(record)

        if records:
            pd.DataFrame(records).to_parquet(self.db_path / "nodes.parquet")

        # Save edge list
        edge_records = []
        for idx in range(self.graph.num_nodes):
            for neighbor in self.graph.outgoing_neighbors(idx):
                edge_records.append({
                    "src_idx": idx,
                    "dst_idx": neighbor,
                    "src_id": self._idx_to_id.get(idx),
                    "dst_id": self._idx_to_id.get(neighbor),
                })
        if edge_records:
            pd.DataFrame(edge_records).to_parquet(self.db_path / "edges.parquet")

    def _load_from_disk(self):
        log.info("Loading graph from {}", self.db_path)

        nodes_path = self.db_path / "nodes.parquet"
        if not nodes_path.exists():
            log.warning("No nodes.parquet at {}", self.db_path)
            return

        nodes_df = pd.read_parquet(nodes_path)

        # Vectorized mapping construction
        idxs = nodes_df["_idx"].astype(int).values
        node_ids = nodes_df["node_id"].astype(int).values
        tx_ids = nodes_df["tx_id"].astype(str).values
        tx_classes = nodes_df["tx_class"].astype(str).values
        time_steps = nodes_df["time_step"].astype(int).values

        self._id_to_idx = dict(zip(node_ids, idxs))
        self._idx_to_id = dict(zip(idxs, node_ids))

        for i in range(len(idxs)):
            idx = int(idxs[i])
            self._node_props[idx] = {
                "node_id": int(node_ids[i]),
                "tx_id": tx_ids[i],
                "tx_class": tx_classes[i],
                "time_step": int(time_steps[i]),
            }
            self.graph.set_node_name(idx, tx_ids[i])

        if "embedding" in nodes_df.columns:
            emb_mask = nodes_df["embedding"].notna()
            for i in nodes_df[emb_mask].index:
                self._embedding_index[int(idxs[i])] = np.array(
                    nodes_df.at[i, "embedding"]
                )

        # Vectorized edge loading
        edges_path = self.db_path / "edges.parquet"
        if edges_path.exists():
            edges_df = pd.read_parquet(edges_path)
            src = edges_df["src_idx"].astype(int).values
            dst = edges_df["dst_idx"].astype(int).values
            edges = [(int(src[i]), int(dst[i]), 1.0) for i in range(len(src))]
            self.graph = Graph.from_edges(edges)
            # Re-set node names after rebuilding graph
            for idx in self._idx_to_id:
                tx_id = self._node_props.get(idx, {}).get("tx_id", "")
                if tx_id:
                    self.graph.set_node_name(idx, tx_id)

        log.info(
            "Loaded: {} nodes, {} edges",
            self.graph.num_nodes,
            self.graph.num_edges,
        )

    # ── Node queries ─────────────────────────────────────────────────

    @property
    def num_nodes(self):
        return self.graph.num_nodes

    def get_node(self, node_id: int) -> Optional[dict[str, Any]]:
        idx = self._id_to_idx.get(node_id)
        if idx is None:
            return None
        return self._node_props.get(idx)

    def get_node_by_tx_id(self, tx_id: str) -> Optional[dict[str, Any]]:
        for props in self._node_props.values():
            if props.get("tx_id") == tx_id:
                return props
        return None

    def query_node_batch(self, offset: int, limit: int) -> pd.DataFrame:
        if offset >= self.num_nodes:
            return pd.DataFrame(columns=["node_id"])
        all_ids = sorted(self._idx_to_id.values())
        return pd.DataFrame({"node_id": all_ids[offset : offset + limit]})

    def query_neighbors(self, nodes: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for node_id in nodes.node_id:
            idx = self._id_to_idx.get(int(node_id))
            if idx is None:
                continue
            for neighbor_idx in self.graph.outgoing_neighbors(idx):
                neighbor_id = self._idx_to_id.get(neighbor_idx)
                if neighbor_id is not None:
                    rows.append({"source_id": int(node_id), "target_id": neighbor_id})

        if not rows:
            return pd.DataFrame(columns=["source_id", "target_id"])

        return (
            pd.DataFrame(rows)
            .sort_values(["source_id", "target_id"])
            .reset_index(drop=True)
        )

    # ── Graph algorithms ─────────────────────────────────────────────

    def bfs(self, node_id: int) -> list[int]:
        idx = self._id_to_idx.get(node_id)
        if idx is None:
            return []
        return [self._idx_to_id.get(i, i) for i in self.graph.bfs(idx)]

    def pagerank(
        self, max_iterations: int = 20, tolerance: float = 1e-6
    ) -> dict[int, float]:
        scores = self.graph.pagerank(max_iterations, tolerance)
        return {self._idx_to_id.get(i, i): s for i, s in enumerate(scores)}

    def louvain(self) -> dict:
        result = self.graph.louvain()
        result["communities"] = [
            [self._idx_to_id.get(n, n) for n in comm]
            for comm in result["communities"]
        ]
        return result

    def dijkstra(self, node_id: int) -> dict[int, float]:
        idx = self._id_to_idx.get(node_id)
        if idx is None:
            return {}
        raw = self.graph.dijkstra(idx)
        return {self._idx_to_id.get(int(k), int(k)): v for k, v in raw.items()}

    def shortest_path(
        self, source_id: int, target_id: int
    ) -> Optional[tuple[float, list[int]]]:
        src_idx = self._id_to_idx.get(source_id)
        tgt_idx = self._id_to_idx.get(target_id)
        if src_idx is None or tgt_idx is None:
            return None
        result = self.graph.shortest_path(src_idx, tgt_idx)
        if result is None:
            return None
        dist, path = result
        return dist, [self._idx_to_id.get(i, i) for i in path]

    def connected_components(self) -> int:
        return self.graph.connected_components()

    def strongly_connected_components(self) -> list[list[int]]:
        return [
            [self._idx_to_id.get(n, n) for n in comp]
            for comp in self.graph.strongly_connected_components()
        ]

    def is_cyclic(self) -> bool:
        return self.graph.is_cyclic()

    # ── Risk analysis (blockchain-specific) ──────────────────────────

    def illicit_neighbors(self, node_id: int) -> list[dict[str, Any]]:
        """Get neighbors of a node that are classified as illicit."""
        idx = self._id_to_idx.get(node_id)
        if idx is None:
            return []
        results = []
        for neighbor_idx in self.graph.outgoing_neighbors(idx):
            props = self._node_props.get(neighbor_idx, {})
            if props.get("tx_class") == "illicit":
                results.append(props)
        # Also check incoming
        for neighbor_idx in self.graph.incoming_neighbors(idx):
            props = self._node_props.get(neighbor_idx, {})
            if props.get("tx_class") == "illicit":
                results.append(props)
        return results

    def risk_score(self, node_id: int) -> float:
        """Compute risk score: ratio of illicit neighbors to total neighbors."""
        idx = self._id_to_idx.get(node_id)
        if idx is None:
            return 0.0
        out_neighbors = set(self.graph.outgoing_neighbors(idx))
        in_neighbors = set(self.graph.incoming_neighbors(idx))
        all_neighbors = out_neighbors | in_neighbors
        if not all_neighbors:
            return 0.0
        illicit_count = sum(
            1
            for n in all_neighbors
            if self._node_props.get(n, {}).get("tx_class") == "illicit"
        )
        return illicit_count / len(all_neighbors)

    def illicit_subgraph(self) -> list[int]:
        """Get all node_ids in the illicit network (illicit + 1-hop neighbors)."""
        illicit_indices = {
            idx
            for idx, props in self._node_props.items()
            if props.get("tx_class") == "illicit"
        }
        network = set(illicit_indices)
        for idx in illicit_indices:
            network.update(self.graph.outgoing_neighbors(idx))
            network.update(self.graph.incoming_neighbors(idx))
        return [self._idx_to_id.get(i, i) for i in sorted(network)]

    def high_risk_transactions(self, threshold: float = 0.0) -> pd.DataFrame:
        """Find non-illicit transactions with high risk scores."""
        rows = []
        for idx, props in self._node_props.items():
            if props.get("tx_class") == "illicit":
                continue
            node_id = props["node_id"]
            score = self.risk_score(node_id)
            if score > threshold:
                rows.append({
                    "node_id": node_id,
                    "tx_id": props.get("tx_id"),
                    "tx_class": props.get("tx_class"),
                    "time_step": props.get("time_step"),
                    "risk_score": round(score, 4),
                })
        if not rows:
            return pd.DataFrame(
                columns=["node_id", "tx_id", "tx_class", "time_step", "risk_score"]
            )
        return (
            pd.DataFrame(rows)
            .sort_values("risk_score", ascending=False)
            .reset_index(drop=True)
        )

    # ── Embeddings ───────────────────────────────────────────────────

    def update_embeddings(
        self,
        embeddings: dict[int, list[float]],
        dim: int,
        column_name: str = "embedding",
    ):
        for node_id, emb in embeddings.items():
            idx = self._id_to_idx.get(node_id)
            if idx is not None:
                self._embedding_index[idx] = np.array(emb)
        self._save_to_disk()

    def reindex_embeddings(self, column_name: str = "embedding"):
        log.info("Embedding index has {} entries", len(self._embedding_index))

    def knn(
        self,
        node_id: int,
        column_name: str = "embedding",
        max_k: int = 10,
        max_distance: float = 1.0,
        exclude: Optional[list[int]] = None,
    ) -> pd.DataFrame:
        idx = self._id_to_idx.get(node_id)
        if idx is None or idx not in self._embedding_index:
            return pd.DataFrame(columns=["node_id", "distance"])

        query_emb = self._embedding_index[idx]
        exclude_set = set(exclude or [])
        exclude_set.add(node_id)

        distances = []
        for other_idx, other_emb in self._embedding_index.items():
            other_id = self._idx_to_id[other_idx]
            if other_id in exclude_set:
                continue
            cos_sim = np.dot(query_emb, other_emb) / (
                np.linalg.norm(query_emb) * np.linalg.norm(other_emb) + 1e-10
            )
            dist = 1.0 - cos_sim
            if dist <= max_distance:
                distances.append({"node_id": other_id, "distance": dist})

        distances.sort(key=lambda x: x["distance"])
        return pd.DataFrame(distances[:max_k])

    # ── Path operations ──────────────────────────────────────────────

    def sample_shortest_paths(
        self,
        source_node_ids: list[int],
        target_node_ids: list[int],
        n: int,
        min_length: int,
        max_length: int,
    ) -> pd.DataFrame:
        log.info(
            "Computing shortest paths: {} sources x {} targets",
            len(source_node_ids),
            len(target_node_ids),
        )

        paths = []
        for src_id in source_node_ids:
            src_idx = self._id_to_idx.get(src_id)
            if src_idx is None:
                continue
            for tgt_id in target_node_ids:
                tgt_idx = self._id_to_idx.get(tgt_id)
                if tgt_idx is None:
                    continue
                result = self.graph.shortest_path(src_idx, tgt_idx)
                if result is None:
                    continue
                _, idx_path = result
                hops = len(idx_path) - 1
                if hops < min_length or hops > max_length:
                    continue
                path = [self._idx_to_id.get(i, i) for i in idx_path]
                # Interleave with "Pays" labels
                interleaved = []
                for j, nid in enumerate(path):
                    interleaved.append(nid)
                    if j < len(path) - 1:
                        interleaved.append("Pays")
                paths.append(interleaved)

        if not paths:
            return pd.DataFrame(columns=["paths"])
        if len(paths) > n:
            paths = random.sample(paths, n)
        return pd.DataFrame({"paths": paths})

    def random_walk(
        self,
        source_node_id: int,
        n: int,
        min_length: int,
        max_length: int,
    ) -> pd.DataFrame:
        src_idx = self._id_to_idx.get(source_node_id)
        if src_idx is None:
            return pd.DataFrame(columns=["source_node_id", "paths"])

        paths = []
        for _ in range(n):
            path = [source_node_id]
            current_idx = src_idx
            rand_len = np.random.randint(min_length, max_length + 1)
            prev_idx = None

            for _ in range(rand_len):
                neighbors = self.graph.outgoing_neighbors(current_idx)
                if prev_idx is not None:
                    neighbors = [n for n in neighbors if n != prev_idx]
                if not neighbors:
                    break
                next_idx = random.choice(neighbors)
                path.append("Pays")
                path.append(self._idx_to_id.get(next_idx, next_idx))
                prev_idx = current_idx
                current_idx = next_idx

            paths.append(path)

        return pd.DataFrame({"source_node_id": source_node_id, "paths": paths})

    # ── Description / hydration (for RAG context) ────────────────────

    def node_description(self, node_id: int) -> str:
        idx = self._id_to_idx.get(node_id)
        if idx is None:
            return f"Transaction(node_id={node_id})"
        props = self._node_props[idx]
        return (
            f"Transaction(tx_id={props['tx_id']}, "
            f"class={props['tx_class']}, "
            f"time_step={props['time_step']})"
        )

    def path_descriptions(
        self,
        paths_df: pd.DataFrame,
        exclude_props: Optional[list[str]] = None,
    ) -> str:
        log.info("Generating descriptions for {} paths", len(paths_df))

        node_descriptions = set()
        rel_descriptions = set()

        for path in paths_df["paths"]:
            for i in range(0, len(path), 2):
                nid = path[i]
                node_descriptions.add(self.node_description(nid))
                if i + 2 < len(path):
                    next_nid = path[i + 2]
                    rel_descriptions.add(
                        f"(tx_id={self._node_props.get(self._id_to_idx.get(nid, -1), {}).get('tx_id', nid)})"
                        f"-[:Pays]->"
                        f"(tx_id={self._node_props.get(self._id_to_idx.get(next_nid, -1), {}).get('tx_id', next_nid)})"
                    )

        if not node_descriptions:
            return ""

        return (
            f"Nodes:\n{chr(10).join(sorted(node_descriptions))}\n\n"
            f"Relationships:\n{chr(10).join(sorted(rel_descriptions))}"
        )

    def get_schema(self) -> str:
        return (
            "Node tables:\n"
            "  Transaction(node_id, tx_id, tx_class, time_step)\n"
            "Relationship tables:\n"
            "  Pays(FROM Transaction TO Transaction)"
        )

    # ── Visualization ────────────────────────────────────────────────

    def to_networkx(self, node_ids: list[int]) -> "nx.DiGraph":
        """Convert a subset of the graph to a networkx DiGraph for visualization.

        Args:
            node_ids: List of node_ids to include. Edges between these nodes
                are included automatically.
        """
        import networkx as nx

        G = nx.DiGraph()
        idx_set = set()

        for node_id in node_ids:
            idx = self._id_to_idx.get(node_id)
            if idx is None:
                continue
            idx_set.add(idx)
            props = self._node_props.get(idx, {})
            G.add_node(
                node_id,
                _label="Transaction",
                node_id=node_id,
                tx_id=props.get("tx_id", ""),
                tx_class=props.get("tx_class", ""),
                time_step=props.get("time_step", 0),
                label=props.get("tx_id", str(node_id)),
            )

        for idx in idx_set:
            src_id = self._idx_to_id[idx]
            for neighbor_idx in self.graph.outgoing_neighbors(idx):
                if neighbor_idx in idx_set:
                    dst_id = self._idx_to_id[neighbor_idx]
                    G.add_edge(src_id, dst_id, _label="Pays", vis_weight=1.0)
            for neighbor_idx in self.graph.incoming_neighbors(idx):
                if neighbor_idx in idx_set:
                    in_id = self._idx_to_id[neighbor_idx]
                    G.add_edge(in_id, src_id, _label="Pays", vis_weight=1.0)

        return G
