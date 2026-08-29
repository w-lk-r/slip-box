export type ItemType = 'literature-note' | 'summary-card' | 'permanent-note';

export type EdgeType = 'SUPPORTS' | 'CONTRADICTS' | 'EXTENDS' | 'RELATED_TO' | 'GROUNDED_IN';

// Mirrors app/api/routers/graph.py's response shape.
export type GraphNode = {
  id: string;
  label: string;
  type: ItemType;
  authored_by?: string;
  created_at?: string;
};

export type GraphEdge = {
  source: string;
  target: string;
  edge_id: string;
  type: EdgeType;
  confidence: number;
  authored_by?: string;
};

export type GraphResponse = {
  nodes: GraphNode[];
  edges: GraphEdge[];
};

export type Source = {
  source_id: string;
  title: string;
  url: string | null;
  type: 'web' | 'youtube' | 'pdf';
  author: string | null;
};

// Mirrors app/api/routers/items.py's GET /items/{note_id} response shape.
export type ItemDetail = {
  note_id: string;
  type: ItemType;
  title: string;
  authored_by?: string;
  source: Source | null;
  date?: string;
  tags?: string[];
  created_at?: string;
  reviewed_at?: string | null;
  body: string;
  connections: Record<string, string[]>;
};

// Mirrors app/api/routers/items.py's GET /items (list) response shape.
export type ItemSummary = {
  note_id: string;
  type: ItemType;
  title: string;
  authored_by?: string;
  date?: string;
  tags?: string[];
  created_at?: string;
  reviewed_at?: string | null;
};

// Mirrors app/api/routers/items.py's GET /sources response shape.
export type SourceListItem = Source & { retrieved_at?: string };

// Mirrors GET /items/review-queue's per-note edge summaries.
export type QueueOutgoingEdge = {
  edge_id: string;
  to_id: string;
  to_title: string;
  type: EdgeType;
  confidence: number;
};

export type QueueIncomingEdge = {
  edge_id: string;
  from_id: string;
  from_title: string;
  type: EdgeType;
  confidence: number;
};

export type ReviewQueueItem = ItemSummary & {
  outgoing_edges: QueueOutgoingEdge[];
  incoming_edges: QueueIncomingEdge[];
};

// Mirrors app/api/models.py's PermanentNoteCreateRequest.
export type PermanentNoteCreateRequest = {
  title: string;
  body: string;
  tags?: string[];
  grounded_in?: string[];
};

// Mirrors app/api/linkgen.py's write_permanent_note return shape (also
// POST /items/permanent's response).
export type PermanentNoteCreateResponse = {
  note_id: string;
  s3_key: string;
  title: string;
};
