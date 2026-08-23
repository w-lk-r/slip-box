'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';

import ReviewQueueCard from '@/components/ReviewQueueCard';
import type { ReviewQueueItem } from '@/lib/types';

export default function ReviewPage() {
  const [items, setItems] = useState<ReviewQueueItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/items/review-queue')
      .then((res) => {
        if (!res.ok) throw new Error(`Request failed: ${res.status}`);
        return res.json();
      })
      .then((data) => setItems(data.items))
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  function handleReviewed(noteId: string) {
    setItems((prev) => prev?.filter((i) => i.note_id !== noteId) ?? prev);
  }

  return (
    <main className="max-w-2xl mx-auto p-6 flex flex-col gap-4 w-full">
      <Link href="/" className="text-sm text-neutral-500 hover:underline self-start">
        ← Graph
      </Link>
      <h1 className="text-xl font-semibold">Review</h1>
      <p className="text-sm text-neutral-500">
        Notes the agent wrote that nobody's looked at yet — every edge below already cleared the write threshold; this
        is about catching the ones worth a second look, not re-litigating everything.
      </p>

      {error && <p className="text-sm text-red-500">{error}</p>}
      {!items && !error && <p className="text-sm text-neutral-500">Loading…</p>}
      {items && items.length === 0 && <p className="text-sm text-neutral-500">Nothing to review — you&apos;re caught up.</p>}

      {items && items.length > 0 && (
        <div className="flex flex-col gap-3">
          {items.map((item) => (
            <ReviewQueueCard key={item.note_id} item={item} onReviewed={handleReviewed} />
          ))}
        </div>
      )}
    </main>
  );
}
