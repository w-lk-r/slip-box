'use client';

import NoteCard from '@/components/NoteCard';
import { useItem } from '@/lib/useItem';

const CONNECTION_LABEL: Record<string, string> = {
  supports: 'Supports',
  contradicts: 'Contradicts',
  extends: 'Extends',
  related_to: 'Related to',
  grounded_in: 'Grounded in',
};

// Frontmatter link entries are stored as "[[note_id|Title]]" — pull out just the title.
function linkTitle(entry: string): string {
  const match = entry.match(/^\[\[[^|]*\|(.+)\]\]$/);
  return match ? match[1] : entry;
}

export default function NodePanel({ noteId, onClose }: { noteId: string; onClose: () => void }) {
  const { item, error, loading } = useItem(noteId);
  const connectionEntries = Object.entries(item?.connections ?? {}).filter(([, links]) => links.length > 0);

  return (
    <aside className="fixed top-0 right-0 h-full w-full max-w-sm overflow-y-auto bg-white p-5 shadow-xl dark:bg-neutral-900">
      <button onClick={onClose} className="mb-3 text-sm text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200">
        ✕ Close
      </button>

      <NoteCard item={item} error={error} loading={loading} />

      {connectionEntries.length > 0 && (
        <div className="mt-5 space-y-2 border-t border-neutral-200 pt-3 dark:border-neutral-700">
          <p className="text-xs font-semibold">Connections</p>
          {connectionEntries.map(([type, links]) => (
            <div key={type} className="text-xs">
              <span className="text-neutral-500">{CONNECTION_LABEL[type] ?? type}:</span>{' '}
              {links.map(linkTitle).join(', ')}
            </div>
          ))}
        </div>
      )}
    </aside>
  );
}
