import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';

interface FileMetadata {
  path: string;
  language: string;
  lines: number;
  functions?: any[];
  classes?: any[];
  imports?: string[];
}

interface ComplexityAnalysisProps {
  files: { [key: string]: FileMetadata };
  highlightTarget?: {
    filePath: string;
    type: string;
    name: string;
  } | null;
}

export default function ComplexityAnalysis({ files, highlightTarget: _highlightTarget }: ComplexityAnalysisProps) {
  if (!files || Object.keys(files).length === 0) {
    return (
      <div className="text-center py-12 bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
        <div className="text-6xl mb-4">📊</div>
        <p className="text-lg font-medium text-slate-700 dark:text-slate-300 mb-2">
          No complexity data available
        </p>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Analyze a repository to see complexity metrics
        </p>
      </div>
    );
  }

  // Files to exclude from complexity analysis (auto-generated, lock files, etc.)
  const excludedFiles = [
    'package-lock.json',
    'yarn.lock',
    'pnpm-lock.yaml',
    'composer.lock',
    'Gemfile.lock',
    'Cargo.lock',
    'poetry.lock',
    'package.json', // Config file, not code
    'tsconfig.json',
    'jsconfig.json',
    '.eslintrc',
    '.prettierrc',
  ];

  // Calculate complexity score for each file
  const fileComplexity = Object.entries(files)
    .filter(([path]) => {
      const filename = path.split(/[/\\]/).pop()?.toLowerCase() || '';
      // Exclude auto-generated and config files
      return !excludedFiles.some(excluded => filename === excluded.toLowerCase());
    })
    .map(([path, metadata]) => {
      const lines = metadata.lines || 0;
      const functions = metadata.functions?.length || 0;
      const classes = metadata.classes?.length || 0;
      const imports = metadata.imports?.length || 0;

      // Complexity formula (weighted by importance)
      const complexityScore =
        (lines / 10) +           // Large files are harder to understand
        (functions * 3) +         // Many functions indicate complexity
        (classes * 5) +           // Classes add structure complexity
        (imports * 2);            // Many imports = high coupling

      // Maintainability (inverse of complexity, 0-100 scale)
      const maintainability = Math.max(0, Math.min(100, 100 - (complexityScore / 20)));

      return {
        path: path.replace(/\\/g, '/'),
        filename: path.split(/[/\\]/).pop() || path,
        lines,
        functions,
        classes,
        imports,
        complexity: Math.round(complexityScore),
        maintainability: Math.round(maintainability),
        language: metadata.language,
      };
    })
    .filter(f => f.complexity > 5) // Filter out trivial files
    .sort((a, b) => b.complexity - a.complexity)
    .slice(0, 15); // Top 15 most complex files

  if (fileComplexity.length === 0) {
    return (
      <div className="text-center py-8 text-slate-500 dark:text-slate-400">
        All files have low complexity - this is a simple codebase!
      </div>
    );
  }

  const getComplexityColor = (complexity: number) => {
    if (complexity > 100) return '#ef4444'; // red
    if (complexity > 50) return '#f59e0b';  // orange
    if (complexity > 25) return '#eab308';  // yellow
    return '#22c55e'; // green
  };

  const getComplexityLabel = (complexity: number) => {
    if (complexity > 100) return 'Very High';
    if (complexity > 50) return 'High';
    if (complexity > 25) return 'Medium';
    return 'Low';
  };

  const avgComplexity = Math.round(
    fileComplexity.reduce((sum, f) => sum + f.complexity, 0) / fileComplexity.length
  );

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      return (
        <div className="bg-white dark:bg-slate-800 border-2 border-slate-300 dark:border-slate-600 rounded-lg p-4 shadow-xl max-w-sm">
          <p className="font-bold text-slate-900 dark:text-white mb-2 text-base">
            {data.filename}
          </p>
          <p className="text-xs text-slate-500 dark:text-slate-400 mb-3 font-mono truncate">
            {data.path}
          </p>
          <div className="space-y-1.5 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-600 dark:text-slate-400">Complexity:</span>
              <span className="font-semibold text-slate-900 dark:text-white">
                {data.complexity} ({getComplexityLabel(data.complexity)})
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-600 dark:text-slate-400">Maintainability:</span>
              <span className="font-semibold text-green-600 dark:text-green-400">
                {data.maintainability}%
              </span>
            </div>
            <div className="border-t border-slate-200 dark:border-slate-700 my-2"></div>
            <div className="flex justify-between text-xs">
              <span className="text-slate-500">Lines:</span>
              <span>{data.lines.toLocaleString()}</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-slate-500">Functions:</span>
              <span>{data.functions}</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-slate-500">Classes:</span>
              <span>{data.classes}</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-slate-500">Imports:</span>
              <span>{data.imports}</span>
            </div>
          </div>
        </div>
      );
    }
    return null;
  };

  const veryHighCount = fileComplexity.filter(f => f.complexity > 100).length;
  const highCount = fileComplexity.filter(f => f.complexity > 50).length;

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-2xl font-bold text-slate-900 dark:text-white mb-2 flex items-center gap-3">
          <span className="text-3xl">🎯</span>
          Code Complexity Analysis
        </h3>
        <p className="text-slate-600 dark:text-slate-400">
          Files ranked by complexity based on lines, functions, classes, and dependencies.
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/30 dark:to-blue-900/50 border-2 border-blue-200 dark:border-blue-800 rounded-xl p-5">
          <div className="text-blue-600 dark:text-blue-400 text-sm font-semibold mb-2">
            Average Complexity
          </div>
          <div className="text-4xl font-bold text-blue-900 dark:text-blue-100">
            {avgComplexity}
          </div>
          <div className="text-xs text-blue-700 dark:text-blue-300 mt-2">
            {getComplexityLabel(avgComplexity)} overall
          </div>
        </div>

        <div className="bg-gradient-to-br from-orange-50 to-orange-100 dark:from-orange-900/30 dark:to-orange-900/50 border-2 border-orange-200 dark:border-orange-800 rounded-xl p-5">
          <div className="text-orange-600 dark:text-orange-400 text-sm font-semibold mb-2">
            High Complexity Files
          </div>
          <div className="text-4xl font-bold text-orange-900 dark:text-orange-100">
            {highCount}
          </div>
          <div className="text-xs text-orange-700 dark:text-orange-300 mt-2">
            Need attention
          </div>
        </div>

        <div className="bg-gradient-to-br from-red-50 to-red-100 dark:from-red-900/30 dark:to-red-900/50 border-2 border-red-200 dark:border-red-800 rounded-xl p-5">
          <div className="text-red-600 dark:text-red-400 text-sm font-semibold mb-2">
            Critical Files
          </div>
          <div className="text-4xl font-bold text-red-900 dark:text-red-100">
            {veryHighCount}
          </div>
          <div className="text-xs text-red-700 dark:text-red-300 mt-2">
            Urgent refactoring
          </div>
        </div>
      </div>

      {/* Chart */}
      <div className="bg-white dark:bg-slate-800 rounded-xl border-2 border-slate-200 dark:border-slate-700 p-6 shadow-lg">
        <h4 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">
          Top 15 Most Complex Files
        </h4>
        <div className="h-[500px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={fileComplexity}
              layout="vertical"
              margin={{ top: 5, right: 30, left: 150, bottom: 5 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" opacity={0.5} />
              <XAxis
                type="number"
                tick={{ fill: '#64748b', fontSize: 12 }}
                label={{ value: 'Complexity Score', position: 'insideBottom', offset: -5 }}
              />
              <YAxis
                type="category"
                dataKey="filename"
                width={140}
                tick={{ fill: '#64748b', fontSize: 11 }}
              />
              <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(59, 130, 246, 0.1)' }} />
              <Bar dataKey="complexity" radius={[0, 8, 8, 0]}>
                {fileComplexity.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={getComplexityColor(entry.complexity)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Complexity Legend */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: 'Low (0-25)', color: '#22c55e', desc: 'Easy to maintain', range: '0-25' },
          { label: 'Medium (25-50)', color: '#eab308', desc: 'Manageable', range: '25-50' },
          { label: 'High (50-100)', color: '#f59e0b', desc: 'Consider refactoring', range: '50-100' },
          { label: 'Very High (100+)', color: '#ef4444', desc: 'Needs urgent attention', range: '100+' },
        ].map((item, idx) => (
          <div key={idx} className="bg-slate-50 dark:bg-slate-700/50 border border-slate-200 dark:border-slate-600 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-1">
              <div className="w-4 h-4 rounded" style={{ backgroundColor: item.color }}></div>
              <span className="text-xs font-semibold text-slate-900 dark:text-white">{item.label}</span>
            </div>
            <p className="text-[10px] text-slate-600 dark:text-slate-400">{item.desc}</p>
          </div>
        ))}
      </div>

      {/* Actionable Insights */}
      <div className="bg-gradient-to-r from-amber-50 via-yellow-50 to-orange-50 dark:from-amber-900/20 dark:via-yellow-900/20 dark:to-orange-900/20 border-2 border-amber-200 dark:border-amber-800 rounded-xl p-6">
        <h4 className="text-lg font-bold text-amber-900 dark:text-amber-200 mb-4 flex items-center gap-2">
          <span className="text-2xl">💡</span>
          Actionable Insights
        </h4>
        <ul className="space-y-3 text-sm text-amber-900 dark:text-amber-100">
          <li className="flex items-start gap-3">
            <span className="text-xl">→</span>
            <span>
              <strong>{veryHighCount} {veryHighCount === 1 ? 'file has' : 'files have'}</strong> very high complexity and should be prioritized for refactoring
            </span>
          </li>
          <li className="flex items-start gap-3">
            <span className="text-xl">→</span>
            <span>
              <strong>{highCount} {highCount === 1 ? 'file' : 'files'}</strong> may benefit from splitting into smaller modules
            </span>
          </li>
          <li className="flex items-start gap-3">
            <span className="text-xl">→</span>
            <span>
              Most complex file: <strong className="font-mono">{fileComplexity[0]?.filename}</strong> with complexity score of <strong>{fileComplexity[0]?.complexity}</strong>
            </span>
          </li>
          <li className="flex items-start gap-3">
            <span className="text-xl">→</span>
            <span>
              When onboarding, start with simpler files and avoid high-complexity files initially
            </span>
          </li>
        </ul>
      </div>
    </div>
  );
}
