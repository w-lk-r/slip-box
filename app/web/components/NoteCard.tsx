'use client';

import type { ItemDetail } from '@/lib/types';

export default function NoteCard({
  item,
  error,
  loading,
  onTitleClick,
  compact = false,
}: {
  item: ItemDetail | null;
  error?: string | null;
  loading?: boolean;
  onTitleClick?: () => void;
  compact?: boolean;
}) {
  if (error) return <p className="text-sm text-red-500">{error}</p>;
  if (loading || !item) return <p className="text-sm text-neutral-500">Loading…</p>;

  return (
    <div>
      {onTitleClick ? (
        <button
          onClick={onTitleClick}
          className="text-left text-lg font-semibold underline decoration-dotted underline-offset-4 hover:decoration-solid"
          title="View this note on its own"
        >
          {item.title}
        </button>
      ) : (
        <h2 className="text-lg font-semibold">{item.title}</h2>
      )}

      <div className="mt-1 flex gap-3 text-xs text-neutral-500">
        <span>{item.type}</span>
        {item.date && <span>{item.date}</span>}
      </div>

      {!!item.tags?.length && <p className="mt-2 text-xs text-neutral-500">{item.tags.join(' · ')}</p>}

      <p className={`mt-3 whitespace-pre-wrap text-sm leading-relaxed ${compact ? 'line-clamp-6' : ''}`}>
        {item.body}
      </p>

      {item.source && !compact && (
        <p className="mt-3 truncate text-xs text-neutral-500">
          Source:{' '}
          {item.source.url ? (
            <a href={item.source.url} target="_blank" rel="noreferrer" className="underline">
              {item.source.title}
            </a>
          ) : (
            item.source.title
          )}
          {item.source.author && ` — ${item.source.author}`}
        </p>
      )}
    </div>
  );
}
