import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import axios from 'axios';
import * as d3 from 'd3';
import VirtualList from './VirtualList';

type NodeType = 'function' | 'api-call' | 'middleware' | 'route' | 'service' | 'db-query';

/** One function as the server lists it (no edge lists). */
export interface CallGraphBrief {
  id: string;
  name: string;
  file: string;
  type: NodeType;
  language: string;
  calls_count: number;
  called_by_count: number;
  is_test: boolean;
}

/** A function in a fetched neighbourhood: edges limited to the other returned functions. */
interface SubgraphNode extends CallGraphBrief {
  calls: string[];
  called_by: string[];
}

interface NodeDetail extends CallGraphBrief {
  calls: CallGraphBrief[];
  called_by: CallGraphBrief[];
}

/** What the `call_graph` stream event carries; the graph itself is queried on demand. */
export interface CallGraphSummary {
  available: boolean;
  total_functions: number;
  connected_functions: number;
  total_calls: number;
  test_functions: number;
  most_called: CallGraphBrief | null;
}

interface CallGraphProps {
  sessionId: string | null;
  summary: CallGraphSummary | null;
  isStreaming: boolean;
}

interface GraphNode {
  id: string;
  label: string;
  file: string;
  fileShort: string;
  isSelected: boolean;
  isExpanded: boolean;
  isCaller: boolean;    // Calls the selected function
  isCallee: boolean;    // Called by the selected function
  isConnected: boolean;
  callsCount: number;
  calledByCount: number;
  language: string;
  type: NodeType;
  x?: number;
  y?: number;
  fx?: number | null;
  fy?: number | null;
}

interface GraphLink {
  source: string | GraphNode;
  target: string | GraphNode;
  type: 'calls' | 'http' | 'db';
}

type ListRow = { kind: 'file'; file: string } | { kind: 'fn'; fn: CallGraphBrief };

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const PAGE_SIZE = 200;
const GRAPH_MAX_NODES = 150;
const FILE_ROW_HEIGHT = 26;
const FN_ROW_HEIGHT = 54;

function errorMessage(err: any): string {
  if (err?.response?.status === 404) {
    return 'This analysis session has expired. Run the analysis again (an unchanged commit loads from cache in seconds).';
  }
  return err?.response?.data?.detail || err?.message || 'Could not load the call graph.';
}

