import { NextResponse } from 'next/server';

import { backendFetch } from '@/lib/backend';

export async function GET() {
  const response = await backendFetch('/items/review-queue');
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
