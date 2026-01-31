import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import * as d3 from 'd3';

interface CallGraphNode {
  name: string;
  file: string;
  calls: string[];
  called_by: string[];
  language: string;
}

interface CallGraphProps {
  callGraph: { [key: string]: CallGraphNode };
  files: { [key: string]: any };
}

interface GraphNode {
  id: string;
  label: string;
  file: string;
  fileShort: string;
  isSelected: boolean;
  isCaller: boolean;    // Calls the selected function
  isCallee: boolean;    // Called by the selected function
  callsCount: number;
  calledByCount: number;
  language: string;
  x?: number;
  y?: number;
  fx?: number | null;
  fy?: number | null;
}

interface GraphLink {
  source: string | GraphNode;
  target: string | GraphNode;
}

export default function CallGraph({ callGraph }: CallGraphProps) {
  const [selectedFunction, setSelectedFunction] = useState<string | null>(null);
  const [expandedFunctions, setExpandedFunctions] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState('');
  const [displayMode, setDisplayMode] = useState<'graph' | 'list'>('graph');
  const [graphMode, setGraphMode] = useState<'all' | 'selected'>('all');
  const [graphDepth, setGraphDepth] = useState(2);
  const [groupByFile, setGroupByFile] = useState(true);
  const svgRef = useRef<SVGSVGElement>(null);

  // Get list of all functions
  const functionList = useMemo(() => {
    return Object.keys(callGraph || {}).sort((a, b) => {
      const fileA = callGraph[a]?.file || '';
      const fileB = callGraph[b]?.file || '';
      if (fileA !== fileB) return fileA.localeCompare(fileB);
      return a.localeCompare(b);
    });
  }, [callGraph]);

  // Group functions by file
  const functionsByFile = useMemo(() => {
    const grouped: { [file: string]: string[] } = {};
    functionList.forEach(funcId => {
      const file = callGraph[funcId]?.file || '(unknown)';
      if (!grouped[file]) grouped[file] = [];
      grouped[file].push(funcId);
    });
    return grouped;
  }, [functionList, callGraph]);

  // Filter functions based on search
  const filteredFunctions = useMemo(() => {
    if (!searchQuery) return functionList;
    const query = searchQuery.toLowerCase();
    return functionList.filter(f => {
      const node = callGraph[f];
      return f.toLowerCase().includes(query) ||
             node?.name.toLowerCase().includes(query) ||
             node?.file.toLowerCase().includes(query);
    });
  }, [functionList, searchQuery, callGraph]);

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
        newSet.add(funcId);
        return newSet;
      });
      setSelectedFunction(funcId);
    } else {
      setSelectedFunction(funcId);
    }
  }, [graphMode]);

  // Get function info for selected function
  const selectedInfo = useMemo(() => {
    if (!selectedFunction) return null;
    return callGraph[selectedFunction] || null;
  }, [selectedFunction, callGraph]);

  // Helper functions
  const getFileName = (path: string) => path.split('/').pop() || path;
  const getFuncName = (funcId: string) => funcId.split('::').pop() || funcId;

  const getFileIcon = (file: string) => {
    const ext = file.split('.').pop()?.toLowerCase() || '';
    if (['ts', 'tsx'].includes(ext)) return '🔷';
    if (['js', 'jsx'].includes(ext)) return '🟨';
    if (ext === 'py') return '🐍';
    if (ext === 'java') return '☕';
    if (ext === 'go') return '🔵';
    return '📄';
  };

  // Color nodes by file directory
  const getNodeColor = useCallback((node: GraphNode, allFiles: string[]) => {
    if (node.isSelected) return '#3b82f6'; // blue for selected
    if (node.isCallee) return '#22c55e';   // green for callees (functions we call)
    if (node.isCaller) return '#a855f7';   // purple for callers (functions that call us)

    // Color by directory
    const dir = node.file.split('/').slice(0, -1).join('/') || '/';
    const colors = [
      '#64748b', '#ef4444', '#f59e0b', '#10b981', '#06b6d4',
      '#8b5cf6', '#ec4899', '#f97316', '#84cc16', '#14b8a6'
    ];
    const uniqueDirs = [...new Set(allFiles.map(f => f.split('/').slice(0, -1).join('/') || '/'))].sort();
    const dirIndex = uniqueDirs.indexOf(dir);
    return colors[dirIndex % colors.length];
  }, []);

  // Calculate statistics
  const stats = useMemo(() => {
    const funcs = Object.values(callGraph || {});
    const totalCalls = funcs.reduce((sum, f) => sum + f.calls.length, 0);
    const connectedFuncs = funcs.filter(f => f.calls.length > 0 || f.called_by.length > 0).length;

    // Find most called function
    let mostCalled = { id: '', count: 0 };
    funcs.forEach(f => {
      if (f.called_by.length > mostCalled.count) {
        const id = Object.entries(callGraph).find(([_, v]) => v === f)?.[0] || '';
        mostCalled = { id, count: f.called_by.length };
      }
    });

    return {
      totalFunctions: funcs.length,
      connectedFunctions: connectedFuncs,
      totalCalls,
      mostCalled: mostCalled.id ? `${getFuncName(mostCalled.id)} (${mostCalled.count})` : '-',
    };
  }, [callGraph]);

  // Build and render D3 graph
  useEffect(() => {
    if (!svgRef.current || displayMode !== 'graph') return;
    if (!callGraph || Object.keys(callGraph).length === 0) return;

    // Clear previous content
    d3.select(svgRef.current).selectAll('*').remove();

    try {

    const functionsToShow = new Set<string>();
    const linksData: Array<{ source: string; target: string }> = [];

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

        const calls = info.calls || [];
        const calledBy = info.called_by || [];

        if (calls.length > 0 || calledBy.length > 0) {
          functionsToShow.add(funcId);
          calls.forEach(callee => {
            if (connectionCount < maxConnections && callGraph[callee]) {
              functionsToShow.add(callee);
              linksData.push({ source: funcId, target: callee });
              connectionCount++;
            }
          });
        }
      });
    } else if (selectedFunction || expandedFunctions.size > 0) {
      // Show selected function and its connections up to depth
      const funcsToExpand = expandedFunctions.size > 0 ? expandedFunctions : new Set([selectedFunction!]);
      const addedLinks = new Set<string>();
      const visited = new Set<string>(); // Prevent infinite recursion

      const collectConnections = (funcId: string, depth: number, direction: 'calls' | 'calledBy') => {
        if (depth > graphDepth) return;
        if (visited.has(`${funcId}-${direction}-${depth}`)) return; // Prevent revisiting
        visited.add(`${funcId}-${direction}-${depth}`);

        functionsToShow.add(funcId);

        const info = callGraph[funcId];
        if (!info) return;

        if (direction === 'calls') {
          (info.calls || []).forEach(callee => {
            // Only add link if callee exists in callGraph
            if (!callGraph[callee]) return;

            const linkKey = `${funcId}->${callee}`;
            if (!addedLinks.has(linkKey)) {
              addedLinks.add(linkKey);
              linksData.push({ source: funcId, target: callee });
            }
            if (!functionsToShow.has(callee)) {
              collectConnections(callee, depth + 1, 'calls');
            }
          });
        } else {
          (info.called_by || []).forEach(caller => {
            // Only add link if caller exists in callGraph
            if (!callGraph[caller]) return;

            const linkKey = `${caller}->${funcId}`;
            if (!addedLinks.has(linkKey)) {
              addedLinks.add(linkKey);
              linksData.push({ source: caller, target: funcId });
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

    // Get all files for color assignment
    const allFiles = [...new Set(validFunctions.map(f => callGraph[f]?.file || ''))];

    // Create a set of valid function IDs for quick lookup
    const validFunctionSet = new Set(validFunctions);

    // Create nodes array
    const nodes: GraphNode[] = validFunctions.map(funcId => {
      const info = callGraph[funcId];
      if (!info) return null;

      const calls = info.calls || [];
      const calledBy = info.called_by || [];
      const selectedInfo = selectedFunction ? callGraph[selectedFunction] : null;

      const isCallee = selectedInfo ? (selectedInfo.calls || []).includes(funcId) : false;
      const isCaller = selectedInfo ? (selectedInfo.called_by || []).includes(funcId) : false;

      return {
        id: funcId,
        label: info.name || funcId.split('::').pop() || funcId,
        file: info.file || '',
        fileShort: getFileName(info.file || ''),
        isSelected: funcId === selectedFunction,
        isCaller,
        isCallee,
        callsCount: calls.length,
        calledByCount: calledBy.length,
        language: info.language || 'Unknown',
      };
    }).filter((n): n is GraphNode => n !== null);

    // Create links array - only include links where both source and target exist
    const links: GraphLink[] = linksData
      .filter(l => validFunctionSet.has(l.source) && validFunctionSet.has(l.target))
      .map(l => ({ source: l.source, target: l.target }));

    // Setup SVG
    const svg = d3.select(svgRef.current);
    const width = svgRef.current.clientWidth || 800;
    const height = 600;

    svg.attr('viewBox', `0 0 ${width} ${height}`);

    // Add zoom behavior
    const container = svg.append('g');
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        container.attr('transform', event.transform);
      });
    svg.call(zoom);

    // Arrow marker
    svg.append('defs').append('marker')
      .attr('id', 'callgraph-arrow')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 20)
      .attr('refY', 0)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('fill', '#94a3b8')
      .attr('d', 'M0,-5L10,0L0,5');

    // Create simulation
    const simulation = d3.forceSimulation(nodes as any)
      .force('link', d3.forceLink(links)
        .id((d: any) => d.id)
        .distance(100))
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(35));

    // Draw links
    const link = container.append('g')
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('stroke', (d: any) => {
        if (selectedFunction) {
          const sourceId = typeof d.source === 'string' ? d.source : d.source.id;
          const targetId = typeof d.target === 'string' ? d.target : d.target.id;
          if (sourceId === selectedFunction) return '#22c55e'; // calls
          if (targetId === selectedFunction) return '#a855f7'; // called by
        }
        return '#94a3b8';
      })
      .attr('stroke-width', 2)
      .attr('stroke-opacity', (d: any) => {
        if (graphMode === 'all' && selectedFunction) {
          const sourceId = typeof d.source === 'string' ? d.source : d.source.id;
          const targetId = typeof d.target === 'string' ? d.target : d.target.id;
          if (!connectedToSelected.has(sourceId) && !connectedToSelected.has(targetId)) {
            return 0.2;
          }
        }
        return 0.8;
      })
      .attr('marker-end', 'url(#callgraph-arrow)');

    // Draw nodes
    let isDragging = false;
    const node = container.append('g')
      .selectAll('g')
      .data(nodes)
      .join('g')
      .attr('cursor', 'pointer')
      .call(d3.drag<SVGGElement, GraphNode>()
        .on('start', (event, d: any) => {
          isDragging = false;
          if (!event.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on('drag', (event, d: any) => {
          isDragging = true;
          d.fx = event.x;
          d.fy = event.y;
        })
        .on('end', (event, d: any) => {
          if (!event.active) simulation.alphaTarget(0);
          d.fx = null;
          d.fy = null;
          setTimeout(() => { isDragging = false; }, 100);
        }) as any)
      .on('click', (_, d) => {
        if (!isDragging) {
          handleNodeClick(d.id);
        }
      });

    // Node circles
    node.append('circle')
      .attr('r', (d: GraphNode) => d.isSelected ? 12 : 8)
      .attr('fill', (d: GraphNode) => getNodeColor(d, allFiles))
      .attr('stroke', (d: GraphNode) => d.isSelected ? '#1d4ed8' : 'white')
      .attr('stroke-width', (d: GraphNode) => d.isSelected ? 3 : 2)
      .attr('opacity', (d: GraphNode) => {
        if (graphMode === 'all' && selectedFunction && !connectedToSelected.has(d.id)) {
          return 0.3;
        }
        return 1;
      });

    // Node labels
    node.append('text')
      .text((d: GraphNode) => d.label)
      .attr('x', 12)
      .attr('y', 4)
      .attr('font-size', '11px')
      .attr('fill', '#e2e8f0')
      .attr('opacity', (d: GraphNode) => {
        if (graphMode === 'all' && selectedFunction && !connectedToSelected.has(d.id)) {
          return 0.3;
        }
        return 1;
      });

    // Tooltips
    node.append('title')
      .text((d: GraphNode) => `${d.label}\nFile: ${d.file}\nCalls: ${d.callsCount} | Called by: ${d.calledByCount}`);

    // Update positions on tick
    simulation.on('tick', () => {
      link
        .attr('x1', (d: any) => d.source.x)
        .attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x)
        .attr('y2', (d: any) => d.target.y);

      node.attr('transform', (d: any) => `translate(${d.x},${d.y})`);
    });

    return () => {
      simulation.stop();
    };
    } catch (error) {
      console.error('Error rendering call graph:', error);
      // Clear SVG on error to prevent broken state
      if (svgRef.current) {
        d3.select(svgRef.current).selectAll('*').remove();
      }
    }
  }, [callGraph, displayMode, graphMode, selectedFunction, expandedFunctions, graphDepth, getNodeColor, handleNodeClick]);

  // Empty state
  if (!callGraph || Object.keys(callGraph).length === 0) {
    return (
      <div className="text-center py-12 bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
        <div className="text-6xl mb-4">🔀</div>
        <p className="text-lg font-medium text-slate-700 dark:text-slate-300 mb-2">
          No call graph data available
        </p>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Analyze a repository with functions to see call relationships
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex justify-between items-start flex-wrap gap-4">
        <div>
          <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
            🔀 Call Graph
          </h3>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Function-to-function call relationships across the codebase
          </p>
        </div>

        {/* Controls */}
        <div className="flex gap-2 flex-wrap">
          <select
            value={displayMode}
            onChange={(e) => setDisplayMode(e.target.value as 'graph' | 'list')}
            className="px-3 py-1.5 text-sm bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-lg"
          >
            <option value="graph">Graph View</option>
            <option value="list">List View</option>
          </select>

          {displayMode === 'graph' && (
            <>
              <select
                value={graphMode}
                onChange={(e) => setGraphMode(e.target.value as 'all' | 'selected')}
                className="px-3 py-1.5 text-sm bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-lg"
              >
                <option value="all">All Connected</option>
                <option value="selected">Selected Function</option>
              </select>

              {graphMode === 'selected' && (
                <select
                  value={graphDepth}
                  onChange={(e) => setGraphDepth(Number(e.target.value))}
                  className="px-3 py-1.5 text-sm bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-lg"
                >
                  <option value={1}>Depth: 1</option>
                  <option value={2}>Depth: 2</option>
                  <option value={3}>Depth: 3</option>
                  <option value={4}>Depth: 4</option>
                  <option value={5}>Depth: 5</option>
                </select>
              )}

              {selectedFunction && (
                <button
                  onClick={handleClearSelection}
                  className="px-3 py-1.5 text-sm bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 border border-red-300 dark:border-red-700 rounded-lg hover:bg-red-200 dark:hover:bg-red-900/50 transition-colors flex items-center gap-1"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                  Clear Selection
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-3 border border-slate-200 dark:border-slate-600">
          <span className="text-xs text-slate-500 dark:text-slate-400">Total Functions</span>
          <p className="text-lg font-bold text-slate-900 dark:text-white">{stats.totalFunctions}</p>
        </div>
        <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-3 border border-slate-200 dark:border-slate-600">
          <span className="text-xs text-slate-500 dark:text-slate-400">Connected</span>
          <p className="text-lg font-bold text-slate-900 dark:text-white">{stats.connectedFunctions}</p>
        </div>
        <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-3 border border-slate-200 dark:border-slate-600">
          <span className="text-xs text-slate-500 dark:text-slate-400">Total Calls</span>
          <p className="text-lg font-bold text-slate-900 dark:text-white">{stats.totalCalls}</p>
        </div>
        <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-3 border border-slate-200 dark:border-slate-600">
          <span className="text-xs text-slate-500 dark:text-slate-400">Most Called</span>
          <p className="text-sm font-bold text-slate-900 dark:text-white truncate">{stats.mostCalled}</p>
        </div>
      </div>

      {/* Main content */}
      <div className="flex gap-4">
        {/* Sidebar - Function list */}
        <div className="w-72 flex-shrink-0">
          <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-3">
            <input
              type="text"
              placeholder="Search functions..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-lg mb-3"
            />

            <div className="flex items-center justify-between gap-2 mb-3">
              <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
                <input
                  type="checkbox"
                  checked={groupByFile}
                  onChange={(e) => setGroupByFile(e.target.checked)}
                  className="rounded"
                />
                Group by file
              </label>
              {selectedFunction && (
                <button
                  onClick={handleClearSelection}
                  className="text-xs px-2 py-1 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 rounded transition-colors"
                >
                  Clear
                </button>
              )}
            </div>

            <div className="max-h-[500px] overflow-y-auto space-y-1">
              {groupByFile ? (
                Object.entries(functionsByFile)
                  .filter(([file]) => filteredFunctions.some(f => callGraph[f]?.file === file))
                  .map(([file, funcs]) => (
                    <div key={file} className="mb-2">
                      <div className="text-xs font-medium text-slate-500 dark:text-slate-400 px-2 py-1 truncate">
                        {getFileIcon(file)} {getFileName(file)}
                      </div>
                      {funcs
                        .filter(f => filteredFunctions.includes(f) && callGraph[f])
                        .map(funcId => {
                          const info = callGraph[funcId];
                          if (!info) return null;
                          const isSelected = funcId === selectedFunction;
                          return (
                            <button
                              key={funcId}
                              onClick={() => handleFunctionSelect(funcId)}
                              className={`w-full text-left px-3 py-1.5 text-sm rounded transition-colors ${
                                isSelected
                                  ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200'
                                  : 'hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300'
                              }`}
                            >
                              <span className="truncate block">{info.name}</span>
                              <span className="text-xs text-slate-400">
                                {(info.calls || []).length}↗ {(info.called_by || []).length}↙
                              </span>
                            </button>
                          );
                        })}
                    </div>
                  ))
              ) : (
                filteredFunctions
                  .filter(funcId => callGraph[funcId])
                  .map(funcId => {
                    const info = callGraph[funcId];
                    if (!info) return null;
                    const isSelected = funcId === selectedFunction;
                    return (
                      <button
                        key={funcId}
                        onClick={() => handleFunctionSelect(funcId)}
                        className={`w-full text-left px-3 py-1.5 text-sm rounded transition-colors ${
                          isSelected
                            ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200'
                            : 'hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300'
                        }`}
                      >
                        <span className="truncate block">{info.name}</span>
                        <span className="text-xs text-slate-400 block truncate">
                          {getFileName(info.file || '')}
                        </span>
                      </button>
                    );
                  })
              )}
            </div>
          </div>
        </div>

        {/* Main view */}
        <div className="flex-1">
          {displayMode === 'graph' ? (
            <div className="bg-slate-900 rounded-lg border border-slate-700 overflow-hidden">
              <svg ref={svgRef} className="w-full" style={{ height: 600 }} />

              {/* Legend */}
              <div className="px-4 py-2 bg-slate-800 border-t border-slate-700 flex gap-4 flex-wrap text-xs">
                <span className="flex items-center gap-1">
                  <span className="w-3 h-3 rounded-full bg-blue-500"></span>
                  Selected
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-3 h-3 rounded-full bg-green-500"></span>
                  Calls (outgoing)
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-3 h-3 rounded-full bg-purple-500"></span>
                  Called by (incoming)
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-3 h-3 rounded-full bg-slate-500"></span>
                  Other
                </span>
              </div>
            </div>
          ) : (
            <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-4">
              {selectedFunction && selectedInfo ? (
                <div className="space-y-4">
                  <div className="pb-4 border-b border-slate-200 dark:border-slate-700">
                    <h4 className="text-lg font-semibold text-slate-900 dark:text-white">
                      {selectedInfo.name}
                    </h4>
                    <p className="text-sm text-slate-500 dark:text-slate-400">
                      {getFileIcon(selectedInfo.file)} {selectedInfo.file}
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <h5 className="text-sm font-medium text-green-600 dark:text-green-400 mb-2">
                        Calls ({selectedInfo.calls.length})
                      </h5>
                      <div className="space-y-1 max-h-64 overflow-y-auto">
                        {selectedInfo.calls.length > 0 ? (
                          selectedInfo.calls.map(calleeId => {
                            const callee = callGraph[calleeId];
                            return (
                              <button
                                key={calleeId}
                                onClick={() => handleFunctionSelect(calleeId)}
                                className="w-full text-left px-3 py-2 text-sm bg-slate-50 dark:bg-slate-700/50 rounded hover:bg-slate-100 dark:hover:bg-slate-700"
                              >
                                <span className="font-medium text-slate-900 dark:text-white">
                                  {callee?.name || getFuncName(calleeId)}
                                </span>
                                <span className="text-xs text-slate-500 dark:text-slate-400 block truncate">
                                  {callee?.file || ''}
                                </span>
                              </button>
                            );
                          })
                        ) : (
                          <p className="text-sm text-slate-400">No outgoing calls</p>
                        )}
                      </div>
                    </div>

                    <div>
                      <h5 className="text-sm font-medium text-purple-600 dark:text-purple-400 mb-2">
                        Called By ({selectedInfo.called_by.length})
                      </h5>
                      <div className="space-y-1 max-h-64 overflow-y-auto">
                        {selectedInfo.called_by.length > 0 ? (
                          selectedInfo.called_by.map(callerId => {
                            const caller = callGraph[callerId];
                            return (
                              <button
                                key={callerId}
                                onClick={() => handleFunctionSelect(callerId)}
                                className="w-full text-left px-3 py-2 text-sm bg-slate-50 dark:bg-slate-700/50 rounded hover:bg-slate-100 dark:hover:bg-slate-700"
                              >
                                <span className="font-medium text-slate-900 dark:text-white">
                                  {caller?.name || getFuncName(callerId)}
                                </span>
                                <span className="text-xs text-slate-500 dark:text-slate-400 block truncate">
                                  {caller?.file || ''}
                                </span>
                              </button>
                            );
                          })
                        ) : (
                          <p className="text-sm text-slate-400">Not called by any function</p>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-center py-8 text-slate-500 dark:text-slate-400">
                  Select a function from the sidebar to see its call relationships
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
