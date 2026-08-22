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
  body: string;
  connections: Record<string, string[]>;
};
