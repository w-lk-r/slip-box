import { NextResponse } from 'next/server';

import { backendFetch } from '@/lib/backend';

export async function GET(request: Request) {
  const { search } = new URL(request.url);
  const response = await backendFetch(`/items${search}`);
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
