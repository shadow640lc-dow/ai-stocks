import { SidebarStorageService } from '@/services/sidebar-storage';
import { ReactNode, useEffect, useState } from 'react';

import { LayoutContext } from './context-hooks';

export interface LayoutContextType {
  isBottomCollapsed: boolean;
  expandBottomPanel: () => void;
  collapseBottomPanel: () => void;
  toggleBottomPanel: () => void;
  setBottomPanelTab: (tab: string) => void;
  currentBottomTab: string;
}

interface LayoutProviderProps {
  children: ReactNode;
}

export function LayoutProvider({ children }: LayoutProviderProps) {
  const [isBottomCollapsed, setIsBottomCollapsed] = useState(() => 
    SidebarStorageService.loadBottomPanelState(true)
  );
  const [currentBottomTab, setCurrentBottomTab] = useState('output');

  // Save bottom panel state when it changes
  useEffect(() => {
    SidebarStorageService.saveBottomPanelState(isBottomCollapsed);
  }, [isBottomCollapsed]);

  const expandBottomPanel = () => {
    setIsBottomCollapsed(false);
  };

  const collapseBottomPanel = () => {
    setIsBottomCollapsed(true);
  };

  const toggleBottomPanel = () => {
    setIsBottomCollapsed(!isBottomCollapsed);
  };

  const setBottomPanelTab = (tab: string) => {
    setCurrentBottomTab(tab);
  };

  const value = {
    isBottomCollapsed,
    expandBottomPanel,
    collapseBottomPanel,
    toggleBottomPanel,
    setBottomPanelTab,
    currentBottomTab,
  };

  return (
    <LayoutContext.Provider value={value}>
      {children}
    </LayoutContext.Provider>
  );
} 