'use client';

import { useCallback, useEffect, useState } from 'react';
import ForceGraph2D, { type GraphData, type LinkObject, type NodeObject } from 'react-force-graph-2d';

import EdgePanel from '@/components/EdgePanel';
import NodePanel from '@/components/NodePanel';
import Legend from '@/components/Legend';
import type { GraphEdge, GraphNode, GraphResponse } from '@/lib/types';

const NODE_COLORS: Record<GraphNode['type'], string> = {
  'literature-note': '#3b82f6',
  'summary-card': '#a855f7',
  'permanent-note': '#22c55e',
};

const EDGE_COLORS: Record<GraphEdge['type'], string> = {
  SUPPORTS: '#22c55e',
  CONTRADICTS: '#ef4444',
  EXTENDS: '#3b82f6',
  RELATED_TO: '#9ca3af',
  GROUNDED_IN: '#a855f7',
};

// Not the backend's EDGE_CONFIDENCE_THRESHOLD (which gates whether an edge
// gets written at all — everything reaching the graph already cleared that
// bar). This is a separate, purely visual cutoff for "worth a second look".
const REVIEW_CONFIDENCE_CUTOFF = 0.85;

// GraphEdge's own `source`/`target: string` (the real API shape) would
// collapse react-force-graph's `source?: string | number | NodeObject`
// union down to just `string` via intersection when used directly as the
// library's LinkType generic — but force-graph mutates link.source/target
// into resolved NodeObject references at runtime once the simulation
// initializes. Use the edge-only fields for the generic so the library's
// own (accurate) union type for source/target isn't overridden.
type LinkExtra = Omit<GraphEdge, 'source' | 'target'>;

type GraphViewData = GraphData<GraphNode, LinkExtra>;

// link.source/target may still be a bare string ID on first render, or an
// already-resolved NodeObject once the simulation has run — same ambiguity
// handled in onLinkClick below.
function endpointLabel(end: string | number | NodeObject<GraphNode>): string {
  return typeof end === 'object' ? (end.label ?? String(end.id)) : String(end);
}

export default function GraphView() {
  const [data, setData] = useState<GraphViewData>({ nodes: [], links: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/graph');
      if (!res.ok) throw new Error(`Request failed: ${res.status}`);
      const json: GraphResponse = await res.json();
      setData({ nodes: json.nodes, links: json.edges });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div style={{ position: 'relative', width: '100vw', height: '100vh', overflow: 'hidden' }}>
      {(loading || error) && (
        <div style={statusStyle}>{error ? `Failed to load: ${error}` : 'Loading graph…'}</div>
      )}

      <ForceGraph2D
        graphData={data}
        nodeId="id"
        nodeLabel={(n: NodeObject<GraphNode>) => n.label ?? ''}
        nodeColor={(n: NodeObject<GraphNode>) => NODE_COLORS[n.type] ?? '#888888'}
        linkColor={(l: LinkObject<GraphNode, LinkExtra>) => EDGE_COLORS[l.type] ?? '#888888'}
        linkLineDash={(l: LinkObject<GraphNode, LinkExtra>) =>
          l.confidence < REVIEW_CONFIDENCE_CUTOFF ? [4, 2] : null
        }
        linkLabel={(l: LinkObject<GraphNode, LinkExtra>) =>
          `${endpointLabel(l.source!)} → ${endpointLabel(l.target!)} (${l.type}, ${l.confidence.toFixed(2)})`
        }
        linkDirectionalArrowLength={4}
        linkDirectionalArrowRelPos={1}
        onNodeClick={(n: NodeObject<GraphNode>) => {
          setSelectedEdge(null);
          setSelectedNodeId(String(n.id));
        }}
        onLinkClick={(l: LinkObject<GraphNode, LinkExtra>) => {
          setSelectedNodeId(null);
          // force-graph mutates link.source/target in place, replacing the
          // original string IDs with resolved node object references once
          // the simulation runs — normalize back to plain IDs so EdgePanel
          // (and the /api/edges/{from_id}/{edge_id} path it builds) always
          // gets what it expects, regardless of simulation state.
          const source = typeof l.source === 'object' ? String(l.source.id) : String(l.source);
          const target = typeof l.target === 'object' ? String(l.target.id) : String(l.target);
          setSelectedEdge({ ...l, source, target } as GraphEdge);
        }}
      />

      <Legend nodeColors={NODE_COLORS} edgeColors={EDGE_COLORS} />

      {selectedNodeId && <NodePanel noteId={selectedNodeId} onClose={() => setSelectedNodeId(null)} />}
      {selectedEdge && (
        <EdgePanel
          edge={selectedEdge}
          onClose={() => setSelectedEdge(null)}
          onChanged={() => {
            setSelectedEdge(null);
            load();
          }}
          onSelectNote={(noteId) => {
            setSelectedEdge(null);
            setSelectedNodeId(noteId);
          }}
        />
      )}
    </div>
  );
}

const statusStyle: React.CSSProperties = {
  position: 'absolute',
  top: 12,
  left: 12,
  zIndex: 10,
  padding: '6px 12px',
  borderRadius: 6,
  background: 'rgba(0,0,0,0.7)',
  color: 'white',
  fontSize: 13,
};
