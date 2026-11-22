import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { AgentNodeData, OutputNodeData } from '@/contexts/node-context';
import { cn } from '@/lib/utils';
import { useEffect, useMemo, useState } from 'react';
import { getActionColor, getDisplayName, getSignalColor, getStatusIcon } from './output-tab-utils';
import { ReasoningContent } from './reasoning-content';

// Animated progress dot
function ProgressDot({ active }: { active: boolean }) {
  return (
    <span className={cn(
      'inline-flex items-center justify-center w-2 h-2 rounded-full',
      active ? 'bg-green-500 animate-pulse' : 'bg-gray-400'
    )} />
  );
}

// Color constants for section header accents
const SECTION_STYLES = {
  progress: 'border-l-4 border-l-orange-500 bg-orange-50/30',
  summary: 'border-l-4 border-l-green-500 bg-green-50/30',
  analysis: 'border-l-4 border-l-purple-500 bg-purple-50/30',
};

// Progress Section Component with enhanced styling
function ProgressSection({ sortedAgents, outputData }: { sortedAgents: [string, AgentNodeData][]; outputData: OutputNodeData | null }) {
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null);

  if (sortedAgents.length === 0) return null;

  return (
    <Card className={cn("border-l-4", SECTION_STYLES.progress)}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-orange-600 dark:text-orange-400">Progress</h2>
          <span className="text-xs text-muted-foreground">{sortedAgents.length} agent(s)</span>
        </div>
        <span className="text-xs text-muted-foreground">{new Date(outputData?.timestamp || Date.now()).toLocaleTimeString()}</span>
      </CardHeader>
      <CardContent className="pt-4">
        <div className="space-y-3">
          {sortedAgents.map(([agentId, data]) => {
            const isExpanded = expandedAgent === agentId;
            const { icon: StatusIcon, color } = getStatusIcon(data.status);
            const displayName = getDisplayName(agentId);

            return (
              <div key={agentId} className="group">
                <div
                  className="flex items-center gap-2 p-2 rounded-lg hover:bg-muted/50 transition-colors cursor-pointer"
                  onClick={() => setExpandedAgent(isExpanded ? null : agentId)}
                >
                  <ProgressDot active={data.status === 'IN_PROGRESS'} />
                  <StatusIcon className={cn("h-4 w-4 flex-shrink-0", color)} />
                  <span className="font-medium text-sm flex-1 truncate">{displayName}</span>
                  {data.ticker && (
                    <span className="text-xs text-muted-foreground">[{data.ticker}]</span>
                  )}
                  <span className={cn("text-xs flex-1", color)}>
                    {data.message || data.status}
                  </span>
                  <span className="text-muted-foreground text-xs">
                    {new Date(data.timestamp || Date.now()).toLocaleTimeString()}
                  </span>
                  <svg
                    className={cn("w-3 h-3 transition-transform", isExpanded && "rotate-90")}
                    fill="none"
                    viewBox="0 0 12 12"
                  >
                    <path stroke="currentColor" strokeWidth="2" d="M5 3v6M5 9h1" />
                  </svg>
                </div>
                {isExpanded && (
                  <div className="px-2 pb-2 pl-6 text-xs text-muted-foreground animate-in fade-in-50 duration-300">
                    {data.detail || 'No additional details available.'}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

// Summary Section Component with enhanced styling
function SummarySection({ outputData }: { outputData: OutputNodeData | null }) {
  if (!outputData) return null;

  return (
    <Card className={cn("border-l-4", SECTION_STYLES.summary)}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <h2 className="text-sm font-semibold text-green-600 dark:text-green-400">Summary</h2>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="font-semibold text-sm">Ticker</TableHead>
              <TableHead className="font-semibold text-sm">Action</TableHead>
              <TableHead className="font-semibold text-sm">Quantity</TableHead>
              <TableHead className="font-semibold text-sm">Confidence</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {Object.entries(outputData.decisions).map(([ticker, decision]) => (
              <TableRow key={ticker} className="hover:bg-muted/30 transition-colors">
                <TableCell className="font-semibold">{ticker}</TableCell>
                <TableCell>
                  <span className={cn("font-semibold", getActionColor(decision.action || ''))}>
                    {decision.action?.toUpperCase() || 'UNKNOWN'}
                  </span>
                </TableCell>
                <TableCell className="font-mono">{decision.quantity || 0}</TableCell>
                <TableCell className="font-mono">{decision.confidence?.toFixed(1) || 0}%</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

// Analysis Results Section Component with enhanced styling
function AnalysisResultsSection({ outputData }: { outputData: OutputNodeData | null }) {
  // Always call hooks at the top of the function
  const [selectedTicker, setSelectedTicker] = useState<string>('');

  // Calculate tickers (safe to do even if outputData is null)
  const tickers = useMemo(
    () => (outputData?.decisions ? Object.keys(outputData.decisions) : []),
    [outputData]
  );

  // Set default selected ticker
  useEffect(() => {
    if (tickers.length > 0 && !selectedTicker) {
      setSelectedTicker(tickers[0]);
    }
  }, [tickers, selectedTicker]);

  // Early returns after all hooks are called
  if (!outputData) return null;
  if (tickers.length === 0) return null;

  return (
    <Card className={cn("border-l-4", SECTION_STYLES.analysis)}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <h2 className="text-sm font-semibold text-purple-600 dark:text-purple-400">Analysis</h2>
      </CardHeader>
      <CardContent>
        <Tabs value={selectedTicker} onValueChange={setSelectedTicker} className="w-full">
          <TabsList className="flex space-x-1 bg-muted p-1 rounded-lg mb-4">
            {tickers.map((ticker) => (
              <TabsTrigger
                key={ticker}
                value={ticker}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium rounded-md transition-all duration-200 data-[state=active]:bg-background data-[state=active]:text-primary data-[state=active]:shadow-sm"
              >
                {ticker}
              </TabsTrigger>
            ))}
          </TabsList>

          {tickers.map((ticker) => {
            const decision = outputData.decisions[ticker];

            return (
              <TabsContent key={ticker} value={ticker} className="space-y-4">
                {/* Agent Analysis */}
                <Card className="bg-transparent border-border">
                  <CardHeader>
                    <CardTitle className="text-sm font-semibold text-primary">Agent Signals</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="font-semibold text-sm">Agent</TableHead>
                          <TableHead className="font-semibold text-sm">Signal</TableHead>
                          <TableHead className="font-semibold text-sm">Confidence</TableHead>
                          <TableHead className="font-semibold text-sm">Reasoning</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {Object.entries(outputData.analyst_signals || {})
                          .filter(([agent, signals]) =>
                            ticker in signals && !agent.includes("risk_management")
                          )
                          .sort(([agentA], [agentB]) => agentA.localeCompare(agentB))
                          .map(([agent, signals]) => {
                            const signal = signals[ticker];
                            const signalType = signal.signal?.toUpperCase() || 'UNKNOWN';
                            const signalColor = getSignalColor(signalType);

                            return (
                              <TableRow key={agent} className="hover:bg-muted/30 transition-colors">
                                <TableCell className="font-medium text-sm">{getDisplayName(agent)}</TableCell>
                                <TableCell>
                                  <span className={cn("font-medium", signalColor)}>{signalType}</span>
                                </TableCell>
                                <TableCell className="font-mono">{signal.confidence || 0}%</TableCell>
                                <TableCell className="max-w-md">
                                  <ReasoningContent content={signal.reasoning} />
                                </TableCell>
                              </TableRow>
                            );
                          })}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>

                {/* Trading Decision */}
                <Card className="bg-transparent border-border">
                  <CardHeader>
                    <CardTitle className="text-sm font-semibold text-primary">Trading Decision</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="font-semibold text-sm">Property</TableHead>
                          <TableHead className="font-semibold text-sm">Value</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        <TableRow className="hover:bg-muted/30 transition-colors">
                          <TableCell className="font-semibold">Action</TableCell>
                          <TableCell>
                            <span className={cn("font-semibold", getActionColor(decision.action || ''))}>
                              {decision.action?.toUpperCase() || 'UNKNOWN'}
                            </span>
                          </TableCell>
                        </TableRow>
                        <TableRow className="hover:bg-muted/30 transition-colors">
                          <TableCell className="font-semibold">Quantity</TableCell>
                          <TableCell className="font-mono">{decision.quantity || 0}</TableCell>
                        </TableRow>
                        <TableRow className="hover:bg-muted/30 transition-colors">
                          <TableCell className="font-semibold">Confidence</TableCell>
                          <TableCell className="font-mono">{decision.confidence?.toFixed(1) || 0}%</TableCell>
                        </TableRow>
                        {decision.reasoning ? (
                          <TableRow className="hover:bg-muted/30 transition-colors">
                            <TableCell className="font-semibold">Reasoning</TableCell>
                            <TableCell className="max-w-md">
                              <ReasoningContent content={decision.reasoning} />
                            </TableCell>
                          </TableRow>
                        ) : null}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              </TabsContent>
            );
          })}
        </Tabs>
      </CardContent>
    </Card>
  );
}

// Main component for regular output
export function RegularOutput({
  sortedAgents,
  outputData,
}: {
  sortedAgents: [string, AgentNodeData][];
  outputData: OutputNodeData | null;
}) {
  return (
    <>
      <ProgressSection sortedAgents={sortedAgents} outputData={outputData} />
      <SummarySection outputData={outputData} />
      <AnalysisResultsSection outputData={outputData} />
    </>
  );
}
