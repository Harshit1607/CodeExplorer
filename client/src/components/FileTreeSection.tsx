import { useState } from 'react';
import FileTreemap from './FileTreemap';

interface FileNode {
  type: 'file' | 'folder';
  size?: number;
  language?: string;
  lines?: number;
  children?: { [key: string]: FileNode };
}

interface FileTreeSectionProps {
  tree: { [key: string]: FileNode };
}

function TreeNode({ name, node, level = 0 }: { name: string; node: FileNode; level?: number }) {
  const [isExpanded, setIsExpanded] = useState(level < 2);

  if (node.type === 'file') {
    return (
      <div
        className="flex items-center gap-2 py-1 px-2 hover:bg-slate-100 dark:hover:bg-slate-700 rounded text-sm"
        style={{ paddingLeft: `${level * 20 + 8}px` }}
      >
        <span className="text-blue-500">📄</span>
        <span className="text-slate-700 dark:text-slate-300">{name}</span>
        <span className="text-xs text-slate-500 dark:text-slate-400 ml-auto">
          {node.language} • {node.lines} lines
        </span>
      </div>
    );
  }

  return (
    <div>
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-2 py-1 px-2 hover:bg-slate-100 dark:hover:bg-slate-700 rounded text-sm w-full text-left"
        style={{ paddingLeft: `${level * 20 + 8}px` }}
      >
        <span className="text-yellow-600">{isExpanded ? '📂' : '📁'}</span>
        <span className="font-medium text-slate-800 dark:text-slate-200">{name}</span>
        <span className="text-xs text-slate-400 ml-2">
          ({Object.keys(node.children || {}).length} items)
        </span>
      </button>
      {isExpanded && node.children && (
        <div>
          {Object.entries(node.children)
            .sort(([, a], [, b]) => {
              if (a.type === b.type) return 0;
              return a.type === 'folder' ? -1 : 1;
            })
            .map(([childName, childNode]) => (
              <TreeNode key={childName} name={childName} node={childNode} level={level + 1} />
            ))}
        </div>
      )}
    </div>
  );
}

export default function FileTreeSection({ tree }: FileTreeSectionProps) {
  const [viewMode, setViewMode] = useState<'tree' | 'treemap'>('tree');

  if (!tree || Object.keys(tree).length === 0) {
    return (
      <div className="text-center py-8 text-slate-500 dark:text-slate-400">
        No file tree data available
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
          File Structure
        </h3>
        <div className="flex gap-2 bg-slate-100 dark:bg-slate-700 p-1 rounded-lg">
          <button
            onClick={() => setViewMode('tree')}
            className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
              viewMode === 'tree'
                ? 'bg-white dark:bg-slate-600 text-slate-900 dark:text-white shadow'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
            }`}
          >
            Tree View
          </button>
          <button
            onClick={() => setViewMode('treemap')}
            className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
              viewMode === 'treemap'
                ? 'bg-white dark:bg-slate-600 text-slate-900 dark:text-white shadow'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
            }`}
          >
            Treemap View
          </button>
        </div>
      </div>

      {viewMode === 'treemap' ? (
        <FileTreemap tree={tree} />
      ) : (
        <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-4 border border-slate-200 dark:border-slate-600 max-h-[600px] overflow-y-auto">
          {Object.entries(tree)
            .sort(([, a], [, b]) => {
              if (a.type === b.type) return 0;
              return a.type === 'folder' ? -1 : 1;
            })
            .map(([name, node]) => (
              <TreeNode key={name} name={name} node={node} />
            ))}
        </div>
      )}
    </div>
  );
}
