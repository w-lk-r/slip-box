import type { EdgeType, ItemType } from '@/lib/types';

export default function Legend({
  nodeColors,
  edgeColors,
}: {
  nodeColors: Record<ItemType, string>;
  edgeColors: Record<EdgeType, string>;
}) {
  return (
    <div className="pointer-events-none fixed bottom-4 left-4 z-10 rounded-lg bg-white/90 p-3 text-xs shadow dark:bg-neutral-900/90">
      <div className="mb-1 font-semibold">Notes</div>
      {Object.entries(nodeColors).map(([type, color]) => (
        <div key={type} className="flex items-center gap-2">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: color }} />
          {type}
        </div>
      ))}
      <div className="mt-2 mb-1 font-semibold">Edges</div>
      {Object.entries(edgeColors).map(([type, color]) => (
        <div key={type} className="flex items-center gap-2">
          <span className="inline-block h-0.5 w-4" style={{ background: color }} />
          {type}
        </div>
      ))}
      <div className="mt-1 text-neutral-500">dashed = lower confidence</div>
    </div>
  );
}
