import { useMemo } from 'react';

interface FileNode {
  type: 'file' | 'folder';
  size?: number;
  language?: string;
  lines?: number;
  children?: { [key: string]: FileNode };
}

interface FileTreemapProps {
  tree: { [key: string]: FileNode };
}

interface FlatFile {
  path: string;
  name: string;
  size: number;
  language: string;
  percentage: number;
}

const LANGUAGE_COLORS: { [key: string]: string } = {
  'Python': '#3572A5',
  'JavaScript': '#f1e05a',
  'TypeScript': '#2b7489',
  'Java': '#b07219',
  'C++': '#f34b7d',
  'C': '#555555',
  'Go': '#00ADD8',
  'Rust': '#dea584',
  'Ruby': '#701516',
  'PHP': '#4F5D95',
  'HTML': '#e34c26',
  'CSS': '#563d7c',
  'SCSS': '#c6538c',
  'Markdown': '#083fa1',
  'JSON': '#292929',
  'YAML': '#cb171e',
  'Other': '#64748b',
};

function flattenTree(tree: { [key: string]: FileNode }, prefix = ''): FlatFile[] {
  const files: FlatFile[] = [];

  Object.entries(tree).forEach(([name, node]) => {
    const fullPath = prefix ? `${prefix}/${name}` : name;

    if (node.type === 'file' && node.lines && node.lines > 0) {
      files.push({
        path: fullPath,
        name,
        size: node.lines,
        language: node.language || 'Other',
        percentage: 0, // Will be calculated later
      });
    } else if (node.type === 'folder' && node.children) {
      files.push(...flattenTree(node.children, fullPath));
    }
  });

  return files;
}

export default function FileTreemap({ tree }: FileTreemapProps) {
  const files = useMemo(() => {
    if (!tree || Object.keys(tree).length === 0) return [];

    const flatFiles = flattenTree(tree);
    const totalLines = flatFiles.reduce((sum, f) => sum + f.size, 0);

    return flatFiles
      .map(f => ({
        ...f,
        percentage: (f.size / totalLines) * 100,
      }))
      .sort((a, b) => b.size - a.size)
      .slice(0, 50); // Top 50 files
  }, [tree]);

  if (files.length === 0) {
    return (
      <div className="text-center py-8 text-slate-500 dark:text-slate-400">
        No file data available for treemap visualization
      </div>
    );
  }

  const totalLines = files.reduce((sum, f) => sum + f.size, 0);

  return (
    <div className="space-y-4">
      <div>
        <h4 className="text-md font-semibold text-slate-900 dark:text-white mb-2">
          File Size Treemap
        </h4>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Visual representation of file sizes (top 50 files by lines of code). Hover for details.
        </p>
      </div>

      {/* Treemap Grid */}
      <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg border border-slate-200 dark:border-slate-600 p-4">
        <div className="grid grid-cols-10 gap-1" style={{ height: '500px' }}>
          {files.map((file, index) => {
            const color = LANGUAGE_COLORS[file.language] || LANGUAGE_COLORS['Other'];
            const minSize = Math.max(file.percentage * 5, 20); // Minimum visible size
            const gridSpan = Math.max(1, Math.min(10, Math.ceil(file.percentage / 2)));

            return (
              <div
                key={index}
                className="group relative rounded overflow-hidden transition-all hover:ring-2 hover:ring-white hover:z-10 cursor-pointer"
                style={{
                  backgroundColor: color,
                  opacity: 0.8,
                  gridColumn: `span ${gridSpan}`,
                  minHeight: `${minSize}px`,
                }}
                title={`${file.path}\n${file.size} lines (${file.percentage.toFixed(1)}%)`}
              >
                {file.percentage > 2 && (
                  <div className="absolute inset-0 p-2 text-white text-xs font-medium">
                    <div className="truncate">{file.name}</div>
                    <div className="text-[10px] opacity-75">{file.size} lines</div>
                  </div>
                )}

                {/* Tooltip on hover */}
                <div className="absolute hidden group-hover:block bottom-full left-0 mb-2 bg-slate-900 text-white text-xs rounded px-3 py-2 whitespace-nowrap z-20 shadow-lg">
                  <div className="font-semibold">{file.name}</div>
                  <div className="text-slate-300">{file.path}</div>
                  <div className="mt-1">
                    {file.size.toLocaleString()} lines • {file.percentage.toFixed(1)}%
                  </div>
                  <div className="text-slate-400">{file.language}</div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-3">
        {Object.entries(
          files.reduce((acc, f) => {
            acc[f.language] = (acc[f.language] || 0) + 1;
            return acc;
          }, {} as { [key: string]: number })
        ).map(([lang, count]) => (
          <div key={lang} className="flex items-center gap-2">
            <div
              className="w-4 h-4 rounded"
              style={{ backgroundColor: LANGUAGE_COLORS[lang] || LANGUAGE_COLORS['Other'] }}
            />
            <span className="text-sm text-slate-700 dark:text-slate-300">
              {lang} ({count})
            </span>
          </div>
        ))}
      </div>

      {/* Stats */}
      <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
        <div className="text-sm text-blue-900 dark:text-blue-200">
          <strong>Total:</strong> {totalLines.toLocaleString()} lines across {files.length} files (showing top 50)
        </div>
      </div>
    </div>
  );
}
