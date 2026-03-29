export interface GraphNode {
  id: number;
  txId: string;
  txClass: "illicit" | "licit" | "unknown";
  timeStep: number;
  riskScore: number;
  // Added by force-graph
  x?: number;
  y?: number;
  z?: number;
}

export interface GraphLink {
  source: number | GraphNode;
  target: number | GraphNode;
}

export interface GraphStats {
  totalNodes: number;
  totalEdges: number;
  displayedNodes: number;
  displayedEdges: number;
  illicitCount: number;
  licitCount: number;
  unknownCount: number;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
  stats: GraphStats;
}
