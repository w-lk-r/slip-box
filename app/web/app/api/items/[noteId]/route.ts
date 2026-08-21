import { NextResponse } from 'next/server';

import { backendFetch } from '@/lib/backend';

export async function GET(_request: Request, { params }: { params: Promise<{ noteId: string }> }) {
  const { noteId } = await params;
  const response = await backendFetch(`/items/${encodeURIComponent(noteId)}`);
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
