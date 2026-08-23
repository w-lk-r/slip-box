import { NextResponse } from 'next/server';

import { backendFetch } from '@/lib/backend';

type Params = { params: Promise<{ noteId: string }> };

function reviewPath(noteId: string) {
  return `/items/${encodeURIComponent(noteId)}/review`;
}

export async function POST(_request: Request, { params }: Params) {
  const { noteId } = await params;
  const response = await backendFetch(reviewPath(noteId), { method: 'POST' });
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}

export async function DELETE(_request: Request, { params }: Params) {
  const { noteId } = await params;
  const response = await backendFetch(reviewPath(noteId), { method: 'DELETE' });
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
