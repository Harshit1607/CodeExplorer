interface OverviewSectionProps {
  repositoryUrl: string;
  scanResults: any;
  structureAnalysis: any;
}

export default function OverviewSection({
  repositoryUrl,
  scanResults,
  structureAnalysis,
}: OverviewSectionProps) {
  const frameworks = structureAnalysis?.frameworks || { frontend: [], backend: [] };
  const databases = structureAnalysis?.databases || [];

  const stats = [
    {
      label: 'Total Files',
      value: structureAnalysis?.total_files || scanResults?.total_files || 0,
      icon: '📄',
      color: 'bg-blue-100 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300',
    },
    {
      label: 'Languages',
      value: Object.keys(structureAnalysis?.languages || {}).length,
      icon: '💻',
      color: 'bg-purple-100 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300',
    },
    {
      label: 'Entry Points',
      value: structureAnalysis?.entry_points?.length || 0,
      icon: '🚀',
      color: 'bg-green-100 dark:bg-green-900/20 text-green-700 dark:text-green-300',
    },
    {
      label: 'Key Files',
      value: structureAnalysis?.key_files?.length || 0,
      icon: '⭐',
      color: 'bg-yellow-100 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-300',
    },
  ];

  const complexityStats = structureAnalysis?.complexity || {};

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">
          Repository Overview
        </h3>
        <a
          href={repositoryUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-600 dark:text-blue-400 hover:underline text-sm"
        >
          {repositoryUrl}
        </a>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat, index) => (
          <div
            key={index}
            className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-4 border border-slate-200 dark:border-slate-600"
          >
            <div className="flex items-center gap-3">
              <div className={`w-12 h-12 rounded-lg ${stat.color} flex items-center justify-center text-2xl`}>
                {stat.icon}
              </div>
              <div>
                <p className="text-sm text-slate-600 dark:text-slate-400">{stat.label}</p>
                <p className="text-2xl font-bold text-slate-900 dark:text-white">
                  {stat.value.toLocaleString()}
                </p>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Frameworks Section */}
      {(frameworks.frontend?.length > 0 || frameworks.backend?.length > 0) && (
        <div className="bg-gradient-to-r from-indigo-50 to-purple-50 dark:from-indigo-900/20 dark:to-purple-900/20 rounded-lg p-5 border border-indigo-200 dark:border-indigo-800">
          <h4 className="text-md font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
            <span>🛠️</span>
            Tech Stack
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Frontend */}
            {frameworks.frontend?.length > 0 && (
              <div>
                <p className="text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">Frontend</p>
                <div className="flex flex-wrap gap-2">
                  {frameworks.frontend.map((fw: string, idx: number) => (
                    <span
                      key={idx}
                      className="inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium
                               bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200
                               border border-blue-200 dark:border-blue-700"
                    >
                      {fw}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Backend */}
            {frameworks.backend?.length > 0 && (
              <div>
                <p className="text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">Backend</p>
                <div className="flex flex-wrap gap-2">
                  {frameworks.backend.map((fw: string, idx: number) => (
                    <span
                      key={idx}
                      className="inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium
                               bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-200
                               border border-green-200 dark:border-green-700"
                    >
                      {fw}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Databases Section */}
      {databases.length > 0 && (
        <div className="bg-gradient-to-r from-orange-50 to-amber-50 dark:from-orange-900/20 dark:to-amber-900/20 rounded-lg p-5 border border-orange-200 dark:border-orange-800">
          <h4 className="text-md font-semibold text-slate-900 dark:text-white mb-3 flex items-center gap-2">
            <span>🗄️</span>
            Databases
          </h4>
          <div className="flex flex-wrap gap-2">
            {databases.map((db: string, idx: number) => (
              <span
                key={idx}
                className="inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium
                         bg-orange-100 dark:bg-orange-900/40 text-orange-800 dark:text-orange-200
                         border border-orange-200 dark:border-orange-700"
              >
                {db}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Complexity Stats */}
      {complexityStats && Object.keys(complexityStats).length > 0 && (
        <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-5 border border-slate-200 dark:border-slate-600">
          <h4 className="text-md font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
            <span>📊</span>
            Code Metrics
          </h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center p-3 bg-white dark:bg-slate-800 rounded-lg">
              <p className="text-2xl font-bold text-slate-900 dark:text-white">
                {(complexityStats.lines || 0).toLocaleString()}
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400">Total Lines</p>
            </div>
            <div className="text-center p-3 bg-white dark:bg-slate-800 rounded-lg">
              <p className="text-2xl font-bold text-slate-900 dark:text-white">
                {(complexityStats.files || 0).toLocaleString()}
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400">Source Files</p>
            </div>
            <div className="text-center p-3 bg-white dark:bg-slate-800 rounded-lg">
              <p className="text-2xl font-bold text-slate-900 dark:text-white">
                {(complexityStats.functions || 0).toLocaleString()}
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400">Functions</p>
            </div>
            <div className="text-center p-3 bg-white dark:bg-slate-800 rounded-lg">
              <p className="text-2xl font-bold text-slate-900 dark:text-white">
                {(complexityStats.classes || 0).toLocaleString()}
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400">Classes</p>
            </div>
          </div>
        </div>
      )}

      {/* README Preview */}
      {structureAnalysis?.readme && (
        <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-4 border border-slate-200 dark:border-slate-600">
          <h4 className="text-md font-semibold text-slate-900 dark:text-white mb-2 flex items-center gap-2">
            <span>📖</span>
            README Preview
          </h4>
          <div className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap max-h-64 overflow-y-auto font-mono bg-white dark:bg-slate-800 p-3 rounded">
            {structureAnalysis.readme.content?.substring(0, 500)}
            {structureAnalysis.readme.content?.length > 500 && '...'}
          </div>
        </div>
      )}
    </div>
  );
}
