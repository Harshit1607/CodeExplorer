import { useEffect, useRef } from 'react';
import * as d3 from 'd3';

interface Node {
  id: string;
  group: number;
  type: string;
}

interface Link {
  source: string;
  target: string;
  value: number;
}

interface DependencyGraphProps {
  dependencies: {
    python?: { [key: string]: string[] };
    javascript?: { [key: string]: string[] };
    other?: { [key: string]: string[] };
  };
}

export default function DependencyGraph({ dependencies }: DependencyGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || !dependencies) return;

    // Clear previous content
    d3.select(svgRef.current).selectAll('*').remove();

    // Prepare graph data
    const nodes: Node[] = [];
    const links: Link[] = [];
    const nodeMap = new Set<string>();

    let group = 0;

    // Process all dependency types
    Object.entries(dependencies).forEach(([depType, depSources]) => {
      if (!depSources) return;

      Object.entries(depSources).forEach(([source, packages]) => {
        if (!packages || packages.length === 0) return;

        const sourceId = `${depType}:${source}`;
        if (!nodeMap.has(sourceId)) {
          nodes.push({ id: sourceId, group, type: depType });
          nodeMap.add(sourceId);
        }

        packages.slice(0, 15).forEach((pkg) => { // Limit to 15 packages per source
          const pkgId = pkg;
          if (!nodeMap.has(pkgId)) {
            nodes.push({ id: pkgId, group: group + 1, type: 'package' });
            nodeMap.add(pkgId);
          }
          links.push({ source: sourceId, target: pkgId, value: 1 });
        });

        group += 2;
      });
    });

    if (nodes.length === 0) return;

    // Set up SVG dimensions
    const width = 800;
    const height = 600;
    const svg = d3.select(svgRef.current)
      .attr('width', '100%')
      .attr('height', '100%')
      .attr('viewBox', `0 0 ${width} ${height}`);

    // Create arrow marker for links
    svg.append('defs').append('marker')
      .attr('id', 'arrowhead')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 20)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 8)
      .attr('markerHeight', 8)
      .append('svg:path')
      .attr('d', 'M 0,-5 L 10 ,0 L 0,5')
      .attr('fill', '#94a3b8');

    // Create force simulation
    const simulation = d3.forceSimulation(nodes as any)
      .force('link', d3.forceLink(links).id((d: any) => d.id).distance(100))
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(30));

    // Create link elements
    const link = svg.append('g')
      .selectAll('line')
      .data(links)
      .enter()
      .append('line')
      .attr('stroke', '#94a3b8')
      .attr('stroke-opacity', 0.6)
      .attr('stroke-width', 2)
      .attr('marker-end', 'url(#arrowhead)');

    // Create node elements
    const node = svg.append('g')
      .selectAll('g')
      .data(nodes)
      .enter()
      .append('g')
      .call(d3.drag<any, any>()
        .on('start', dragstarted)
        .on('drag', dragged)
        .on('end', dragended) as any);

    // Add circles to nodes
    node.append('circle')
      .attr('r', (d) => d.type === 'package' ? 8 : 12)
      .attr('fill', (d) => {
        if (d.type === 'python') return '#3572A5';
        if (d.type === 'javascript') return '#f1e05a';
        if (d.type === 'package') return '#8b5cf6';
        return '#64748b';
      })
      .attr('stroke', '#fff')
      .attr('stroke-width', 2);

    // Add labels to nodes
    node.append('text')
      .text((d) => {
        const parts = d.id.split(':');
        return parts[parts.length - 1].substring(0, 15);
      })
      .attr('x', 15)
      .attr('y', 4)
      .attr('font-size', 10)
      .attr('fill', '#334155')
      .attr('class', 'dark:fill-slate-300');

    // Add tooltips
    node.append('title')
      .text((d) => `${d.id} (${d.type})`);

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
  }, [dependencies]);

  return (
    <div className="w-full bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-4">
      <div className="mb-4">
        <h4 className="text-md font-semibold text-slate-900 dark:text-white mb-2">
          Dependency Graph
        </h4>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Interactive visualization of dependencies. Drag nodes to explore connections.
        </p>
        <div className="flex gap-4 mt-2 text-xs">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-[#3572A5]"></div>
            <span className="text-slate-600 dark:text-slate-400">Python</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-[#f1e05a]"></div>
            <span className="text-slate-600 dark:text-slate-400">JavaScript</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-[#8b5cf6]"></div>
            <span className="text-slate-600 dark:text-slate-400">Package</span>
          </div>
        </div>
      </div>
      <svg ref={svgRef} className="w-full h-[600px]" />
    </div>
  );
}
