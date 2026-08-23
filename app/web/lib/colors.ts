import type { EdgeType, ItemType } from '@/lib/types';

// Shared between GraphView.tsx and ReviewQueueCard.tsx so a node/edge reads
// the same color wherever it shows up, not just inside the force graph.
export const NODE_COLORS: Record<ItemType, string> = {
  'literature-note': '#3b82f6',
  'summary-card': '#a855f7',
  'permanent-note': '#22c55e',
};

export const EDGE_COLORS: Record<EdgeType, string> = {
  SUPPORTS: '#22c55e',
  CONTRADICTS: '#ef4444',
  EXTENDS: '#3b82f6',
  RELATED_TO: '#9ca3af',
  GROUNDED_IN: '#a855f7',
};
