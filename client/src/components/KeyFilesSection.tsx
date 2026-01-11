
interface KeyFilesSectionProps {
  keyFiles: string[];
  entryPoints: string[];
}

export default function KeyFilesSection({ keyFiles, entryPoints }: KeyFilesSectionProps) {
  return (
    <div className="space-y-6">
      <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
        Key Files & Entry Points
      </h3>

      {/* Entry Points */}
      <div className="space-y-3">
        <h4 className="text-md font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-2">
          <span>🚀</span>
          Entry Points
        </h4>
        {entryPoints && entryPoints.length > 0 ? (
          <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-4 border border-slate-200 dark:border-slate-600">
            <div className="space-y-2">
              {entryPoints.map((file, index) => (
                <div
                  key={index}
                  className="flex items-center gap-3 p-3 bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-600"
                >
                  <div className="w-8 h-8 bg-green-100 dark:bg-green-900/20 rounded flex items-center justify-center text-green-600 dark:text-green-400">
                    🎯
                  </div>
                  <div className="flex-1">
                    <p className="text-sm font-mono text-slate-900 dark:text-white">
                      {file}
                    </p>
                  </div>
                </div>
              ))}
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-3">
              {entryPoints.length} entry point{entryPoints.length !== 1 ? 's' : ''} detected
            </p>
          </div>
        ) : (
          <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-4 border border-slate-200 dark:border-slate-600 text-center text-slate-500 dark:text-slate-400 text-sm">
            No entry points detected
          </div>
        )}
      </div>

      {/* Key Files */}
      <div className="space-y-3">
        <h4 className="text-md font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-2">
          <span>⭐</span>
          Key Files
        </h4>
        {keyFiles && keyFiles.length > 0 ? (
          <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-4 border border-slate-200 dark:border-slate-600">
            <div className="grid grid-cols-1 gap-2">
              {keyFiles.map((file, index) => {
                const fileName = file.split('/').pop() || file;
                const filePath = file.split('/').slice(0, -1).join('/');

                return (
                  <div
                    key={index}
                    className="flex items-start gap-3 p-3 bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-600 hover:border-blue-400 dark:hover:border-blue-600 transition-colors"
                  >
                    <div className="w-8 h-8 bg-yellow-100 dark:bg-yellow-900/20 rounded flex items-center justify-center text-yellow-600 dark:text-yellow-400 flex-shrink-0">
                      📄
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
                    </div>
                  </div>
                );
              })}
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-3">
              {keyFiles.length} key file{keyFiles.length !== 1 ? 's' : ''} identified
            </p>
          </div>
        ) : (
          <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-4 border border-slate-200 dark:border-slate-600 text-center text-slate-500 dark:text-slate-400 text-sm">
            No key files identified
          </div>
        )}
      </div>

      {/* Info Box */}
      <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
        <div className="flex gap-3">
          <div className="text-blue-600 dark:text-blue-400 mt-0.5">
            ℹ️
          </div>
          <div className="text-sm text-blue-900 dark:text-blue-200">
            <p className="font-medium mb-1">About Key Files</p>
            <p className="text-blue-700 dark:text-blue-300">
              Key files are identified based on configuration files, files with many imports,
              or files with significant code complexity. Entry points are files that typically
              start the application.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