export default function CallGraph({ sessionId, summary, isStreaming }: CallGraphProps) {
  const [selectedFunction, setSelectedFunction] = useState<string | null>(null);
  const [expandedFunctions, setExpandedFunctions] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [displayMode, setDisplayMode] = useState<'graph' | 'list'>('graph');
  const graphMode: string = 'selected';
  const [graphDepth, setGraphDepth] = useState(2);
  const [groupByFile, setGroupByFile] = useState(true);
  const [fullStackMode, setFullStackMode] = useState(true);
  const [includeTests, setIncludeTests] = useState(false);
  const [sortBy, setSortBy] = useState<'file' | 'called'>('file');
  const svgRef = useRef<SVGSVGElement>(null);

  // ---- Function list: server-side search, paged, rendered virtualized
  const [listItems, setListItems] = useState<CallGraphBrief[]>([]);
  const [listTotal, setListTotal] = useState(0);
  const [listLoading, setListLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const listRequest = useRef(0);
  const pageInFlight = useRef(false); // scroll events fire faster than state updates
  const ready = !!sessionId && !!summary?.available;

  // Everything the client has seen, so names stay available for pinned chips and headers.
  const known = useRef<Map<string, CallGraphBrief>>(new Map());
  const remember = (items: CallGraphBrief[]) => items.forEach(f => known.current.set(f.id, f));

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(searchQuery.trim()), 200);
    return () => clearTimeout(t);
  }, [searchQuery]);

  const fetchPage = useCallback(async (offset: number) => {
    if (!sessionId) return;
    const request = offset === 0 ? ++listRequest.current : listRequest.current;
    pageInFlight.current = true;
    setListLoading(true);
    try {
      const { data } = await axios.get(`${API_BASE_URL}/api/callgraph/${sessionId}/functions`, {
        params: { q: debouncedQuery, include_tests: includeTests, sort: sortBy, offset, limit: PAGE_SIZE },
      });
      if (request !== listRequest.current) return; // a newer search replaced this one
      remember(data.items);
      setListItems(prev => (offset === 0 ? data.items : [...prev, ...data.items]));
      setListTotal(data.total);
      setError(null);
    } catch (err) {
      if (request === listRequest.current) setError(errorMessage(err));
    } finally {
      if (request === listRequest.current) {
        pageInFlight.current = false;
        setListLoading(false);
      }
    }
  }, [sessionId, debouncedQuery, includeTests, sortBy]);

  useEffect(() => {
    if (ready) fetchPage(0);
  }, [ready, fetchPage]);

  const loadMore = useCallback(() => {
    if (!pageInFlight.current && listItems.length < listTotal) fetchPage(listItems.length);
  }, [listItems.length, listTotal, fetchPage]);

  // Rows for the virtual list: file headers interleaved when grouping (file order only).
  const grouped = groupByFile && sortBy === 'file';
  const rows = useMemo<ListRow[]>(() => {
    if (!grouped) return listItems.map(fn => ({ kind: 'fn', fn }));
    const out: ListRow[] = [];
    let file: string | null = null;
    for (const fn of listItems) {
      if (fn.file !== file) {
        file = fn.file;
        out.push({ kind: 'file', file });
      }
      out.push({ kind: 'fn', fn });
    }
    return out;
  }, [listItems, grouped]);

  // ---- Graph: the neighbourhood of the pinned functions, fetched on demand
  const [subgraph, setSubgraph] = useState<Record<string, SubgraphNode>>({});
  const [truncated, setTruncated] = useState(false);
  const pinnedKey = useMemo(() => Array.from(expandedFunctions).sort().join('\n'), [expandedFunctions]);

  useEffect(() => {
    if (!sessionId || !pinnedKey) {
      setSubgraph({});
      setTruncated(false);
      return;
    }
    let cancelled = false;
    const params = new URLSearchParams();
    pinnedKey.split('\n').forEach(id => params.append('ids', id));
    params.set('depth', String(graphDepth));
    params.set('include_tests', String(includeTests));
    params.set('max_nodes', String(GRAPH_MAX_NODES));
    axios.get(`${API_BASE_URL}/api/callgraph/${sessionId}/neighbourhood`, { params })
      .then(({ data }) => {
        if (cancelled) return;
        remember(Object.values(data.nodes) as CallGraphBrief[]);
        setSubgraph(data.nodes);
        setTruncated(!!data.truncated);
      })
      .catch(err => { if (!cancelled) setError(errorMessage(err)); });
    return () => { cancelled = true; };
  }, [sessionId, pinnedKey, graphDepth, includeTests]);

  // ---- List view: one function with all its callers and callees
  const [nodeDetail, setNodeDetail] = useState<NodeDetail | null>(null);
  useEffect(() => {
    if (!sessionId || !selectedFunction || displayMode !== 'list') return;
    let cancelled = false;
    axios.get(`${API_BASE_URL}/api/callgraph/${sessionId}/node`, {
      params: { id: selectedFunction, include_tests: includeTests },
    })
      .then(({ data }) => {
        if (cancelled) return;
        remember([data, ...data.calls, ...data.called_by]);
        setNodeDetail(data);
      })
      .catch(err => { if (!cancelled) setError(errorMessage(err)); });
    return () => { cancelled = true; };
  }, [sessionId, selectedFunction, displayMode, includeTests]);

  // Handle function selection from sidebar
  const handleFunctionSelect = useCallback((funcId: string) => {
    setSelectedFunction(funcId);
    setExpandedFunctions(new Set([funcId]));
  }, []);

  // Clear selection
  const handleClearSelection = useCallback(() => {
    setSelectedFunction(null);
    setExpandedFunctions(new Set());
  }, []);

  // Handle node click in graph
  const handleNodeClick = useCallback((funcId: string) => {
    if (graphMode === 'selected') {
      setExpandedFunctions(prev => {
        const newSet = new Set(prev);
        if (newSet.has(funcId) && newSet.size > 1) {
          // Toggle off if already present (multi-select mode)
          newSet.delete(funcId);
          if (selectedFunction === funcId) {
            setSelectedFunction(Array.from(newSet).pop() || null);
          }
        } else {
          newSet.add(funcId);
          setSelectedFunction(funcId);
        }
        return newSet;
      });
    } else {
      setSelectedFunction(funcId);
    }
  }, [graphMode, selectedFunction]);

  const handleRemoveFunction = useCallback((funcId: string) => {
    setExpandedFunctions(prev => {
      const newSet = new Set(prev);
      newSet.delete(funcId);
      if (selectedFunction === funcId) {
        setSelectedFunction(Array.from(newSet).pop() || null);
      }
      return newSet;
    });
  }, [selectedFunction]);

  // Get function info for selected function
  const selectedInfo = useMemo<CallGraphBrief | null>(() => {
    if (!selectedFunction) return null;
    if (nodeDetail?.id === selectedFunction) return nodeDetail;
    return subgraph[selectedFunction] || known.current.get(selectedFunction) || null;
  }, [selectedFunction, nodeDetail, subgraph]);
  const selectedDetail = nodeDetail?.id === selectedFunction ? nodeDetail : null;

  // Helper functions
  const getFileName = (path: string) => path.split('/').pop() || path;
  const getFuncName = (funcId: string) => funcId.split('::').pop() || funcId;
  const getFilePath = (path: string) => {
    const parts = path.split('/');
    return parts.slice(0, -1).join('/') || '/';
  };

  const getFileIcon = (file: string) => {
    const ext = file.split('.').pop()?.toLowerCase() || '';
    if (['ts', 'tsx'].includes(ext)) return '🔷';
    if (['js', 'jsx'].includes(ext)) return '🟨';
    if (ext === 'py') return '🐍';
    if (ext === 'java') return '☕';
    if (ext === 'go') return '🔵';
    if (ext === 'rs') return '🦀';
    return '📄';
  };

  // Get node color based on state and type
  const getNodeColor = useCallback((node: GraphNode) => {
    if (node.isSelected) return '#3b82f6'; // blue for selected
    
    // Type-based colors for Full-stack mode
    if (node.type === 'api-call') return '#f59e0b';   // orange for API boundary
    if (node.type === 'middleware') return '#ec4899'; // pink for middleware
    if (node.type === 'route') return '#ef4444';      // red for route handler (controller)
    if (node.type === 'service') return '#8b5cf6';    // purple for service
    if (node.type === 'db-query') return '#10b981';   // emerald for DB
    
    if (node.isExpanded && !node.isSelected) return '#0ea5e9'; // cyan for expanded
    if (node.isCallee) return '#22c55e';   // green for callees
    if (node.isCaller) return '#38bdf8';   // sky blue for callers
    return '#64748b'; // gray for other
  }, []);

  // Statistics come with the stream; they cover the whole graph.
  const stats = {
    totalFunctions: summary?.total_functions ?? 0,
    connectedFunctions: summary?.connected_functions ?? 0,
    totalCalls: summary?.total_calls ?? 0,
    mostCalledName: summary?.most_called?.name || '-',
    mostCalledCount: summary?.most_called?.called_by_count ?? 0,
  };

  const renderFunctionButton = (info: CallGraphBrief, subtitle: string) => {
    const isSelected = info.id === selectedFunction;
    return (
      <button
        onClick={() => handleFunctionSelect(info.id)}
        className={`w-full h-[50px] text-left p-2 rounded transition-all ${
          isSelected
            ? 'bg-blue-100 dark:bg-blue-900/40 border border-blue-300 dark:border-blue-700'
            : 'bg-white dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 border border-transparent'
        }`}
      >
        <div className="flex items-center gap-2">
          <span className="text-sm">⚡</span>
          <span className="text-xs font-medium text-slate-900 dark:text-white truncate flex-1">
            {info.name}
          </span>
          {info.is_test && (
            <span className="text-[9px] px-1 bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 rounded">test</span>
          )}
        </div>
        <div className="flex items-center gap-2 mt-0.5 ml-6">
          <span className="text-[10px] text-slate-500 truncate flex-1">
            {subtitle}
          </span>
          <div className="flex gap-1">
            {info.calls_count > 0 && (
              <span className="text-[9px] px-1 bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300 rounded">
                ↗{info.calls_count}
              </span>
            )}
            {info.called_by_count > 0 && (
              <span className="text-[9px] px-1 bg-sky-100 dark:bg-sky-900/40 text-sky-700 dark:text-sky-300 rounded">
                ↙{info.called_by_count}
              </span>
            )}
          </div>
        </div>
      </button>
    );
  };

  // "12 of 2,572" when hidden tests (or the server's cap) leave some out of the list.
  const edgeCount = (shown: CallGraphBrief[] | undefined, total: number) =>
    shown && shown.length !== total
      ? `${shown.length.toLocaleString()} of ${total.toLocaleString()}${includeTests ? '' : ', tests hidden'}`
      : total.toLocaleString();

  const renderEdgeList = (edges: CallGraphBrief[] | undefined, emptyText: string) => {
    if (!edges) return <p className="text-sm text-slate-500">Loading...</p>;
    if (edges.length === 0) return <p className="text-sm text-slate-500 italic">{emptyText}</p>;
    return (
      <VirtualList
        items={edges}
        maxHeight={350}
        rowKey={(f) => f.id}
        rowHeight={() => FN_ROW_HEIGHT}
        renderRow={(f) => (
          <button
            onClick={() => handleFunctionSelect(f.id)}
            className="w-full h-[50px] flex items-center gap-2 p-2 bg-slate-50 dark:bg-slate-700/50 hover:bg-slate-100 dark:hover:bg-slate-700 rounded text-left"
          >
            <span>{getFileIcon(f.file)}</span>
            <div className="flex-1 min-w-0">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-300 block truncate">
                {f.name}
              </span>
              <span className="text-[10px] text-slate-500 block truncate">
                {f.file}
              </span>
            </div>
          </button>
        )}
      />
    );
  };

  // Build and render D3 graph
  useEffect(() => {
    if (!svgRef.current || displayMode !== 'graph') return;

    // Clear previous content
    d3.select(svgRef.current).selectAll('*').remove();

    // Only the fetched neighbourhood of the pinned functions is drawn.
    const callGraph = subgraph;
    if (Object.keys(callGraph).length === 0) return;

    let simulation: any;

    try {

    const functionsToShow = new Set<string>();
    const linksData: Array<{ source: string; target: string; type: 'calls' | 'http' | 'db' }> = [];

    // Track functions connected to selected
    const connectedToSelected = new Set<string>();
    if (selectedFunction) {
      connectedToSelected.add(selectedFunction);
      (callGraph[selectedFunction]?.calls || []).forEach(c => connectedToSelected.add(c));
      (callGraph[selectedFunction]?.called_by || []).forEach(c => connectedToSelected.add(c));
    }

    if (graphMode === 'all') {
      // Show all functions that have connections (limit to avoid overwhelming)
      let connectionCount = 0;
      const maxConnections = 500;

      Object.entries(callGraph || {}).forEach(([funcId, info]) => {
        if (connectionCount >= maxConnections) return;
        if (!info) return;
        
        // --- Full-Stack Filter ---
        if (!fullStackMode && info.type && info.type !== 'function') return;

        const calls = info.calls || [];
        const calledBy = info.called_by || [];

        if (calls.length > 0 || calledBy.length > 0) {
          functionsToShow.add(funcId);
          calls.forEach(callee => {
            if (connectionCount < maxConnections && callGraph[callee]) {
              // --- Full-Stack Filter ---
              if (!fullStackMode && callGraph[callee].type && callGraph[callee].type !== 'function') return;

              functionsToShow.add(callee);
              
              // Determine link type
              let linkType: 'calls' | 'http' | 'db' = 'calls';
              if (info.type === 'api-call') linkType = 'http';
              if (callGraph[callee].type === 'db-query') linkType = 'db';

              linksData.push({ source: funcId, target: callee, type: linkType });
              connectionCount++;
            }
          });
        }
      });
    } else if (selectedFunction || expandedFunctions.size > 0) {
      // Show selected function and its connections up to depth
      const funcsToExpand = expandedFunctions.size > 0 ? expandedFunctions : new Set([selectedFunction!]);
      const addedLinks = new Set<string>();
      const visited = new Set<string>();

      const collectConnections = (funcId: string, depth: number, direction: 'calls' | 'calledBy') => {
        if (depth > graphDepth) return;
        
        const info = callGraph[funcId];
        if (!info) return;

        // --- Full-Stack Filter ---
        if (!fullStackMode && info.type && info.type !== 'function') return;

        if (visited.has(`${funcId}-${direction}-${depth}`)) return;
        visited.add(`${funcId}-${direction}-${depth}`);

        functionsToShow.add(funcId);

        if (direction === 'calls') {
          (info.calls || []).forEach(callee => {
            const calleeInfo = callGraph[callee];
            if (!calleeInfo) return;
            
            // --- Full-Stack Filter ---
            if (!fullStackMode && calleeInfo.type && calleeInfo.type !== 'function') return;

            const linkKey = `${funcId}->${callee}`;
            if (!addedLinks.has(linkKey)) {
              addedLinks.add(linkKey);
              
              let linkType: 'calls' | 'http' | 'db' = 'calls';
              if (info.type === 'api-call') linkType = 'http';
              if (calleeInfo.type === 'db-query') linkType = 'db';
              
              linksData.push({ source: funcId, target: callee, type: linkType });
            }
            if (!functionsToShow.has(callee)) {
              collectConnections(callee, depth + 1, 'calls');
            }
          });
        } else {
          (info.called_by || []).forEach(caller => {
            const callerInfo = callGraph[caller];
            if (!callerInfo) return;
            
            // --- Full-Stack Filter ---
            if (!fullStackMode && callerInfo.type && callerInfo.type !== 'function') return;

            const linkKey = `${caller}->${funcId}`;
            if (!addedLinks.has(linkKey)) {
              addedLinks.add(linkKey);
              
              let linkType: 'calls' | 'http' | 'db' = 'calls';
              if (callerInfo.type === 'api-call') linkType = 'http';
              if (info.type === 'db-query') linkType = 'db';

              linksData.push({ source: caller, target: funcId, type: linkType });
            }
            if (!functionsToShow.has(caller)) {
              collectConnections(caller, depth + 1, 'calledBy');
            }
          });
        }
      };

      funcsToExpand.forEach(funcId => {
        if (callGraph[funcId]) {
          functionsToShow.add(funcId);
          collectConnections(funcId, 0, 'calls');
          collectConnections(funcId, 0, 'calledBy');
        }
      });
    }

    if (functionsToShow.size === 0) return;

    // Filter to only include functions that exist in callGraph
    const validFunctions = Array.from(functionsToShow).filter(f => callGraph[f]);

    if (validFunctions.length === 0) return;

    // Create a set of valid function IDs for quick lookup
    const validFunctionSet = new Set(validFunctions);

    // Create nodes array
    const nodes: GraphNode[] = validFunctions.map(funcId => {
      const info = callGraph[funcId];
      if (!info) return null;

      const selectedInfoLocal = selectedFunction ? callGraph[selectedFunction] : null;

      const isCallee = selectedInfoLocal ? (selectedInfoLocal.calls || []).includes(funcId) : false;
      const isCaller = selectedInfoLocal ? (selectedInfoLocal.called_by || []).includes(funcId) : false;
      const isConnected = connectedToSelected.has(funcId);
      const isExpanded = expandedFunctions.has(funcId);

      return {
        id: funcId,
        label: info.name || funcId.split('::').pop() || funcId,
        file: info.file || '',
        fileShort: getFileName(info.file || ''),
        isSelected: funcId === selectedFunction,
        isExpanded,
        isCaller,
        isCallee,
        isConnected,
        callsCount: info.calls_count,
        calledByCount: info.called_by_count,
        language: info.language || 'Unknown',
        type: (info.type as any) || 'function',
      };
    }).filter((n): n is GraphNode => n !== null);

    // Create links array - only include links where both source and target exist
    const links: GraphLink[] = linksData
      .filter(l => validFunctionSet.has(l.source) && validFunctionSet.has(l.target))
      .map(l => ({ source: l.source, target: l.target, type: l.type }));

    // Create node map for lookups
    const nodeMap = new Map(nodes.map(n => [n.id, n]));

    // Set up SVG dimensions
    const width = 900;
    const height = 700;
    const svg = d3.select(svgRef.current)
      .attr('width', '100%')
      .attr('height', '100%')
      .attr('viewBox', `0 0 ${width} ${height}`);

    // Create container for zoom
    const container = svg.append('g');

    // Add zoom behavior
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        container.attr('transform', event.transform);
      });
    svg.call(zoom);

    // Create arrow markers
    svg.append('defs').append('marker')
      .attr('id', 'arrowhead-call')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 25)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .append('svg:path')
      .attr('d', 'M 0,-5 L 10 ,0 L 0,5')
      .attr('fill', '#64748b');

    // Create selected arrow marker
    svg.select('defs').append('marker')
      .attr('id', 'arrowhead-call-selected')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 25)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .append('svg:path')
      .attr('d', 'M 0,-5 L 10 ,0 L 0,5')
      .attr('fill', '#3b82f6');

    // Create outgoing call arrow marker
    svg.select('defs').append('marker')
      .attr('id', 'arrowhead-call-outgoing')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 25)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .append('svg:path')
      .attr('d', 'M 0,-5 L 10 ,0 L 0,5')
      .attr('fill', '#22c55e');

    // Create incoming call arrow marker
    svg.select('defs').append('marker')
      .attr('id', 'arrowhead-call-incoming')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 25)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .append('svg:path')
      .attr('d', 'M 0,-5 L 10 ,0 L 0,5')
      .attr('fill', '#a855f7');

    // Create simulation
    simulation = d3.forceSimulation(nodes as any)
      .force('link', d3.forceLink(links)
        .id((d: any) => d.id)
        .distance(120))
      .force('charge', d3.forceManyBody().strength(-400))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(40));

    // Draw links
    const link = container.append('g')
      .selectAll('line')
      .data(links)
      .enter()
      .append('line')
      .attr('stroke', (d: any) => {
        const sourceNode = typeof d.source === 'object' ? d.source : nodeMap.get(d.source);
        const targetNode = typeof d.target === 'object' ? d.target : nodeMap.get(d.target);
        if (selectedFunction) {
          const sourceId = sourceNode?.id || d.source;
          const targetId = targetNode?.id || d.target;
          if (sourceId === selectedFunction) return '#22c55e'; // calls (outgoing)
          if (targetId === selectedFunction) return '#a855f7'; // called by (incoming)
        }
        if (sourceNode?.isSelected || targetNode?.isSelected) return '#3b82f6';
        if (selectedFunction && (sourceNode?.isConnected && targetNode?.isConnected)) return '#94a3b8';
        return '#64748b';
      })
      .attr('stroke-opacity', (d: any) => {
        const sourceNode = typeof d.source === 'object' ? d.source : nodeMap.get(d.source);
        const targetNode = typeof d.target === 'object' ? d.target : nodeMap.get(d.target);
        if (graphMode === 'all' && selectedFunction) {
          if (sourceNode?.isSelected || targetNode?.isSelected) return 0.9;
          if (sourceNode?.isConnected && targetNode?.isConnected) return 0.6;
          return 0.15;
        }
        return 0.6;
      })
      .attr('stroke-width', (d: any) => {
        const sourceNode = typeof d.source === 'object' ? d.source : nodeMap.get(d.source);
        const targetNode = typeof d.target === 'object' ? d.target : nodeMap.get(d.target);
        if (sourceNode?.isSelected || targetNode?.isSelected) return 2.5;
        return 1.5;
      })
      .attr('stroke-dasharray', (d: any) => {
        if (d.type === 'http') return '5,5'; // Dashed for HTTP calls
        if (d.type === 'db') return '2,2';   // Dotted for DB queries
        return null;
      })
      .attr('marker-end', (d: any) => {
        if (selectedFunction) {
          const sourceNode = typeof d.source === 'object' ? d.source : nodeMap.get(d.source);
          const targetNode = typeof d.target === 'object' ? d.target : nodeMap.get(d.target);
          const sourceId = sourceNode?.id || d.source;
          const targetId = targetNode?.id || d.target;
          if (sourceId === selectedFunction) return 'url(#arrowhead-call-outgoing)';
          if (targetId === selectedFunction) return 'url(#arrowhead-call-incoming)';
          if (sourceNode?.isSelected || targetNode?.isSelected) return 'url(#arrowhead-call-selected)';
        }
        return 'url(#arrowhead-call)';
      });

    // Draw nodes
    let isDragging = false;
    const node = container.append('g')
      .selectAll('g')
      .data(nodes)
      .enter()
      .append('g')
      .style('cursor', 'pointer')
      .call(d3.drag<any, any>()
        .on('start', (event) => {
          isDragging = false;
          if (!event.active) simulation.alphaTarget(0.3).restart();
          event.subject.fx = event.subject.x;
          event.subject.fy = event.subject.y;
        })
        .on('drag', (event) => {
          isDragging = true;
          event.subject.fx = event.x;
          event.subject.fy = event.y;
        })
        .on('end', (event) => {
          if (!event.active) simulation.alphaTarget(0);
          event.subject.fx = null;
          event.subject.fy = null;
        }) as any)
      .on('click', (_, d) => {
        if (!isDragging) {
          handleNodeClick(d.id);
        }
      })
      .on('contextmenu', (event, d) => {
        event.preventDefault();
        handleRemoveFunction(d.id);
      });

    // Node circles
    node.append('circle')
      .attr('r', (d: GraphNode) => d.isSelected ? 14 : (d.isExpanded ? 13 : 12))
      .attr('fill', (d: GraphNode) => getNodeColor(d))
      .attr('stroke', '#fff')
      .attr('stroke-width', 2)
      .attr('opacity', (d: GraphNode) => {
        if (graphMode === 'all' && selectedFunction && !d.isConnected) return 0.3;
        return 1;
      });

    // Node labels
    node.append('text')
      .text((d: GraphNode) => d.label.substring(0, 20))
      .attr('x', 18)
      .attr('y', 4)
      .attr('font-size', 11)
      .attr('fill', '#334155')
      .attr('class', 'dark:fill-slate-300')
      .attr('opacity', (d: GraphNode) => {
        if (graphMode === 'all' && selectedFunction && !d.isConnected) return 0.3;
        return 1;
      });

    // Tooltips
    node.append('title')
      .text((d: GraphNode) => `${d.label}\nFile: ${d.file}\nCalls: ${d.callsCount} | Called by: ${d.calledByCount}`);

    // Link final update
    simulation.on('tick', () => {
      link
        .attr('x1', (d: any) => d.source.x)
        .attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x)
        .attr('y2', (d: any) => d.target.y);

      node.attr('transform', (d: any) => `translate(${d.x},${d.y})`);
    });

    // Node Badges (A, M, C, S, D)
    const badge = node.append('g')
      .attr('display', fullStackMode ? 'block' : 'none');

    badge.append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', '.35em')
      .attr('font-size', '8px')
      .attr('font-weight', 'bold')
      .attr('fill', '#fff')
      .text((d: GraphNode) => {
        if (d.type === 'api-call') return 'A';
        if (d.type === 'middleware') return 'M';
        if (d.type === 'route') return 'C';
        if (d.type === 'service') return 'S';
        if (d.type === 'db-query') return 'D';
        return '';
      });

    } catch (error) {
      console.error('Error rendering call graph:', error);
      if (svgRef.current) {
        d3.select(svgRef.current).selectAll('*').remove();
      }
    }

    return () => {
      if (simulation) simulation.stop();
    };
    // handleRemoveFunction is recreated every render; listing it would rebuild the graph each time.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subgraph, displayMode, graphMode, selectedFunction, expandedFunctions, graphDepth, getNodeColor, handleNodeClick, fullStackMode]);


  // Empty state
  if (!ready) {
    const building = !summary && isStreaming;
    return (
      <div className="text-center py-12 bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
        <div className="text-6xl mb-4">🔀</div>
        <p className="text-lg font-medium text-slate-700 dark:text-slate-300 mb-2">
          {building ? 'Building the call graph...' : 'No call graph data available'}
        </p>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          {building
            ? 'It appears here as soon as the static analysis finishes'
            : 'Analyze a repository with functions to see call relationships'}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4 relative">
      {/* Header with Stats */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
            🔀 Call Graph
          </h3>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Function-to-function call relationships across the codebase
          </p>
        </div>

        {/* Quick Stats */}
        <div className="flex gap-3">
          <div className="text-center px-3 py-1 bg-blue-50 dark:bg-blue-900/30 rounded">
            <p className="text-lg font-bold text-blue-600 dark:text-blue-400">{stats.totalFunctions}</p>
            <p className="text-[10px] text-slate-500">Functions</p>
          </div>
          <div className="text-center px-3 py-1 bg-green-50 dark:bg-green-900/30 rounded">
            <p className="text-lg font-bold text-green-600 dark:text-green-400">{stats.connectedFunctions}</p>
            <p className="text-[10px] text-slate-500">Connected</p>
          </div>
          <div className="text-center px-3 py-1 bg-sky-50 dark:bg-sky-900/30 rounded">
            <p className="text-lg font-bold text-sky-600 dark:text-sky-400">{stats.totalCalls}</p>
            <p className="text-[10px] text-slate-500">Calls</p>
          </div>
          <div className="text-center px-3 py-1 bg-purple-50 dark:bg-purple-900/30 rounded">
            <p className="text-sm font-bold text-purple-600 dark:text-purple-400 truncate max-w-[80px]">{stats.mostCalledName}</p>
            <p className="text-[10px] text-slate-500">Most Called ({stats.mostCalledCount})</p>
          </div>
        </div>
      </div>

      {/* View Mode Toggle */}
      <div className="flex flex-wrap gap-4 items-center">
        <div className="flex gap-1 bg-slate-100 dark:bg-slate-700 p-1 rounded-lg">
          <button
            onClick={() => setDisplayMode('graph')}
            className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
              displayMode === 'graph'
                ? 'bg-white dark:bg-slate-600 text-slate-900 dark:text-white shadow'
                : 'text-slate-600 dark:text-slate-400'
            }`}
          >
            📊 Graph View
          </button>
          <button
            onClick={() => setDisplayMode('list')}
            className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
              displayMode === 'list'
                ? 'bg-white dark:bg-slate-600 text-slate-900 dark:text-white shadow'
                : 'text-slate-600 dark:text-slate-400'
            }`}
          >
            📋 List View
          </button>
        </div>

        {displayMode === 'graph' && (
          <>
            {/* Removed Graph Mode toggle to prevent rendering all functions which crashes UI */}

            {graphMode === 'selected' && (
              <div className="flex items-center gap-2">
                <span className="text-sm text-slate-600 dark:text-slate-400">Depth:</span>
                <select
                  value={graphDepth}
                  onChange={(e) => setGraphDepth(Number(e.target.value))}
                  className="px-2 py-1 text-sm bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded"
                >
                  {[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{n}</option>)}
                </select>
              </div>
            )}
          </>
        )}
      </div>

      {error && (
        <div className="px-3 py-2 text-sm rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-800">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Function Selection Panel */}
        <div className="lg:col-span-1">
          <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg border border-slate-200 dark:border-slate-600 p-3">
            <h4 className="text-sm font-semibold text-slate-800 dark:text-slate-200 mb-2">
              Select Function ({listTotal.toLocaleString()})
            </h4>

            <div className="relative mb-2">
              <input
                type="text"
                placeholder="Search functions or files..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full px-3 py-1.5 pl-8 text-sm bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-600 rounded-lg"
              />
              <span className="absolute left-2.5 top-2 text-slate-400 text-sm">🔍</span>
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="absolute right-2 top-1.5 text-slate-400 hover:text-slate-600 text-sm"
                >
                  ✕
                </button>
              )}
            </div>

            <div className="flex items-center justify-between gap-2 mb-1">
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as 'file' | 'called')}
                className="px-2 py-1 text-xs bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-600 rounded"
                aria-label="Sort functions"
              >
                <option value="file">By file</option>
                <option value="called">Most called</option>
              </select>
              {selectedFunction && (
                <button
                  onClick={handleClearSelection}
                  className="text-xs px-2 py-1 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 rounded-lg transition-colors"
                >
                  Clear
                </button>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mb-2">
              {sortBy === 'file' && (
                <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-400">
                  <input
                    type="checkbox"
                    checked={groupByFile}
                    onChange={(e) => setGroupByFile(e.target.checked)}
                    className="rounded"
                  />
                  Group by file
                </label>
              )}
              <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-400" title="Test files are hidden from the list and the graph unless this is on">
                <input
                  type="checkbox"
                  checked={includeTests}
                  onChange={(e) => setIncludeTests(e.target.checked)}
                  className="rounded"
                />
                Show tests{summary?.test_functions ? ` (${summary.test_functions.toLocaleString()})` : ''}
              </label>
            </div>

            <VirtualList
              items={rows}
              maxHeight={650}
              rowKey={(row) => (row.kind === 'file' ? `file:${row.file}` : row.fn.id)}
              rowHeight={(row) => (row.kind === 'file' ? FILE_ROW_HEIGHT : FN_ROW_HEIGHT)}
              onEndReached={loadMore}
              renderRow={(row) => row.kind === 'file' ? (
                <div className="text-xs font-medium text-slate-500 dark:text-slate-400 px-2 py-1 truncate" title={row.file}>
                  {getFileIcon(row.file)} {getFileName(row.file)}
                </div>
              ) : renderFunctionButton(row.fn, grouped ? (getFilePath(row.fn.file) || '/') : getFileName(row.fn.file))}
            />
            {listLoading && (
              <p className="text-[11px] text-slate-500 mt-2">Loading...</p>
            )}
            {!listLoading && listItems.length === 0 && (
              <p className="text-xs text-slate-500 italic mt-2">No matching functions</p>
            )}
          </div>
        </div>

        {/* Main Content Area */}
        <div className="lg:col-span-3">
          {displayMode === 'graph' ? (
            /* Graph View - D3 force-directed graph */
            (graphMode === 'all' || selectedFunction) ? (
              <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-4">
                <div className="mb-4 flex flex-col gap-3">
                  <div className="flex items-start justify-between">
                    <div>
                      <h4 className="text-md font-semibold text-slate-900 dark:text-white mb-1">
                        {graphMode === 'all'
                          ? (selectedFunction ? `Connections for ${selectedInfo?.name || getFuncName(selectedFunction)}` : 'All Function Calls')
                          : expandedFunctions.size > 1
                          ? `Exploring ${expandedFunctions.size} functions`
                          : `Call graph for ${selectedInfo?.name || getFuncName(selectedFunction || '')}`}
                      </h4>
                      <p className="text-sm text-slate-600 dark:text-slate-400">
                        {graphMode === 'all' && selectedFunction
                          ? 'Showing connected functions highlighted. Click another node or clear selection.'
                          : graphMode === 'selected' && selectedFunction
                          ? 'Click any node to expand or remove. Drag to reposition, scroll to zoom.'
                          : 'Interactive visualization. Drag nodes to explore connections. Scroll to zoom.'}
                      </p>
                    </div>
                    {selectedFunction && (
                      <button
                        onClick={handleClearSelection}
                        className="px-3 py-1.5 text-xs font-medium bg-red-50 dark:bg-red-900/20 hover:bg-red-100 dark:hover:bg-red-900/40 text-red-600 dark:text-red-400 rounded-lg transition-colors flex items-center gap-2"
                      >
                        ✕ Reset All
                      </button>
                    )}
                  </div>

                  {/* Active Pinned Nodes Chips */}
                  {graphMode === 'selected' && expandedFunctions.size > 0 && (
                    <div className="flex flex-wrap gap-2 pt-2 border-t border-slate-100 dark:border-slate-700">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider self-center mr-1">Pinned:</span>
                      {Array.from(expandedFunctions).map(funcId => (
                        <div key={funcId} className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-[10px] font-medium transition-all ${
                          selectedFunction === funcId 
                            ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 ring-1 ring-blue-300 dark:ring-blue-800'
                            : 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-600'
                        }`}>
                          <span className="cursor-pointer" onClick={() => setSelectedFunction(funcId)}>
                            {known.current.get(funcId)?.name || getFuncName(funcId)}
                          </span>
                          <button 
                            onClick={(e) => {
                              e.stopPropagation();
                              handleRemoveFunction(funcId);
                            }}
                            className="hover:text-red-500 transition-colors"
                          >
                            ✕
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                {truncated && (
                  <p className="text-xs text-amber-700 dark:text-amber-300 mb-2">
                    Showing the nearest {GRAPH_MAX_NODES} functions. Lower the depth or pin fewer functions to see the rest.
                  </p>
                )}
                <svg ref={svgRef} className="w-full h-[700px] bg-slate-50 dark:bg-slate-900 rounded-lg" />
              </div>
            ) : (
              <div className="flex items-center justify-center h-[700px] bg-slate-50 dark:bg-slate-700/50 rounded-lg border border-slate-200 dark:border-slate-600">
                <div className="text-center">
                  <div className="text-5xl mb-4">👈</div>
                  <p className="text-lg text-slate-600 dark:text-slate-400">
                    Select a function to view its call graph
                  </p>
                  <p className="text-sm text-slate-500 mt-2">
                    Or pick one of the most called: sort the list by "Most called"
                  </p>
                </div>
              </div>
            )
          ) : selectedFunction && selectedInfo ? (
            /* List View */
            <div className="space-y-4">
              {/* Selected Function Header */}
              <div className="bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 rounded-lg p-4 border border-blue-200 dark:border-blue-800">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">⚡</span>
                  <div className="flex-1 min-w-0">
                    <h4 className="text-lg font-semibold text-slate-900 dark:text-white">
                      {selectedInfo.name}
                    </h4>
                    <p className="text-sm text-slate-600 dark:text-slate-400 font-mono truncate">
                      {getFileIcon(selectedInfo.file)} {selectedInfo.file}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <span className="text-xs px-2 py-1 bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300 rounded">
                      ↗{selectedInfo.calls_count} calls
                    </span>
                    <span className="text-xs px-2 py-1 bg-sky-100 dark:bg-sky-900/40 text-sky-700 dark:text-sky-300 rounded">
                      ↙{selectedInfo.called_by_count} callers
                    </span>
                  </div>
                </div>
              </div>

              {/* Call Relationships */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-4">
                  <h5 className="text-sm font-semibold text-slate-800 dark:text-slate-200 mb-3 flex items-center gap-2">
                    <span className="text-green-500">↗</span>
                    Calls ({edgeCount(selectedDetail?.calls, selectedInfo.calls_count)})
                  </h5>
                  {renderEdgeList(selectedDetail?.calls, 'No outgoing calls')}
                </div>

                <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-4">
                  <h5 className="text-sm font-semibold text-slate-800 dark:text-slate-200 mb-3 flex items-center gap-2">
                    <span className="text-sky-500">↙</span>
                    Called By ({edgeCount(selectedDetail?.called_by, selectedInfo.called_by_count)})
                  </h5>
                  {renderEdgeList(selectedDetail?.called_by, 'Not called by any function')}
                </div>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center h-[700px] bg-slate-50 dark:bg-slate-700/50 rounded-lg border border-slate-200 dark:border-slate-600">
              <div className="text-center">
                <div className="text-5xl mb-4">👈</div>
                <p className="text-lg text-slate-600 dark:text-slate-400">
                  Select a function to see its call relationships
                </p>
                <p className="text-sm text-slate-500 dark:text-slate-500 mt-2">
                  Select a function from the list
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Legend & Controls Overlay */}
      <div className="absolute bottom-4 right-4 flex flex-col gap-3">
        {/* Full Stack Toggle */}
        <div className="bg-white/90 dark:bg-slate-800/90 backdrop-blur shadow-lg rounded-xl p-3 border border-slate-200 dark:border-slate-700">
           <label className="flex items-center gap-3 cursor-pointer group">
              <div className="relative inline-flex items-center">
                <input 
                  type="checkbox" 
                  checked={fullStackMode} 
                  onChange={() => setFullStackMode(!fullStackMode)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer dark:bg-slate-700 peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-blue-600"></div>
              </div>
              <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                Full-stack Mode
              </span>
           </label>
           <p className="text-[10px] text-slate-500 mt-1">Trace: UI ↘ API ↘ Middleware ↘ DB</p>
        </div>

        {/* Legend */}
        <div className="bg-white/95 dark:bg-slate-800/95 backdrop-blur shadow-xl rounded-xl p-3 border border-slate-200 dark:border-slate-700 w-56">
          <h5 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2 flex justify-between items-center border-b border-slate-100 dark:border-slate-700 pb-1">
            <span>Execution Flow</span>
            <span className="text-blue-500">START ↘</span>
          </h5>
          
          <div className="grid grid-cols-2 gap-x-2 gap-y-1.5">
            <div className="flex items-center gap-1.5">
              <div className="w-3.5 h-3.5 rounded bg-[#f59e0b] flex items-center justify-center text-[9px] text-white font-bold">A</div>
              <span className="text-[10px] text-slate-600 dark:text-slate-300 truncate">API</span>
            </div>
            
            <div className="flex items-center gap-1.5">
              <div className="w-3.5 h-3.5 rounded bg-[#ec4899] flex items-center justify-center text-[9px] text-white font-bold">M</div>
              <span className="text-[10px] text-slate-600 dark:text-slate-300 truncate">Middleware</span>
            </div>

            <div className="flex items-center gap-1.5">
              <div className="w-3.5 h-3.5 rounded bg-[#ef4444] flex items-center justify-center text-[9px] text-white font-bold">C</div>
              <span className="text-[10px] text-slate-600 dark:text-slate-300 truncate">Controller</span>
            </div>
            
            <div className="flex items-center gap-1.5">
              <div className="w-3.5 h-3.5 rounded bg-[#8b5cf6] flex items-center justify-center text-[9px] text-white font-bold">S</div>
              <span className="text-[10px] text-slate-600 dark:text-slate-300 truncate">Service</span>
            </div>
            
            <div className="flex items-center gap-1.5">
              <div className="w-3.5 h-3.5 rounded bg-[#10b981] flex items-center justify-center text-[9px] text-white font-bold">D</div>
              <span className="text-[10px] text-slate-600 dark:text-slate-300 truncate">Database</span>
            </div>
            
            <div className="flex items-center gap-1.5">
              <span className="w-3.5 h-3.5 rounded bg-[#3b82f6] border border-white"></span>
              <span className="text-[10px] text-slate-600 dark:text-slate-300">Selected</span>
            </div>
          </div>

          <div className="mt-2 border-t border-slate-100 dark:border-slate-700 pt-2 grid grid-cols-1 gap-1">
             <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-3 border-t border-dashed border-slate-400"></span>
                  <span className="text-[9px] text-slate-500">Network</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-3 border-t border-dotted border-slate-500"></span>
                  <span className="text-[9px] text-slate-500">DB Op</span>
                </div>
             </div>
             <div className="text-[8px] text-blue-500 font-bold text-right">↘ END</div>
          </div>
        </div>
      </div>
    </div>
  );
}
