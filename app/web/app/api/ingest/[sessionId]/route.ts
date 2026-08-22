import { NextResponse } from 'next/server';

import { backendFetch } from '@/lib/backend';

export async function GET(_request: Request, ctx: RouteContext<'/api/ingest/[sessionId]'>) {
  const { sessionId } = await ctx.params;
  const response = await backendFetch(`/ingest/${encodeURIComponent(sessionId)}`);
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
