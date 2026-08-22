import { NextResponse } from 'next/server';

import { backendFetch } from '@/lib/backend';

export async function POST(request: Request) {
  const body = await request.text();
  const response = await backendFetch('/uploads/presign', { method: 'POST', body });
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
