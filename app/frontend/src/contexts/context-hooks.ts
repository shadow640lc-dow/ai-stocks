import { createContext, useContext } from 'react';

import type { FlowContextType } from './flow-context';
import type { LayoutContextType } from './layout-context';
import type { NodeContextType } from './node-context';
import type { TabsContextType } from './tabs-context';

export const FlowContext = createContext<FlowContextType | null>(null);

export function useFlowContext() {
  const context = useContext(FlowContext);
  if (!context) {
    throw new Error('useFlowContext must be used within a FlowProvider');
  }
  return context;
}

export const NodeContext = createContext<NodeContextType | undefined>(undefined);

export function useNodeContext() {
  const context = useContext(NodeContext);

  if (context === undefined) {
    throw new Error('useNodeContext must be used within a NodeProvider');
  }

  return context;
}

export const TabsContext = createContext<TabsContextType | null>(null);

export function useTabsContext() {
  const context = useContext(TabsContext);
  if (!context) {
    throw new Error('useTabsContext must be used within a TabsProvider');
  }
  return context;
}

export const LayoutContext = createContext<LayoutContextType | null>(null);

export function useLayoutContext() {
  const context = useContext(LayoutContext);
  if (!context) {
    throw new Error('useLayoutContext must be used within a LayoutProvider');
  }
  return context;
}
