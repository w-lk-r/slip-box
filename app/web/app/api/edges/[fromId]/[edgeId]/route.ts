import { NextResponse } from 'next/server';

import { backendFetch } from '@/lib/backend';

type Params = { params: Promise<{ fromId: string; edgeId: string }> };

function edgePath(fromId: string, edgeId: string) {
  return `/edges/${encodeURIComponent(fromId)}/${encodeURIComponent(edgeId)}`;
}

export async function PATCH(request: Request, { params }: Params) {
  const { fromId, edgeId } = await params;
  const body = await request.text();
  const response = await backendFetch(edgePath(fromId, edgeId), { method: 'PATCH', body });
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}

export async function DELETE(_request: Request, { params }: Params) {
  const { fromId, edgeId } = await params;
  const response = await backendFetch(edgePath(fromId, edgeId), { method: 'DELETE' });
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
