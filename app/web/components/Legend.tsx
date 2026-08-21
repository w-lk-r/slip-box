'use client';

import { useState } from 'react';
import type { EdgeType, ItemType } from '@/lib/types';

export default function Legend({
  nodeColors,
  edgeColors,
}: {
  nodeColors: Record<ItemType, string>;
  edgeColors: Record<EdgeType, string>;
}) {
  const [pinned, setPinned] = useState(false);

  return (
    // Self-hover expand (`group` + `group-hover`) for a quick peek, click to
    // pin open (via `pinned` state) for reading without holding the mouse still.
    <div
      className="group fixed bottom-4 left-4 z-10 cursor-pointer"
      onClick={() => setPinned((p) => !p)}
    >
      <div
        className={`flex h-8 w-8 items-center justify-center rounded-full bg-black/70 shadow backdrop-blur-sm transition-opacity duration-150 ${
          pinned ? 'opacity-0' : 'opacity-100 group-hover:opacity-0'
        }`}
      >
        <span className="h-2 w-2 rounded-full bg-white/70" />
      </div>
      <div
        className={`absolute bottom-0 left-0 w-56 cursor-auto overflow-hidden rounded-lg bg-black/70 text-xs text-neutral-200 shadow backdrop-blur-sm transition-all duration-150 ${
          pinned
            ? 'pointer-events-auto max-h-96 p-3 opacity-100'
            : 'pointer-events-none max-h-0 p-0 opacity-0 group-hover:pointer-events-auto group-hover:max-h-96 group-hover:p-3 group-hover:opacity-100'
        }`}
      >
        <div className="mb-1 font-semibold text-white">Notes</div>
        {Object.entries(nodeColors).map(([type, color]) => (
          <div key={type} className="flex items-center gap-2">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ background: color, boxShadow: `0 0 4px ${color}` }}
            />
            {type}
          </div>
        ))}
        <div className="mt-2 mb-1 font-semibold text-white">Edges</div>
        {Object.entries(edgeColors).map(([type, color]) => (
          <div key={type} className="flex items-center gap-2">
            <span className="inline-block h-0.5 w-4" style={{ background: color }} />
            {type}
          </div>
        ))}
        <div className="mt-1 text-neutral-400">dashed = lower confidence</div>
      </div>
    </div>
  );
}
