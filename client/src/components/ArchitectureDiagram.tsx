import { useMemo } from 'react';
import ReactFlow, {
  Node,
  Edge,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
  Position,
  Handle,
} from 'reactflow';
import 'reactflow/dist/style.css';

// Data interfaces (matching backend output)
interface ArchNode {
  id: string;
  label: string;
  type: 'component' | 'database';
  layer: string;
  file_count: number;
  languages: string[];
  functions_count: number;
  classes_count: number;
  lines: number;
  frameworks: string[];
}

interface ArchEdge {
  source: string;
  target: string;
  label: string;
  weight?: number;
}

interface ArchLayer {
  name: string;
  nodes: string[];
}

interface ArchitectureData {
  nodes: ArchNode[];
  edges: ArchEdge[];
  layers: ArchLayer[];
}

interface ArchitectureDiagramProps {
  architecture: ArchitectureData;
}

// Layer colors mapping
const LAYER_COLORS: { [key: string]: { bg: string; border: string; text: string } } = {
  frontend: {
    bg: 'bg-blue-50 dark:bg-blue-900/30',
    border: 'border-blue-300 dark:border-blue-700',
    text: 'text-blue-800 dark:text-blue-200',
  },
  api: {
    bg: 'bg-green-50 dark:bg-green-900/30',
    border: 'border-green-300 dark:border-green-700',
    text: 'text-green-800 dark:text-green-200',
  },
  middleware: {
    bg: 'bg-cyan-50 dark:bg-cyan-900/30',
    border: 'border-cyan-300 dark:border-cyan-700',
    text: 'text-cyan-800 dark:text-cyan-200',
  },
  services: {
    bg: 'bg-purple-50 dark:bg-purple-900/30',
    border: 'border-purple-300 dark:border-purple-700',
    text: 'text-purple-800 dark:text-purple-200',
  },
  data: {
    bg: 'bg-orange-50 dark:bg-orange-900/30',
    border: 'border-orange-300 dark:border-orange-700',
    text: 'text-orange-800 dark:text-orange-200',
  },
  config: {
    bg: 'bg-slate-100 dark:bg-slate-700/50',
    border: 'border-slate-300 dark:border-slate-600',
    text: 'text-slate-800 dark:text-slate-200',
  },
  tests: {
    bg: 'bg-yellow-50 dark:bg-yellow-900/30',
    border: 'border-yellow-300 dark:border-yellow-700',
    text: 'text-yellow-800 dark:text-yellow-200',
  },
  utils: {
    bg: 'bg-indigo-50 dark:bg-indigo-900/30',
    border: 'border-indigo-300 dark:border-indigo-700',
    text: 'text-indigo-800 dark:text-indigo-200',
  },
  other: {
    bg: 'bg-gray-50 dark:bg-gray-800',
    border: 'border-gray-300 dark:border-gray-600',
    text: 'text-gray-800 dark:text-gray-200',
  },
};

// Custom node component for architectural components
function ComponentNode({ data }: { data: any }) {
  const colors = LAYER_COLORS[data.layer] || LAYER_COLORS.other;

  return (
    <div className={`px-4 py-3 rounded-lg border-2 shadow-md min-w-[160px] ${colors.bg} ${colors.border}`}>
      <Handle type="target" position={Position.Top} className="!bg-slate-400" />
      <div className={`text-sm font-semibold ${colors.text}`}>
        {data.label}
      </div>
      {data.frameworks?.length > 0 && (
        <div className="text-xs text-slate-500 dark:text-slate-400 mt-1">
          {data.frameworks.join(', ')}
        </div>
      )}
      <div className="text-xs text-slate-400 dark:text-slate-500 mt-1">
        {data.file_count} files • {data.lines.toLocaleString()} lines
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-slate-400" />
    </div>
  );
}

