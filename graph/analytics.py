import pandas as pd
from loguru import logger as log

from graph.ops import GraphOps


class GraphAnalytics:
    def __init__(self, schema: str):
        self.ops = GraphOps(schema)

    def risk_summary(self) -> pd.DataFrame:
        """Compute risk scores for all non-illicit transactions."""
        return self.ops.high_risk_transactions(threshold=0.0)

    def illicit_network_stats(self) -> dict:
        """Summary statistics for the illicit subgraph."""
        illicit_ids = self.ops.illicit_subgraph()
        total = self.ops.num_nodes

        illicit_direct = sum(
            1
            for props in self.ops._node_props.values()
            if props.get("tx_class") == "illicit"
        )

        return {
            "total_transactions": total,
            "illicit_transactions": illicit_direct,
            "illicit_network_size": len(illicit_ids),
            "illicit_pct": round(illicit_direct / total * 100, 2) if total else 0,
            "network_pct": round(len(illicit_ids) / total * 100, 2) if total else 0,
        }

    def community_analysis(self) -> dict:
        """Run Louvain community detection and tag communities by illicit concentration."""
        result = self.ops.louvain()
        communities = result["communities"]

        community_stats = []
        for i, comm in enumerate(communities):
            comm_set = set(comm)
            illicit_count = sum(
                1
                for nid in comm
                if self.ops._node_props.get(
                    self.ops._id_to_idx.get(nid), {}
                ).get("tx_class")
                == "illicit"
            )
            community_stats.append({
                "community_id": i,
                "size": len(comm),
                "illicit_count": illicit_count,
                "illicit_pct": round(illicit_count / len(comm) * 100, 2) if comm else 0,
            })

        return {
            "modularity": result["modularity"],
            "num_communities": result["num_communities"],
            "communities": sorted(
                community_stats, key=lambda c: c["illicit_pct"], reverse=True
            ),
        }

    def pagerank_analysis(self, top_n: int = 20) -> pd.DataFrame:
        """Find the most important transactions by PageRank."""
        scores = self.ops.pagerank()
        rows = []
        for node_id, score in scores.items():
            idx = self.ops._id_to_idx.get(node_id)
            props = self.ops._node_props.get(idx, {})
            rows.append({
                "node_id": node_id,
                "tx_id": props.get("tx_id"),
                "tx_class": props.get("tx_class"),
                "time_step": props.get("time_step"),
                "pagerank": round(score, 6),
            })

        df = pd.DataFrame(rows).sort_values("pagerank", ascending=False)
        return df.head(top_n).reset_index(drop=True)
