import { useEffect, useState } from 'react';

import type { ItemDetail } from '@/lib/types';

export function useItem(noteId: string | null) {
  const [item, setItem] = useState<ItemDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setItem(null);
    setError(null);
    if (!noteId) return;
    fetch(`/api/items/${encodeURIComponent(noteId)}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Request failed: ${res.status}`);
        return res.json();
      })
      .then(setItem)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [noteId]);

  return { item, error, loading: !item && !error };
}
