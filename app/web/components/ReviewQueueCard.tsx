'use client';

import { useState } from 'react';

import EdgePanel from '@/components/EdgePanel';
import { EDGE_COLORS } from '@/lib/colors';
import type { GraphEdge, QueueIncomingEdge, QueueOutgoingEdge, ReviewQueueItem } from '@/lib/types';

// Same "worth a second look" cutoff GraphView.tsx already renders with a
// dashed line — kept in sync by eye, not imported, since GraphView's copy is
// a rendering constant local to that file. See docs/frontend-ux-spec.md.
const REVIEW_CONFIDENCE_CUTOFF = 0.85;

function EdgeChip({
  label,
  type,
  confidence,
  onClick,
}: {
  label: string;
  type: GraphEdge['type'];
  confidence: number;
  onClick: () => void;
}) {
  const lowConfidence = confidence < REVIEW_CONFIDENCE_CUTOFF;
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs hover:bg-neutral-100 dark:hover:bg-neutral-800 ${
        lowConfidence ? 'border-amber-400 dark:border-amber-600' : 'border-neutral-200 dark:border-neutral-700'
      }`}
      title={`${type} · confidence ${confidence.toFixed(2)}`}
    >
      <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: EDGE_COLORS[type] }} />
      <span className="truncate max-w-[10rem]">{label}</span>
      {lowConfidence && <span className="text-amber-600 dark:text-amber-400">{confidence.toFixed(2)}</span>}
    </button>
  );
}

export default function ReviewQueueCard({
  item,
  onReviewed,
}: {
  item: ReviewQueueItem;
  onReviewed: (noteId: string) => void;
}) {
  const [selectedEdge, setSelectedEdge] = useState<{ edge: GraphEdge; from: string; to: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const totalEdges = item.outgoing_edges.length + item.incoming_edges.length;
  const isOrphan = totalEdges === 0;
  const isRising = totalEdges >= 3;
  const hasLowConfidence = [...item.outgoing_edges, ...item.incoming_edges].some(
    (e) => e.confidence < REVIEW_CONFIDENCE_CUTOFF
  );

  async function handleMarkReviewed() {
    setBusy(true);
    try {
      const res = await fetch(`/api/items/${encodeURIComponent(item.note_id)}/review`, { method: 'POST' });
      if (!res.ok) throw new Error(`Request failed: ${res.status}`);
      onReviewed(item.note_id);
    } catch {
      setBusy(false);
    }
  }

  function openOutgoing(e: QueueOutgoingEdge) {
    setSelectedEdge({
      edge: { source: item.note_id, target: e.to_id, edge_id: e.edge_id, type: e.type, confidence: e.confidence },
      from: item.note_id,
      to: e.to_id,
    });
  }

  function openIncoming(e: QueueIncomingEdge) {
    setSelectedEdge({
      edge: { source: e.from_id, target: item.note_id, edge_id: e.edge_id, type: e.type, confidence: e.confidence },
      from: e.from_id,
      to: item.note_id,
    });
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-neutral-200 p-4 dark:border-neutral-800">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold">{item.title}</h3>
          <div className="mt-1 flex flex-wrap gap-2 text-xs text-neutral-500">
            <span>{item.type}</span>
            {item.date && <span>{item.date}</span>}
            {isOrphan && <span className="text-neutral-400">no connections yet</span>}
            {isRising && <span className="text-blue-500">{totalEdges} connections — consider a summary card</span>}
            {hasLowConfidence && <span className="text-amber-600 dark:text-amber-400">low-confidence edge to confirm</span>}
          </div>
          {!!item.tags?.length && <p className="mt-1 text-xs text-neutral-500">{item.tags.join(' · ')}</p>}
        </div>
        <button
          onClick={handleMarkReviewed}
          disabled={busy}
          className="shrink-0 rounded-md bg-neutral-900 px-3 py-1.5 text-xs text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
        >
          {busy ? 'Marking…' : 'Mark reviewed'}
        </button>
      </div>

      {totalEdges > 0 && (
        <div className="flex flex-wrap gap-2">
          {item.outgoing_edges.map((e) => (
            <EdgeChip key={e.edge_id} label={`→ ${e.to_title}`} type={e.type} confidence={e.confidence} onClick={() => openOutgoing(e)} />
          ))}
          {item.incoming_edges.map((e) => (
            <EdgeChip key={e.edge_id} label={`← ${e.from_title}`} type={e.type} confidence={e.confidence} onClick={() => openIncoming(e)} />
          ))}
        </div>
      )}

      {selectedEdge && (
        <EdgePanel
          edge={selectedEdge.edge}
          onClose={() => setSelectedEdge(null)}
          onChanged={() => setSelectedEdge(null)}
          onSelectNote={() => {}}
        />
      )}
    </div>
  );
}
