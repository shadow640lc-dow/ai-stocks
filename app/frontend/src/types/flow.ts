import type { Edge, Node, Viewport } from '@xyflow/react';

export interface FlowNodeData {
  internal_state?: Record<string, unknown>;
  [key: string]: unknown;
}

export type FlowNode = Node<FlowNodeData>;

export interface FlowData {
  nodeStates?: Record<string, Record<string, unknown>>;
  [key: string]: unknown;
}

export interface Flow {
  id: number;
  name: string;
  description?: string;
  nodes: FlowNode[];
  edges: Edge[];
  viewport?: Viewport;
  data?: FlowData;
  is_template: boolean;
  tags?: string[];
  created_at: string;
  updated_at?: string;
}