// Custom node component for databases
function DatabaseNode({ data }: { data: any }) {
  return (
    <div className="px-4 py-3 rounded-xl border-2 shadow-md min-w-[120px] bg-amber-50 dark:bg-amber-900/30 border-amber-400 dark:border-amber-700">
      <Handle type="target" position={Position.Top} className="!bg-amber-500" />
      <div className="text-center">
        <div className="text-2xl mb-1">🗄️</div>
        <div className="text-sm font-semibold text-amber-900 dark:text-amber-100">
          {data.label}
        </div>
      </div>
    </div>
  );
}

// Node types for ReactFlow
const nodeTypes = {
  component: ComponentNode,
  database: DatabaseNode,
};

// Compute layout for nodes based on layers
function computeLayout(archData: ArchitectureData): { nodes: Node[]; edges: Edge[] } {
  const layerOrder = ['frontend', 'api', 'middleware', 'services', 'data', 'config', 'utils', 'tests', 'other'];
  const LAYER_GAP = 180;
  const NODE_GAP_X = 220;
  const VIEWPORT_WIDTH = 1200;

  // Assign Y position per layer (top-to-bottom)
  const layerY: Record<string, number> = {};
  let currentY = 50;

  layerOrder.forEach(layerName => {
    const layerNodes = archData.nodes.filter(n => n.layer === layerName);
    if (layerNodes.length > 0) {
      layerY[layerName] = currentY;
      currentY += LAYER_GAP;
    }
  });

  // Group nodes per layer
  const nodesPerLayer: Record<string, ArchNode[]> = {};
  archData.nodes.forEach(n => {
    if (!nodesPerLayer[n.layer]) nodesPerLayer[n.layer] = [];
    nodesPerLayer[n.layer].push(n);
  });

  // Position nodes within each layer (spread horizontally, centered)
  const rfNodes: Node[] = archData.nodes.map(n => {
    const layerNodes = nodesPerLayer[n.layer] || [];
    const indexInLayer = layerNodes.indexOf(n);
    const totalInLayer = layerNodes.length;
    const totalWidth = totalInLayer * NODE_GAP_X;
    const startX = (VIEWPORT_WIDTH - totalWidth) / 2 + NODE_GAP_X / 2;

    return {
      id: n.id,
      type: n.type,
      position: {
        x: startX + indexInLayer * NODE_GAP_X,
        y: layerY[n.layer] || 0,
      },
      data: {
        label: n.label,
        layer: n.layer,
        type: n.type,
        frameworks: n.frameworks,
        file_count: n.file_count,
        lines: n.lines,
        functions_count: n.functions_count,
        classes_count: n.classes_count,
        languages: n.languages,
      },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
    };
  });

  // Create edges
  const rfEdges: Edge[] = archData.edges.map((e, i) => ({
    id: `edge-${i}`,
    source: e.source,
    target: e.target,
    type: 'smoothstep',
    animated: false,
    markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
    style: { stroke: '#94a3b8', strokeWidth: Math.min(2 + (e.weight || 1) / 5, 5) },
    label: e.weight && e.weight > 1 ? `${e.weight}` : undefined,
    labelStyle: { fontSize: 10, fill: '#64748b' },
    labelBgStyle: { fill: '#1e293b', fillOpacity: 0.8 },
  }));

  return { nodes: rfNodes, edges: rfEdges };
}

