import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ForceGraph3D from "react-force-graph-3d";
import * as THREE from "three";
import type { GraphData, GraphNode } from "./types";
import "./App.css";

const CLASS_COLORS: Record<string, string> = {
  illicit: "#ff2d55",
  licit: "#30d158",
  unknown: "#636366",
};

const CLASS_GLOW: Record<string, string> = {
  illicit: "#ff2d55",
  licit: "#30d158",
  unknown: "#48484a",
};

function App() {
  const fgRef = useRef<any>(null);
  const [data, setData] = useState<GraphData | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [filters, setFilters] = useState({
    illicit: true,
    licit: true,
    unknown: true,
  });
  const [minTimeStep, setMinTimeStep] = useState(1);
  const [maxTimeStep, setMaxTimeStep] = useState(49);

  useEffect(() => {
    fetch("/graph.json")
      .then((r) => r.json())
      .then((d: GraphData) => setData(d));
  }, []);

  const filteredData = useMemo(() => {
    if (!data) return null;

    const visibleNodes = data.nodes.filter(
      (n) =>
        filters[n.txClass] &&
        n.timeStep >= minTimeStep &&
        n.timeStep <= maxTimeStep
    );
    const visibleIds = new Set(visibleNodes.map((n) => n.id));
    const visibleLinks = data.links.filter((l) => {
      const srcId = typeof l.source === "object" ? l.source.id : l.source;
      const tgtId = typeof l.target === "object" ? l.target.id : l.target;
      return visibleIds.has(srcId) && visibleIds.has(tgtId);
    });

    return { nodes: visibleNodes, links: visibleLinks };
  }, [data, filters, minTimeStep, maxTimeStep]);

  const nodeThreeObject = useCallback((node: GraphNode) => {
    const color = CLASS_COLORS[node.txClass] || CLASS_COLORS.unknown;
    const isIllicit = node.txClass === "illicit";
    const size = isIllicit ? 4 : node.riskScore > 0.5 ? 3 : 2;

    const group = new THREE.Group();

    // Core sphere
    const geometry = new THREE.SphereGeometry(size, 16, 16);
    const material = new THREE.MeshPhongMaterial({
      color,
      emissive: color,
      emissiveIntensity: isIllicit ? 0.8 : 0.3,
      transparent: true,
      opacity: 0.9,
    });
    const sphere = new THREE.Mesh(geometry, material);
    group.add(sphere);

    // Glow for illicit / high-risk
    if (isIllicit || node.riskScore > 0.5) {
      const glowGeometry = new THREE.SphereGeometry(size * 1.8, 16, 16);
      const glowMaterial = new THREE.MeshBasicMaterial({
        color: CLASS_GLOW[node.txClass] || CLASS_GLOW.unknown,
        transparent: true,
        opacity: isIllicit ? 0.15 : 0.08,
      });
      const glow = new THREE.Mesh(glowGeometry, glowMaterial);
      group.add(glow);
    }

    return group;
  }, []);

  const handleNodeClick = useCallback(
    (node: GraphNode) => {
      setSelectedNode(node);
      if (fgRef.current) {
        const distance = 120;
        const distRatio =
          1 + distance / Math.hypot(node.x || 0, node.y || 0, node.z || 0);
        fgRef.current.cameraPosition(
          {
            x: (node.x || 0) * distRatio,
            y: (node.y || 0) * distRatio,
            z: (node.z || 0) * distRatio,
          },
          node,
          1500
        );
      }
    },
    [fgRef]
  );

  if (!data || !filteredData) {
    return (
      <div className="loading">
        <div className="spinner" />
        <p>Loading Bitcoin Transaction Graph...</p>
      </div>
    );
  }

  return (
    <div className="app">
      <ForceGraph3D
        ref={fgRef}
        graphData={filteredData}
        nodeId="id"
        nodeThreeObject={nodeThreeObject}
        nodeLabel={(node: GraphNode) =>
          `<div class="tooltip">
            <strong>${node.txId}</strong><br/>
            Class: <span style="color:${CLASS_COLORS[node.txClass]}">${node.txClass}</span><br/>
            Time Step: ${node.timeStep}<br/>
            Risk Score: ${(node.riskScore * 100).toFixed(1)}%
          </div>`
        }
        linkColor={() => "rgba(100, 100, 140, 0.3)"}
        linkWidth={0.5}
        linkDirectionalArrowLength={3}
        linkDirectionalArrowRelPos={1}
        linkDirectionalArrowColor={() => "rgba(100, 100, 140, 0.6)"}
        backgroundColor="#0a0a1a"
        onNodeClick={handleNodeClick}
        enableNodeDrag={true}
        warmupTicks={100}
        cooldownTicks={200}
      />

      {/* Header */}
      <div className="header">
        <h1>Bitcoin Transaction Graph</h1>
        <p className="subtitle">Elliptic Dataset - Illicit Activity Network</p>
      </div>

      {/* Stats */}
      <div className="stats-panel">
        <h3>Network Stats</h3>
        <div className="stat">
          <span className="stat-label">Total Transactions</span>
          <span className="stat-value">
            {data.stats.totalNodes.toLocaleString()}
          </span>
        </div>
        <div className="stat">
          <span className="stat-label">Total Flows</span>
          <span className="stat-value">
            {data.stats.totalEdges.toLocaleString()}
          </span>
        </div>
        <div className="stat-divider" />
        <div className="stat">
          <span className="stat-label">Displayed Nodes</span>
          <span className="stat-value">
            {filteredData.nodes.length.toLocaleString()}
          </span>
        </div>
        <div className="stat">
          <span className="stat-label">Displayed Edges</span>
          <span className="stat-value">
            {filteredData.links.length.toLocaleString()}
          </span>
        </div>
      </div>

      {/* Filters */}
      <div className="filter-panel">
        <h3>Filters</h3>
        {(["illicit", "licit", "unknown"] as const).map((cls) => (
          <label key={cls} className="filter-item">
            <input
              type="checkbox"
              checked={filters[cls]}
              onChange={() =>
                setFilters((f) => ({ ...f, [cls]: !f[cls] }))
              }
            />
            <span
              className="filter-dot"
              style={{ background: CLASS_COLORS[cls] }}
            />
            <span className="filter-label">
              {cls} ({data.stats[`${cls}Count` as keyof typeof data.stats]})
            </span>
          </label>
        ))}
        <div className="stat-divider" />
        <label className="filter-range-label">
          Time Step: {minTimeStep} - {maxTimeStep}
        </label>
        <input
          type="range"
          min={1}
          max={49}
          value={minTimeStep}
          onChange={(e) => setMinTimeStep(Number(e.target.value))}
          className="range-input"
        />
        <input
          type="range"
          min={1}
          max={49}
          value={maxTimeStep}
          onChange={(e) => setMaxTimeStep(Number(e.target.value))}
          className="range-input"
        />
      </div>

      {/* Selected Node */}
      {selectedNode && (
        <div className="detail-panel">
          <div className="detail-header">
            <h3>Transaction Details</h3>
            <button className="close-btn" onClick={() => setSelectedNode(null)}>
              x
            </button>
          </div>
          <div className="detail-row">
            <span>TX ID</span>
            <span className="mono">{selectedNode.txId}</span>
          </div>
          <div className="detail-row">
            <span>Classification</span>
            <span
              style={{ color: CLASS_COLORS[selectedNode.txClass] }}
              className="badge"
            >
              {selectedNode.txClass.toUpperCase()}
            </span>
          </div>
          <div className="detail-row">
            <span>Time Step</span>
            <span>{selectedNode.timeStep}</span>
          </div>
          <div className="detail-row">
            <span>Risk Score</span>
            <span
              style={{
                color:
                  selectedNode.riskScore > 0.5
                    ? "#ff2d55"
                    : selectedNode.riskScore > 0.2
                      ? "#ff9f0a"
                      : "#30d158",
              }}
            >
              {(selectedNode.riskScore * 100).toFixed(1)}%
            </span>
          </div>
        </div>
      )}

      {/* Legend */}
      <div className="legend">
        <div className="legend-item">
          <span className="legend-dot" style={{ background: "#ff2d55" }} />
          Illicit
        </div>
        <div className="legend-item">
          <span className="legend-dot" style={{ background: "#30d158" }} />
          Licit
        </div>
        <div className="legend-item">
          <span className="legend-dot" style={{ background: "#636366" }} />
          Unknown
        </div>
      </div>
    </div>
  );
}

export default App;
