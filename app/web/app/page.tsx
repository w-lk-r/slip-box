'use client';

import dynamic from 'next/dynamic';

// react-force-graph-2d touches window/DOM at module load — canvas-based
// libraries like this and Cytoscape.js are hard client-only. `ssr: false`
// is only permitted with next/dynamic inside a Client Component in this
// Next.js version (it errors at build time inside a Server Component), so
// this file itself is "use client" rather than pushing the dynamic import
// down into GraphView.tsx.
const GraphView = dynamic(() => import('@/components/GraphView'), { ssr: false });

export default function Home() {
  return <GraphView />;
}
