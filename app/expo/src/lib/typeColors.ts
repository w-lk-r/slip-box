import type { EdgeType, ItemType } from '@/lib/api';

// Mirrors app/web/lib/colors.ts's hex values exactly — one shared palette
// between web and mobile rather than a second one invented independently.
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

export const TYPE_LABEL: Record<ItemType, string> = {
  'literature-note': 'note',
  'summary-card': 'summary',
  'permanent-note': 'idea',
};
