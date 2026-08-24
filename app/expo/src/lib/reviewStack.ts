// Hands a tapped-into review group's note_ids off to app/review-stack.tsx
// without serializing a whole list into a URL param — same "simple external
// module" idea as pendingIngestions.ts, but no polling/subscription needed
// here since the stack screen only ever reads this once, on mount.
import type { ReviewQueueItem } from '@/lib/api';

let activeStack: { title: string; items: ReviewQueueItem[] } | null = null;

export function setActiveReviewStack(title: string, items: ReviewQueueItem[]): void {
  activeStack = { title, items };
}

export function getActiveReviewStack(): { title: string; items: ReviewQueueItem[] } | null {
  return activeStack;
}
