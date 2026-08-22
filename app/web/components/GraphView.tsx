'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
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

// Matches Obsidian's graph view: near-black canvas, glowing dots, thin
// translucent web-like edges — not the flat-UI default look.
const CANVAS_BACKGROUND = '#050508';

function hexToRgba(hex: string, alpha: number): string {
  const n = parseInt(hex.replace('#', ''), 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// Base radius plus a sqrt scale on connection count, so hub notes read as
// visibly bigger without one mega-connected node dwarfing everything else.
function nodeRadius(degree: number): number {
  return 2.5 + Math.sqrt(degree) * 1.8;
}

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

function isIncidentToSelection(l: LinkObject<GraphNode, LinkExtra>, selectedNodeId: string | null): boolean {
  if (!selectedNodeId) return false;
  const source = typeof l.source === 'object' ? String((l.source as NodeObject).id) : String(l.source);
  const target = typeof l.target === 'object' ? String((l.target as NodeObject).id) : String(l.target);
  return source === selectedNodeId || target === selectedNodeId;
}

export default function GraphView() {
  const [data, setData] = useState<GraphViewData>({ nodes: [], links: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);
  // Summary-card note_ids the user has expanded — collapsed (not in this set)
  // is the default, matching CLAUDE.md's "collapsed = one node with edges
  // routing through it; expanded = individual notes visible" cluster design.
  const [expandedClusters, setExpandedClusters] = useState<Set<string>>(new Set());

  const nodeTypeById = useMemo(() => {
    const map = new Map<string, GraphNode['type']>();
    for (const n of data.nodes) map.set(String(n.id), n.type);
    return map;
  }, [data]);

  // hub summary-card id -> its member note_ids, from GROUNDED_IN edges whose
  // source is a summary-card (permanent-note GROUNDED_IN edges are plain
  // citations, not clustering, so they're excluded from collapse behavior).
  const clusterMembersByHub = useMemo(() => {
    const map = new Map<string, Set<string>>();
    for (const l of data.links) {
      if (l.type !== 'GROUNDED_IN') continue;
      const source = typeof l.source === 'object' ? String((l.source as NodeObject).id) : String(l.source);
      const target = typeof l.target === 'object' ? String((l.target as NodeObject).id) : String(l.target);
      if (nodeTypeById.get(source) !== 'summary-card') continue;
      if (!map.has(source)) map.set(source, new Set());
      map.get(source)!.add(target);
    }
    return map;
  }, [data, nodeTypeById]);

  // The actual rendered graph: members of a still-collapsed cluster are
  // hidden, and any edge touching one of them is redirected to its hub —
  // "nodes that would connect to the underlying notes connect to the
  // summary instead" while collapsed.
  const displayData = useMemo(() => {
    const memberToHub = new Map<string, string>();
    for (const [hub, members] of clusterMembersByHub) {
      if (expandedClusters.has(hub)) continue;
      for (const m of members) memberToHub.set(m, hub);
    }

    const nodes = data.nodes.filter((n) => !memberToHub.has(String(n.id)));

    const links: LinkExtra[] = [];
    for (const l of data.links) {
      const rawSource = typeof l.source === 'object' ? String((l.source as NodeObject).id) : String(l.source);
      const rawTarget = typeof l.target === 'object' ? String((l.target as NodeObject).id) : String(l.target);
      const effSource = memberToHub.get(rawSource) ?? rawSource;
      const effTarget = memberToHub.get(rawTarget) ?? rawTarget;
      // Both ends collapse to the same hub — internal to the cluster (this
      // includes the hub's own GROUNDED_IN edges to its members) — drop it.
      if (effSource === effTarget) continue;
      links.push({ ...l, source: effSource, target: effTarget } as unknown as LinkExtra);
    }

    return { nodes, links } as GraphViewData;
  }, [data, clusterMembersByHub, expandedClusters]);

  const degreeById = useMemo(() => {
    const map = new Map<string, number>();
    for (const n of displayData.nodes) map.set(String(n.id), 0);
    for (const l of displayData.links) {
      const source = typeof l.source === 'object' ? String((l.source as NodeObject).id) : String(l.source);
      const target = typeof l.target === 'object' ? String((l.target as NodeObject).id) : String(l.target);
      map.set(source, (map.get(source) ?? 0) + 1);
      map.set(target, (map.get(target) ?? 0) + 1);
    }
    return map;
  }, [displayData]);

  const neighborIds = useMemo(() => {
    const set = new Set<string>();
    if (!selectedNodeId) return set;
    for (const l of displayData.links) {
      const source = typeof l.source === 'object' ? String((l.source as NodeObject).id) : String(l.source);
      const target = typeof l.target === 'object' ? String((l.target as NodeObject).id) : String(l.target);
      if (source === selectedNodeId) set.add(target);
      if (target === selectedNodeId) set.add(source);
    }
    return set;
  }, [displayData, selectedNodeId]);

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
    <div style={{ position: 'relative', width: '100vw', height: '100vh', overflow: 'hidden', background: CANVAS_BACKGROUND }}>
      {(loading || error) && (
        <div style={statusStyle}>{error ? `Failed to load: ${error}` : 'Loading graph…'}</div>
      )}

      <ForceGraph2D
        graphData={displayData}
        nodeId="id"
        backgroundColor={CANVAS_BACKGROUND}
        nodeLabel={(n: NodeObject<GraphNode>) => n.label ?? ''}
        nodeCanvasObject={(n: NodeObject<GraphNode>, ctx: CanvasRenderingContext2D) => {
          const color = NODE_COLORS[n.type] ?? '#888888';
          const r = nodeRadius(degreeById.get(String(n.id)) ?? 0);
          const idStr = String(n.id);
          const selected = idStr === selectedNodeId;
          const neighbor = !selected && neighborIds.has(idStr);
          ctx.save();
          ctx.shadowColor = color;
          ctx.shadowBlur = selected ? 18 : neighbor ? 14 : 10;
          ctx.beginPath();
          ctx.arc(n.x!, n.y!, r, 0, 2 * Math.PI);
          ctx.fillStyle = color;
          ctx.fill();
          if (selected || neighbor) {
            // Ring sits outside the glow so it reads clearly against both
            // the node's own color and the dark canvas. Dimmer/thinner for
            // neighbors so the selected node still reads as the focus.
            ctx.shadowBlur = 0;
            ctx.beginPath();
            ctx.arc(n.x!, n.y!, r + 3, 0, 2 * Math.PI);
            ctx.strokeStyle = selected ? '#ffffff' : 'rgba(255, 255, 255, 0.55)';
            ctx.lineWidth = selected ? 1.5 : 1;
            ctx.stroke();
          }
          ctx.restore();
        }}
        nodePointerAreaPaint={(n: NodeObject<GraphNode>, color: string, ctx: CanvasRenderingContext2D) => {
          const r = nodeRadius(degreeById.get(String(n.id)) ?? 0);
          ctx.beginPath();
          ctx.arc(n.x!, n.y!, r, 0, 2 * Math.PI);
          ctx.fillStyle = color;
          ctx.fill();
        }}
        linkColor={(l: LinkObject<GraphNode, LinkExtra>) => {
          const base = EDGE_COLORS[l.type] ?? '#888888';
          return hexToRgba(base, isIncidentToSelection(l, selectedNodeId) ? 0.9 : 0.35);
        }}
        linkWidth={(l: LinkObject<GraphNode, LinkExtra>) => (isIncidentToSelection(l, selectedNodeId) ? 1.8 : 0.6)}
        linkLineDash={(l: LinkObject<GraphNode, LinkExtra>) =>
          l.confidence < REVIEW_CONFIDENCE_CUTOFF ? [4, 2] : null
        }
        linkLabel={(l: LinkObject<GraphNode, LinkExtra>) =>
          `${endpointLabel(l.source!)} → ${endpointLabel(l.target!)} (${l.type}, ${l.confidence.toFixed(2)})`
        }
        onNodeClick={(n: NodeObject<GraphNode>) => {
          const id = String(n.id);
          // Summary cards both toggle their collapsed/expanded cluster state
          // AND open their own note panel — previously click was consumed
          // entirely by the toggle, so the card's own synthesis text was
          // never reachable from the graph at all.
          if (n.type === 'summary-card') {
            setExpandedClusters((prev) => {
              const next = new Set(prev);
              if (next.has(id)) next.delete(id);
              else next.add(id);
              return next;
            });
          }
          setSelectedEdge(null);
          setSelectedNodeId(id);
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
