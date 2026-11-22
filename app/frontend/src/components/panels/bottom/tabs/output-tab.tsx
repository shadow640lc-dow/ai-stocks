import { useFlowContext } from '@/contexts/context-hooks';
import { useNodeContext } from '@/contexts/context-hooks';
import { cn } from '@/lib/utils';
import { useEffect, useState, useRef } from 'react';
import { BacktestOutput } from './backtest-output';
import { sortAgents } from './output-tab-utils';
import { RegularOutput } from './regular-output';

interface OutputTabProps {
  className?: string;
}

export function OutputTab({ className }: OutputTabProps) {
  const { currentFlowId } = useFlowContext();
  const { getAgentNodeDataForFlow, getOutputNodeDataForFlow } = useNodeContext();
  const [, setUpdateTrigger] = useState(0);
  const hasMounted = useRef(false);

  // Get current flow data
  const agentData = getAgentNodeDataForFlow(currentFlowId?.toString() || null);
  const outputData = getOutputNodeDataForFlow(currentFlowId?.toString() || null);

  // Force re-render periodically to show real-time updates
  useEffect(() => {
    const interval = setInterval(() => {
      setUpdateTrigger(prev => prev + 1);
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  // Fade-in animation on mount
  useEffect(() => {
    if (hasMounted.current) return;
    hasMounted.current = true;
    const timer = setTimeout(() => {
      setUpdateTrigger(t => t + 1);
    }, 60);
    return () => clearTimeout(timer);
  }, []);

  // Detect if this is a backtest run
  const isBacktestRun = agentData && agentData['backtest'];

  // Sort agents for display (exclude backtest agent from regular agent list)
  const sortedAgents = sortAgents(Object.entries(agentData).filter(([agentId]) => agentId !== 'backtest'));

  return (
    <div className={cn("h-full overflow-y-auto font-mono text-sm", className)}>
      {/* Fade-in wrapper */}
      <div className="h-full overflow-y-auto font-mono text-sm animate-fadeIn">
        {/* Render backtest output if this is a backtest run */}
        {isBacktestRun && (
          <BacktestOutput agentData={agentData} outputData={outputData} />
        )}

        {/* Render regular output if not a backtest run */}
        {!isBacktestRun && (
          <RegularOutput sortedAgents={sortedAgents} outputData={outputData} />
        )}

        {/* Empty State */}
        {!outputData && sortedAgents.length === 0 && !isBacktestRun && (
          <div className="h-full flex items-center justify-center text-center p-8">
            <div className="animate-pulse text-muted-foreground">
              <div className="text-2xl mb-3">📡</div>
              <p className="text-sm text-muted-foreground">No output to display.</p>
              <p className="text-xs text-muted-foreground/70 mt-1">
                Run an analysis to see progress and results.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
