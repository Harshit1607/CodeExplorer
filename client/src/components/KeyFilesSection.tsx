interface KeyFilesSectionProps {
  keyFiles: string[];
  entryPoints: string[];
}

export default function KeyFilesSection({ keyFiles, entryPoints }: KeyFilesSectionProps) {
  // Normalize path separators (Windows uses \, Unix uses /)
  const normalizePath = (path: string) => path.replace(/\\/g, '/');

  return (
    <div className="space-y-6">
      <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
        Key Files & Entry Points
      </h3>

      {/* Entry Points */}
      <div className="space-y-3">
        <h4 className="text-md font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-2">
          <span>🚀</span>
          Entry Points ({entryPoints?.length || 0})
        </h4>
        {entryPoints && entryPoints.length > 0 ? (
          <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-4 border border-slate-200 dark:border-slate-600">
            <div className="space-y-2">
              {entryPoints.map((file, index) => {
                const normalizedPath = normalizePath(file);
                const fileName = normalizedPath.split('/').pop() || file;

                return (
                  <div
                    key={index}
                    className="flex items-center gap-3 p-3 bg-gradient-to-r from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20 rounded-lg border border-green-200 dark:border-green-800 hover:shadow-md transition-shadow"
                  >
                    <div className="w-10 h-10 bg-green-500 rounded-lg flex items-center justify-center text-white text-xl flex-shrink-0">
                      🎯
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-slate-900 dark:text-white mb-1">
                        {fileName}
                      </p>
                      <p className="text-xs font-mono text-slate-600 dark:text-slate-400 truncate">
                        {normalizedPath}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <div className="bg-amber-50 dark:bg-amber-900/20 rounded-lg p-6 border border-amber-200 dark:border-amber-800 text-center">
            <div className="text-4xl mb-2">🔍</div>
            <p className="text-sm font-medium text-amber-900 dark:text-amber-200 mb-1">
              No entry points detected
            </p>
            <p className="text-xs text-amber-700 dark:text-amber-300">
              This repository may use non-standard entry point patterns
            </p>
          </div>
        )}
      </div>

      {/* Key Files */}
      <div className="space-y-3">
        <h4 className="text-md font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-2">
          <span>⭐</span>
          Important Files ({keyFiles?.length || 0})
        </h4>
        {keyFiles && keyFiles.length > 0 ? (
          <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-4 border border-slate-200 dark:border-slate-600">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {keyFiles.map((file, index) => {
                const normalizedPath = normalizePath(file);
                const fileName = normalizedPath.split('/').pop() || file;
                const filePath = normalizedPath.split('/').slice(0, -1).join('/');
                const baseName = fileName.split('.')[0].toLowerCase();

                // Determine if this is an entry point file
                const entryPointNames = ['app', 'main', 'index', 'page', 'layout', 'server', 'application', 'program', 'startup'];
                const isEntryPoint = entryPointNames.includes(baseName);

                // Get file extension for icon
                const ext = fileName.split('.').pop()?.toLowerCase() || '';
                const getFileIcon = () => {
                  if (isEntryPoint) return '🚀';
                  if (['ts', 'tsx'].includes(ext)) return '🔷';
                  if (['js', 'jsx'].includes(ext)) return '🟨';
                  if (ext === 'py') return '🐍';
                  if (ext === 'java') return '☕';
                  if (ext === 'go') return '🔵';
                  if (ext === 'rs') return '🦀';
                  if (ext === 'rb') return '💎';
                  if (ext === 'php') return '🐘';
                  if (['cs', 'csx'].includes(ext)) return '💜';
                  return '📄';
                };

                return (
                  <div
                    key={index}
                    className={`flex items-start gap-3 p-3 rounded-lg border transition-all hover:shadow-md ${
                      isEntryPoint
                        ? 'bg-gradient-to-r from-sky-50 to-indigo-50 dark:from-sky-900/20 dark:to-indigo-900/20 border-sky-200 dark:border-sky-800'
                        : 'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-600'
                    }`}
                  >
                    <div className={`w-8 h-8 rounded flex items-center justify-center flex-shrink-0 ${
                      isEntryPoint
                        ? 'bg-sky-500 text-white'
                        : 'bg-slate-100 dark:bg-slate-700'
                    }`}>
                      {getFileIcon()}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-slate-900 dark:text-white truncate">
                        {fileName}
                      </p>
                      {filePath && (
                        <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
                          {filePath}
                        </p>
                      )}
                      {isEntryPoint && (
                        <span className="inline-block mt-1 px-2 py-0.5 text-[10px] font-medium bg-sky-100 dark:bg-sky-900/40 text-sky-700 dark:text-sky-300 rounded">
                          ENTRY POINT
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-6 border border-slate-200 dark:border-slate-600 text-center">
            <div className="text-4xl mb-2">📂</div>
            <p className="text-sm text-slate-600 dark:text-slate-400">
              No key files identified
            </p>
          </div>
        )}
      </div>

      {/* Info Box */}
      <div className="bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
        <div className="flex gap-3">
          <div className="text-2xl">
            💡
          </div>
          <div className="text-sm">
            <p className="font-semibold text-blue-900 dark:text-blue-200 mb-2">
              Understanding Key Files
            </p>
            <ul className="space-y-1 text-blue-800 dark:text-blue-300">
              <li><strong>🚀 Entry Points:</strong> Application starting files (App.tsx, main.py, index.js, page.tsx)</li>
              <li><strong>📄 Important Code:</strong> Files with many classes, functions, or imports - core architecture files</li>
            </ul>
            <p className="mt-2 text-xs text-blue-600 dark:text-blue-400">
              Config files (package.json, etc.) and lock files are excluded - only source code shown.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