export default function ArchitectureDiagram({ architecture }: ArchitectureDiagramProps) {
  const { nodes: initialNodes, edges: initialEdges } = useMemo(
    () => computeLayout(architecture || { nodes: [], edges: [], layers: [] }),
    [architecture]
  );

  const [nodes, , onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(initialEdges);

  // Get unique layers that have nodes
  const activeLayers = useMemo(() => {
    return (architecture?.layers || []).filter(l => l.nodes.length > 0);
  }, [architecture]);

  // Calculate stats
  const stats = useMemo(() => {
    const archNodes = architecture?.nodes || [];
    const componentNodes = archNodes.filter(n => n.type === 'component');
    const totalFiles = componentNodes.reduce((sum, n) => sum + n.file_count, 0);
    const totalLines = componentNodes.reduce((sum, n) => sum + n.lines, 0);

    return {
      components: componentNodes.length,
      databases: archNodes.filter(n => n.type === 'database').length,
      connections: architecture?.edges?.length || 0,
      totalFiles,
      totalLines,
    };
  }, [architecture]);

  // Empty state
  if (!architecture || !architecture.nodes || architecture.nodes.length === 0) {
    return (
      <div className="text-center py-12 bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
        <div className="text-6xl mb-4">🏗️</div>
        <p className="text-lg font-medium text-slate-700 dark:text-slate-300 mb-2">
          No architecture data available
        </p>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Analyze a repository to see its high-level architecture
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
            🏗️ Architecture Diagram
          </h3>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Auto-generated high-level system architecture
          </p>
        </div>

        {/* Legend */}
        <div className="flex gap-2 flex-wrap">
          {Object.entries(LAYER_COLORS).slice(0, 6).map(([layer, colors]) => (
            <span
              key={layer}
              className={`px-2 py-1 text-xs rounded ${colors.bg} ${colors.border} border ${colors.text}`}
            >
              {layer}
            </span>
          ))}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-3 border border-slate-200 dark:border-slate-600">
          <span className="text-xs text-slate-500 dark:text-slate-400">Components</span>
          <p className="text-lg font-bold text-slate-900 dark:text-white">{stats.components}</p>
        </div>
        <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-3 border border-slate-200 dark:border-slate-600">
          <span className="text-xs text-slate-500 dark:text-slate-400">Databases</span>
          <p className="text-lg font-bold text-slate-900 dark:text-white">{stats.databases}</p>
        </div>
        <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-3 border border-slate-200 dark:border-slate-600">
          <span className="text-xs text-slate-500 dark:text-slate-400">Connections</span>
          <p className="text-lg font-bold text-slate-900 dark:text-white">{stats.connections}</p>
        </div>
        <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-3 border border-slate-200 dark:border-slate-600">
          <span className="text-xs text-slate-500 dark:text-slate-400">Total Files</span>
          <p className="text-lg font-bold text-slate-900 dark:text-white">{stats.totalFiles}</p>
        </div>
        <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-3 border border-slate-200 dark:border-slate-600">
          <span className="text-xs text-slate-500 dark:text-slate-400">Total Lines</span>
          <p className="text-lg font-bold text-slate-900 dark:text-white">{stats.totalLines.toLocaleString()}</p>
        </div>
      </div>

      {/* ReactFlow Diagram */}
      <div
        className="bg-slate-900 rounded-lg border border-slate-700 overflow-hidden"
        style={{ height: 600 }}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.3}
          maxZoom={2}
          defaultEdgeOptions={{
            type: 'smoothstep',
          }}
        >
          <Background color="#334155" gap={20} />
          <Controls className="!bg-slate-800 !border-slate-600 !rounded-lg [&>button]:!bg-slate-700 [&>button]:!border-slate-600 [&>button]:!text-slate-300 [&>button:hover]:!bg-slate-600" />
          <MiniMap
            nodeColor={(node) => {
              const layer = node.data?.layer || 'other';
              const colorMap: Record<string, string> = {
                frontend: '#3b82f6',
                api: '#22c55e',
                middleware: '#06b6d4',
                services: '#a855f7',
                data: '#f97316',
                config: '#64748b',
                tests: '#eab308',
                utils: '#6366f1',
                other: '#6b7280',
              };
              return colorMap[layer] || '#6b7280';
            }}
            className="!bg-slate-800 !border-slate-600 !rounded-lg"
            maskColor="rgba(0, 0, 0, 0.5)"
          />
        </ReactFlow>
      </div>

      {/* Layer summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
        {activeLayers.map(layer => {
          const colors = LAYER_COLORS[layer.name] || LAYER_COLORS.other;
          return (
            <div
              key={layer.name}
              className={`rounded-lg p-3 border ${colors.bg} ${colors.border}`}
            >
              <span className={`text-xs font-semibold uppercase ${colors.text}`}>
                {layer.name}
              </span>
              <p className="text-lg font-bold text-slate-900 dark:text-white">
                {layer.nodes.length} {layer.nodes.length === 1 ? 'component' : 'components'}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
