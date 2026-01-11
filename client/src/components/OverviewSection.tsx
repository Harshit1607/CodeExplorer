
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

      {structureAnalysis?.readme && (
        <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-4 border border-slate-200 dark:border-slate-600">
          <h4 className="text-md font-semibold text-slate-900 dark:text-white mb-2 flex items-center gap-2">
            <span>📖</span>
            README Preview
          </h4>
          <div className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap max-h-64 overflow-y-auto">
            {structureAnalysis.readme.content?.substring(0, 500)}
            {structureAnalysis.readme.content?.length > 500 && '...'}
          </div>
        </div>
      )}

      {structureAnalysis?.license && (
        <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-4 border border-slate-200 dark:border-slate-600">
          <h4 className="text-md font-semibold text-slate-900 dark:text-white mb-2 flex items-center gap-2">
            <span>📜</span>
            License
          </h4>
          <p className="text-sm text-slate-700 dark:text-slate-300">
            <strong>Type:</strong> {structureAnalysis.license.type}
          </p>
          <p className="text-xs text-slate-600 dark:text-slate-400 mt-2">
            File: {structureAnalysis.license.file}
          </p>
        </div>
      )}
    </div>
  );
}
