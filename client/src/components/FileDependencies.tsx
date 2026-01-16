import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import * as d3 from 'd3';

interface FileDependency {
  imports: string[];
  resolved: string[];
  external: string[];
}

interface FileDependenciesProps {
  files: { [key: string]: any };
  fileDependencies: { [key: string]: FileDependency };
}

interface GraphNode {
  id: string;
  label: string;
  path: string;
  type: 'file' | 'external';
  isSelected: boolean;
  isExpanded?: boolean; // File has been expanded to show its connections
  isDirectDep: boolean;
  isDirectUsedBy: boolean;
  isConnected?: boolean; // Connected to selected file (direct dep or used-by)
  hasCircular: boolean;
  depsCount: number;
  usedByCount: number;
  x?: number;
  y?: number;
  fx?: number | null;
  fy?: number | null;
}

interface GraphLink {
  source: string | GraphNode;
  target: string | GraphNode;
}

export default function FileDependencies({ files, fileDependencies }: FileDependenciesProps) {
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [expandedFiles, setExpandedFiles] = useState<Set<string>>(new Set()); // Track expanded files in 'selected' mode
  const [searchQuery, setSearchQuery] = useState('');
  const [displayMode, setDisplayMode] = useState<'list' | 'graph'>('graph');
  const [graphMode, setGraphMode] = useState<'all' | 'selected'>('all');
  const [graphDepth, setGraphDepth] = useState(2);
  const [showExternal, setShowExternal] = useState(false);
  const svgRef = useRef<SVGSVGElement>(null);

  // When selected file changes from sidebar, reset expanded files
  const handleFileSelect = useCallback((file: string) => {
    setSelectedFile(file);
    setExpandedFiles(new Set([file]));
  }, []);

  // When clicking a node in 'selected' mode, expand to show its connections too
  const handleNodeClick = useCallback((fileId: string) => {
    if (graphMode === 'selected') {
      // Add this file to expanded files (keeping existing ones)
      setExpandedFiles(prev => {
        const newSet = new Set(prev);
        newSet.add(fileId);
        return newSet;
      });
      setSelectedFile(fileId);
    } else {
      // In 'all' mode, just highlight the file
      setSelectedFile(fileId);
    }
  }, [graphMode]);

  // Normalize path helper
  const normalizePath = useCallback((path: string) => path.replace(/\\/g, '/'), []);

  // Get list of files for selection
  const fileList = useMemo(() => {
    return Object.keys(files || {}).map(normalizePath).sort();
  }, [files, normalizePath]);

  // Filter files based on search
  const filteredFiles = useMemo(() => {
    if (!searchQuery) return fileList;
    const query = searchQuery.toLowerCase();
    return fileList.filter(f => f.toLowerCase().includes(query));
  }, [fileList, searchQuery]);

  // Create normalized dependency map
  const normalizedDeps = useMemo(() => {
    if (!fileDependencies) return {};
    const normalized: { [key: string]: FileDependency } = {};
    Object.entries(fileDependencies).forEach(([file, deps]) => {
      normalized[normalizePath(file)] = {
        imports: deps.imports || [],
        resolved: (deps.resolved || []).map(normalizePath),
        external: deps.external || [],
      };
    });
    return normalized;
  }, [fileDependencies, normalizePath]);

  // Calculate reverse dependencies
  const reverseDependencies = useMemo(() => {
    const reverse: { [key: string]: string[] } = {};
    Object.entries(normalizedDeps).forEach(([file, deps]) => {
      deps.resolved?.forEach(dep => {
        if (!reverse[dep]) reverse[dep] = [];
        if (!reverse[dep].includes(file)) reverse[dep].push(file);
      });
    });
    return reverse;
  }, [normalizedDeps]);

  // Detect circular dependencies
  const circularFiles = useMemo(() => {
    const circular = new Set<string>();
    const visited = new Set<string>();
    const recursionStack = new Set<string>();

    const detectCycle = (file: string, path: string[]): boolean => {
      if (recursionStack.has(file)) {
        path.slice(path.indexOf(file)).forEach(f => circular.add(f));
        circular.add(file);
        return true;
      }
      if (visited.has(file)) return false;

      visited.add(file);
      recursionStack.add(file);

      for (const dep of normalizedDeps[file]?.resolved || []) {
        if (detectCycle(dep, [...path, file])) return true;
      }

      recursionStack.delete(file);
      return false;
    };

    Object.keys(normalizedDeps).forEach(file => {
      if (!visited.has(file)) detectCycle(file, []);
    });

    return circular;
  }, [normalizedDeps]);

  // Get dependencies and used-by for selected file
  const selectedDeps = useMemo(() => {
    if (!selectedFile) return null;
    return normalizedDeps[selectedFile] || null;
  }, [selectedFile, normalizedDeps]);

  const usedBy = useMemo(() => {
    if (!selectedFile) return [];
    return reverseDependencies[selectedFile] || [];
  }, [selectedFile, reverseDependencies]);

  // Helper functions
  const getFileIcon = (path: string) => {
    const ext = path.split('.').pop()?.toLowerCase() || '';
    if (['ts', 'tsx'].includes(ext)) return '🔷';
    if (['js', 'jsx'].includes(ext)) return '🟨';
    if (ext === 'py') return '🐍';
    if (ext === 'java') return '☕';
    if (ext === 'go') return '🔵';
    if (ext === 'rs') return '🦀';
    if (ext === 'vue') return '💚';
    return '📄';
  };

  const getFileName = (path: string) => path.split('/').pop() || path;
  const getFilePath = (path: string) => {
    const parts = path.split('/');
    return parts.slice(0, -1).join('/') || '/';
  };

  // Get node color based on state
  const getNodeColor = (node: GraphNode) => {
    if (node.type === 'external') return '#8b5cf6'; // purple for external
    if (node.isSelected) return '#3b82f6'; // blue for selected
    if (node.hasCircular) return '#ef4444'; // red for circular
    if (node.isExpanded && !node.isSelected) return '#0ea5e9'; // cyan for expanded (but not selected)
    if (node.isDirectDep) return '#22c55e'; // green for direct dep
    if (node.isDirectUsedBy) return '#a855f7'; // purple for used by
    return '#64748b'; // gray for other
  };

  // Build and render D3 graph
  useEffect(() => {
    if (!svgRef.current || displayMode !== 'graph') return;

    // Clear previous content
    d3.select(svgRef.current).selectAll('*').remove();

    const filesToShow = new Set<string>();
    const linksData: Array<{ source: string; target: string }> = [];
    const externalPackages = new Set<string>();

    // Track files connected to selected file (for highlighting in 'all' mode)
    const connectedToSelected = new Set<string>();
    if (selectedFile) {
      connectedToSelected.add(selectedFile);
      // Add direct dependencies
      (normalizedDeps[selectedFile]?.resolved || []).forEach(dep => connectedToSelected.add(dep));
      // Add files that import the selected file
      (reverseDependencies[selectedFile] || []).forEach(parent => connectedToSelected.add(parent));
    }

    if (graphMode === 'all') {
      // Show ALL files that have connections
      Object.entries(normalizedDeps).forEach(([file, deps]) => {
        if (deps.resolved.length > 0 || reverseDependencies[file]?.length > 0) {
          filesToShow.add(file);
          deps.resolved.forEach(dep => {
            filesToShow.add(dep);
            linksData.push({ source: file, target: dep });
          });
        }
      });
    } else if (selectedFile || expandedFiles.size > 0) {
      // Show dependencies for all expanded files (allows exploring multiple nodes)
      const filesToExpand = expandedFiles.size > 0 ? expandedFiles : new Set([selectedFile!]);

      // Track which links we've already added to avoid duplicates
      const addedLinks = new Set<string>();

      const collectDeps = (file: string, depth: number, direction: 'deps' | 'usedBy', isExpandedFile: boolean) => {
        if (depth > graphDepth) return;

        // Always add the file
        filesToShow.add(file);

        if (direction === 'deps') {
          const deps = normalizedDeps[file]?.resolved || [];
          deps.forEach(dep => {
            const linkKey = `${file}->${dep}`;
            if (!addedLinks.has(linkKey)) {
              addedLinks.add(linkKey);
              linksData.push({ source: file, target: dep });
            }
            if (!filesToShow.has(dep)) {
              collectDeps(dep, depth + 1, 'deps', false);
            }
          });

          // Show external packages for expanded files
          if (showExternal && isExpandedFile) {
            (normalizedDeps[file]?.external || []).forEach(ext => {
              externalPackages.add(ext);
            });
          }
        } else {
          const parents = reverseDependencies[file] || [];
          parents.forEach(parent => {
            const linkKey = `${parent}->${file}`;
            if (!addedLinks.has(linkKey)) {
              addedLinks.add(linkKey);
              linksData.push({ source: parent, target: file });
            }
            if (!filesToShow.has(parent)) {
              collectDeps(parent, depth + 1, 'usedBy', false);
            }
          });
        }
      };

      // Collect dependencies for ALL expanded files
      filesToExpand.forEach(file => {
        filesToShow.add(file);
        collectDeps(file, 0, 'deps', true);
        collectDeps(file, 0, 'usedBy', true);
      });
    }

    if (filesToShow.size === 0 && externalPackages.size === 0) return;

    // Create nodes array
    const nodes: GraphNode[] = Array.from(filesToShow).map(file => {
      const isDirectDep = selectedFile ? (normalizedDeps[selectedFile]?.resolved.includes(file) && file !== selectedFile) : false;
      const isDirectUsedBy = selectedFile ? (reverseDependencies[selectedFile]?.includes(file) && file !== selectedFile) : false;
      const isConnected = connectedToSelected.has(file);
      const isExpanded = expandedFiles.has(file);

      return {
        id: file,
        label: getFileName(file),
        path: getFilePath(file),
        type: 'file' as const,
        isSelected: file === selectedFile,
        isExpanded, // Track if this file has been expanded
        isDirectDep,
        isDirectUsedBy,
        isConnected, // New property to track if connected to selected file
        hasCircular: circularFiles.has(file),
        depsCount: normalizedDeps[file]?.resolved.length || 0,
        usedByCount: reverseDependencies[file]?.length || 0,
      };
    });

    // Add external packages if showing
    if (graphMode === 'selected' && showExternal && selectedFile) {
      externalPackages.forEach(pkg => {
        nodes.push({
          id: `ext-${pkg}`,
          label: pkg,
          path: 'external',
          type: 'external',
          isSelected: false,
          isDirectDep: true,
          isDirectUsedBy: false,
          hasCircular: false,
          depsCount: 0,
          usedByCount: 0,
        });
        linksData.push({ source: selectedFile, target: `ext-${pkg}` });
      });
    }

    // Create links with node references
    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    const links: GraphLink[] = linksData
      .filter(l => nodeMap.has(l.source) && nodeMap.has(l.target))
      .map(l => ({
        source: l.source,
        target: l.target,
      }));

    // Set up SVG dimensions
    const width = 900;
    const height = 550;
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

    // Create arrow marker for links
    svg.append('defs').append('marker')
      .attr('id', 'arrowhead-file')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 25)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .append('svg:path')
      .attr('d', 'M 0,-5 L 10 ,0 L 0,5')
      .attr('fill', '#64748b');

    // Create circular arrow marker
    svg.select('defs').append('marker')
      .attr('id', 'arrowhead-circular')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 25)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .append('svg:path')
      .attr('d', 'M 0,-5 L 10 ,0 L 0,5')
      .attr('fill', '#ef4444');

    // Create selected arrow marker
    svg.select('defs').append('marker')
      .attr('id', 'arrowhead-selected')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 25)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .append('svg:path')
      .attr('d', 'M 0,-5 L 10 ,0 L 0,5')
      .attr('fill', '#3b82f6');

    // Create force simulation
    const simulation = d3.forceSimulation(nodes as any)
      .force('link', d3.forceLink(links).id((d: any) => d.id).distance(120))
      .force('charge', d3.forceManyBody().strength(-400))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(40));

    // Create link elements
    const link = container.append('g')
      .selectAll('line')
      .data(links)
      .enter()
      .append('line')
      .attr('stroke', (d: any) => {
        const sourceNode = typeof d.source === 'object' ? d.source : nodeMap.get(d.source);
        const targetNode = typeof d.target === 'object' ? d.target : nodeMap.get(d.target);
        if (sourceNode?.hasCircular && targetNode?.hasCircular) return '#ef4444';
        if (sourceNode?.isSelected || targetNode?.isSelected) return '#3b82f6';
        // Highlight links connected to selected file
        if (selectedFile && (sourceNode?.isConnected && targetNode?.isConnected)) return '#94a3b8';
        return '#64748b';
      })
      .attr('stroke-opacity', (d: any) => {
        const sourceNode = typeof d.source === 'object' ? d.source : nodeMap.get(d.source);
        const targetNode = typeof d.target === 'object' ? d.target : nodeMap.get(d.target);
        // In 'all' mode with selected file, dim links not connected to selected
        if (graphMode === 'all' && selectedFile) {
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
      .attr('marker-end', (d: any) => {
        const sourceNode = typeof d.source === 'object' ? d.source : nodeMap.get(d.source);
        const targetNode = typeof d.target === 'object' ? d.target : nodeMap.get(d.target);
        if (sourceNode?.hasCircular && targetNode?.hasCircular) return 'url(#arrowhead-circular)';
        if (sourceNode?.isSelected || targetNode?.isSelected) return 'url(#arrowhead-selected)';
        return 'url(#arrowhead-file)';
      });

    // Track if we're dragging to prevent click after drag
    let isDragging = false;

    // Create node elements
    const node = container.append('g')
      .selectAll('g')
      .data(nodes)
      .enter()
      .append('g')
      .style('cursor', 'pointer')
      .call(d3.drag<any, any>()
        .on('start', (event) => {
          isDragging = false;
          dragstarted(event);
        })
        .on('drag', (event) => {
          isDragging = true;
          dragged(event);
        })
        .on('end', dragended) as any)
      .on('click', (_event, d) => {
        // Only handle click if we weren't dragging
        if (!isDragging && d.type !== 'external') {
          handleNodeClick(d.id);
        }
      });

    // Add circles to nodes
    node.append('circle')
      .attr('r', (d) => d.type === 'external' ? 10 : (d.isSelected ? 14 : (d.isExpanded ? 13 : 12)))
      .attr('fill', (d) => getNodeColor(d))
      .attr('stroke', '#fff')
      .attr('stroke-width', 2)
      .attr('opacity', (d) => {
        // In 'all' mode with a selected file, dim non-connected nodes
        if (graphMode === 'all' && selectedFile && !d.isConnected) return 0.3;
        return 1;
      });

    // Add labels to nodes
    node.append('text')
      .text((d) => d.label.substring(0, 20))
      .attr('x', 18)
      .attr('y', 4)
      .attr('font-size', 11)
      .attr('fill', '#334155')
      .attr('class', 'dark:fill-slate-300')
      .attr('opacity', (d) => {
        // In 'all' mode with a selected file, dim non-connected labels
        if (graphMode === 'all' && selectedFile && !d.isConnected) return 0.3;
        return 1;
      });

    // Add tooltips
    node.append('title')
      .text((d) => `${d.id}\n${d.type === 'external' ? 'External Package' : `Deps: ${d.depsCount}, Used by: ${d.usedByCount}`}`);

    // Update positions on tick
    simulation.on('tick', () => {
      link
        .attr('x1', (d: any) => d.source.x)
        .attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x)
        .attr('y2', (d: any) => d.target.y);

      node.attr('transform', (d: any) => `translate(${d.x},${d.y})`);
    });

    // Drag functions
    function dragstarted(event: any) {
      if (!event.active) simulation.alphaTarget(0.3).restart();
      event.subject.fx = event.subject.x;
      event.subject.fy = event.subject.y;
    }

    function dragged(event: any) {
      event.subject.fx = event.x;
      event.subject.fy = event.y;
    }

    function dragended(event: any) {
      if (!event.active) simulation.alphaTarget(0);
      event.subject.fx = null;
      event.subject.fy = null;
    }

    return () => {
      simulation.stop();
    };
  }, [displayMode, graphMode, selectedFile, expandedFiles, graphDepth, showExternal, normalizedDeps, reverseDependencies, circularFiles, handleNodeClick]);

  // Statistics
  const stats = useMemo(() => ({
    totalFiles: fileList.length,
    filesWithDeps: Object.values(normalizedDeps).filter(d => d.resolved.length > 0).length,
    totalConnections: Object.values(normalizedDeps).reduce((sum, d) => sum + d.resolved.length, 0),
    externalPackages: new Set(Object.values(normalizedDeps).flatMap(d => d.external)).size,
    circularCount: circularFiles.size,
  }), [fileList, normalizedDeps, circularFiles]);

  if (!fileDependencies || Object.keys(fileDependencies).length === 0) {
    return (
      <div className="text-center py-12 bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
        <div className="text-6xl mb-4">🔗</div>
        <p className="text-lg font-medium text-slate-700 dark:text-slate-300 mb-2">
          No dependency data available
        </p>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Analyze a repository to see file dependencies
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header with Stats */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
            🔗 File Dependencies
          </h3>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Visualize how files depend on each other
          </p>
        </div>

        {/* Quick Stats */}
        <div className="flex gap-3">
          <div className="text-center px-3 py-1 bg-blue-50 dark:bg-blue-900/30 rounded">
            <p className="text-lg font-bold text-blue-600 dark:text-blue-400">{stats.totalFiles}</p>
            <p className="text-[10px] text-slate-500">Files</p>
          </div>
          <div className="text-center px-3 py-1 bg-green-50 dark:bg-green-900/30 rounded">
            <p className="text-lg font-bold text-green-600 dark:text-green-400">{stats.totalConnections}</p>
            <p className="text-[10px] text-slate-500">Links</p>
          </div>
          <div className="text-center px-3 py-1 bg-purple-50 dark:bg-purple-900/30 rounded">
            <p className="text-lg font-bold text-purple-600 dark:text-purple-400">{stats.externalPackages}</p>
            <p className="text-[10px] text-slate-500">Packages</p>
          </div>
          {stats.circularCount > 0 && (
            <div className="text-center px-3 py-1 bg-red-50 dark:bg-red-900/30 rounded">
              <p className="text-lg font-bold text-red-600 dark:text-red-400">{stats.circularCount}</p>
              <p className="text-[10px] text-slate-500">Circular</p>
            </div>
          )}
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
            {/* Graph Mode: All vs Selected */}
            <div className="flex gap-1 bg-slate-100 dark:bg-slate-700 p-1 rounded-lg">
              <button
                onClick={() => setGraphMode('all')}
                className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                  graphMode === 'all'
                    ? 'bg-white dark:bg-slate-600 text-slate-900 dark:text-white shadow'
                    : 'text-slate-600 dark:text-slate-400'
                }`}
              >
                🌐 All Files
              </button>
              <button
                onClick={() => setGraphMode('selected')}
                className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                  graphMode === 'selected'
                    ? 'bg-white dark:bg-slate-600 text-slate-900 dark:text-white shadow'
                    : 'text-slate-600 dark:text-slate-400'
                }`}
              >
                🎯 Selected File
              </button>
            </div>

            {graphMode === 'selected' && (
              <>
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

                <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
                  <input
                    type="checkbox"
                    checked={showExternal}
                    onChange={(e) => setShowExternal(e.target.checked)}
                    className="rounded"
                  />
                  Show packages
                </label>
              </>
            )}
          </>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* File Selection Panel */}
        <div className="lg:col-span-1">
          <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg border border-slate-200 dark:border-slate-600 p-3">
            <h4 className="text-sm font-semibold text-slate-800 dark:text-slate-200 mb-2">
              Select File ({filteredFiles.length})
            </h4>

            <div className="relative mb-2">
              <input
                type="text"
                placeholder="Search files..."
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

            <div className="max-h-[500px] overflow-y-auto space-y-1">
              {filteredFiles.map((file) => {
                const isSelected = selectedFile === file;
                const deps = normalizedDeps[file];
                const depCount = deps?.resolved?.length || 0;
                const usedByCount = reverseDependencies[file]?.length || 0;
                const hasCircular = circularFiles.has(file);

                return (
                  <button
                    key={file}
                    onClick={() => handleFileSelect(file)}
                    className={`w-full text-left p-2 rounded transition-all ${
                      isSelected
                        ? 'bg-blue-100 dark:bg-blue-900/40 border border-blue-300 dark:border-blue-700'
                        : hasCircular
                        ? 'bg-red-50 dark:bg-red-900/20 hover:bg-red-100 border border-transparent'
                        : 'bg-white dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 border border-transparent'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-sm">{getFileIcon(file)}</span>
                      <span className="text-xs font-medium text-slate-900 dark:text-white truncate flex-1">
                        {getFileName(file)}
                      </span>
                      {hasCircular && <span className="text-red-500 text-xs">⚠️</span>}
                    </div>
                    <div className="flex items-center gap-2 mt-0.5 ml-6">
                      <span className="text-[10px] text-slate-500 truncate flex-1">
                        {getFilePath(file) || '/'}
                      </span>
                      <div className="flex gap-1">
                        {depCount > 0 && (
                          <span className="text-[9px] px-1 bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 rounded">
                            →{depCount}
                          </span>
                        )}
                        {usedByCount > 0 && (
                          <span className="text-[9px] px-1 bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300 rounded">
                            ←{usedByCount}
                          </span>
                        )}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Main Content Area */}
        <div className="lg:col-span-3">
          {displayMode === 'graph' ? (
            /* Graph View - D3 force-directed graph */
            (graphMode === 'all' || selectedFile) ? (
              <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-4">
                <div className="mb-4 flex items-start justify-between">
                  <div>
                    <h4 className="text-md font-semibold text-slate-900 dark:text-white mb-2">
                      {graphMode === 'all'
                        ? (selectedFile ? `Connections for ${getFileName(selectedFile)}` : 'All File Dependencies')
                        : expandedFiles.size > 1
                        ? `Exploring ${expandedFiles.size} files (selected: ${getFileName(selectedFile || '')})`
                        : `Dependencies for ${getFileName(selectedFile || '')}`}
                    </h4>
                    <p className="text-sm text-slate-600 dark:text-slate-400">
                      {graphMode === 'all' && selectedFile
                        ? 'Showing connected files highlighted. Click another node or clear selection.'
                        : graphMode === 'selected' && selectedFile
                        ? 'Click any node to expand and show its connections. Drag to reposition, scroll to zoom.'
                        : 'Interactive visualization. Drag nodes to explore connections. Scroll to zoom.'}
                    </p>
                  </div>
                  {selectedFile && (
                    <button
                      onClick={() => {
                        setSelectedFile(null);
                        setExpandedFiles(new Set());
                      }}
                      className="px-3 py-1.5 text-xs font-medium bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-300 rounded-lg transition-colors"
                    >
                      ✕ Clear Selection
                    </button>
                  )}
                </div>
                <svg ref={svgRef} className="w-full h-[550px] bg-slate-50 dark:bg-slate-900 rounded-lg" />
              </div>
            ) : (
              <div className="flex items-center justify-center h-[550px] bg-slate-50 dark:bg-slate-700/50 rounded-lg border border-slate-200 dark:border-slate-600">
                <div className="text-center">
                  <div className="text-5xl mb-4">👈</div>
                  <p className="text-lg text-slate-600 dark:text-slate-400">
                    Select a file to view its dependencies
                  </p>
                  <p className="text-sm text-slate-500 mt-2">
                    Or switch to "All Files" mode to see the complete graph
                  </p>
                </div>
              </div>
            )
          ) : selectedFile ? (
            /* List View */
            <div className="space-y-4">
              {/* Selected File Header */}
              <div className="bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 rounded-lg p-4 border border-blue-200 dark:border-blue-800">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">{getFileIcon(selectedFile)}</span>
                  <div className="flex-1 min-w-0">
                    <h4 className="text-lg font-semibold text-slate-900 dark:text-white">
                      {getFileName(selectedFile)}
                    </h4>
                    <p className="text-sm text-slate-600 dark:text-slate-400 font-mono truncate">
                      {selectedFile}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <span className="text-xs px-2 py-1 bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 rounded">
                      →{selectedDeps?.resolved?.length || 0} deps
                    </span>
                    <span className="text-xs px-2 py-1 bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300 rounded">
                      ←{usedBy.length} importers
                    </span>
                  </div>
                </div>
              </div>

              {/* Dependencies */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-4">
                  <h5 className="text-sm font-semibold text-slate-800 dark:text-slate-200 mb-3 flex items-center gap-2">
                    <span className="text-blue-500">📁</span>
                    Depends On ({selectedDeps?.resolved?.length || 0})
                  </h5>
                  {selectedDeps?.resolved && selectedDeps.resolved.length > 0 ? (
                    <div className="space-y-1 max-h-[200px] overflow-y-auto">
                      {selectedDeps.resolved.map((dep, idx) => (
                        <button
                          key={idx}
                          onClick={() => setSelectedFile(dep)}
                          className="w-full flex items-center gap-2 p-2 bg-slate-50 dark:bg-slate-700/50 hover:bg-slate-100 dark:hover:bg-slate-700 rounded text-left"
                        >
                          <span>{getFileIcon(dep)}</span>
                          <span className="text-sm text-slate-700 dark:text-slate-300 truncate">{getFileName(dep)}</span>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-slate-500 italic">No internal dependencies</p>
                  )}
                </div>

                <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-4">
                  <h5 className="text-sm font-semibold text-slate-800 dark:text-slate-200 mb-3 flex items-center gap-2">
                    <span className="text-green-500">📥</span>
                    Used By ({usedBy.length})
                  </h5>
                  {usedBy.length > 0 ? (
                    <div className="space-y-1 max-h-[200px] overflow-y-auto">
                      {usedBy.map((file, idx) => (
                        <button
                          key={idx}
                          onClick={() => setSelectedFile(file)}
                          className="w-full flex items-center gap-2 p-2 bg-slate-50 dark:bg-slate-700/50 hover:bg-slate-100 dark:hover:bg-slate-700 rounded text-left"
                        >
                          <span>{getFileIcon(file)}</span>
                          <span className="text-sm text-slate-700 dark:text-slate-300 truncate">{getFileName(file)}</span>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-slate-500 italic">No files import this</p>
                  )}
                </div>
              </div>

              {/* External Packages */}
              {selectedDeps?.external && selectedDeps.external.length > 0 && (
                <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-4">
                  <h5 className="text-sm font-semibold text-slate-800 dark:text-slate-200 mb-3 flex items-center gap-2">
                    <span className="text-purple-500">📦</span>
                    External Packages ({selectedDeps.external.length})
                  </h5>
                  <div className="flex flex-wrap gap-2">
                    {selectedDeps.external.map((pkg, idx) => (
                      <span
                        key={idx}
                        className="px-2 py-1 rounded text-xs font-medium bg-purple-100 dark:bg-purple-900/40 text-purple-800 dark:text-purple-200"
                      >
                        {pkg}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="flex items-center justify-center h-[550px] bg-slate-50 dark:bg-slate-700/50 rounded-lg border border-slate-200 dark:border-slate-600">
              <div className="text-center">
                <div className="text-5xl mb-4">👈</div>
                <p className="text-lg text-slate-600 dark:text-slate-400">
                  Select a file to view its dependencies
                </p>
                <p className="text-sm text-slate-500 dark:text-slate-500 mt-2">
                  Select a file from the list
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Legend */}
      <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-3 border border-slate-200 dark:border-slate-700">
        <div className="flex flex-wrap gap-x-6 gap-y-2 text-xs">
          {/* Node colors */}
          <div className="flex items-center gap-4">
            <span className="text-slate-500 dark:text-slate-400 font-medium">Nodes:</span>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 bg-blue-500 rounded-full"></div>
              <span className="text-slate-600 dark:text-slate-400">Selected</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 bg-cyan-500 rounded-full"></div>
              <span className="text-slate-600 dark:text-slate-400">Expanded</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 bg-green-500 rounded-full"></div>
              <span className="text-slate-600 dark:text-slate-400">Dependency</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 bg-purple-500 rounded-full"></div>
              <span className="text-slate-600 dark:text-slate-400">Importer</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 bg-red-500 rounded-full"></div>
              <span className="text-slate-600 dark:text-slate-400">Circular</span>
            </div>
          </div>

          {/* Arrow meanings */}
          <div className="flex items-center gap-4">
            <span className="text-slate-500 dark:text-slate-400 font-medium">Arrows:</span>
            <div className="flex items-center gap-2">
              <span className="text-slate-600 dark:text-slate-400">A → B</span>
              <span className="text-slate-500 dark:text-slate-500">=</span>
              <span className="text-slate-600 dark:text-slate-400">A imports B</span>
            </div>
          </div>

          {/* Counts */}
          <div className="flex items-center gap-4">
            <span className="text-slate-500 dark:text-slate-400 font-medium">Counts:</span>
            <div className="flex items-center gap-2">
              <span className="text-blue-500 font-medium">→N</span>
              <span className="text-slate-600 dark:text-slate-400">imports N files</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-green-500 font-medium">←N</span>
              <span className="text-slate-600 dark:text-slate-400">imported by N files</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
