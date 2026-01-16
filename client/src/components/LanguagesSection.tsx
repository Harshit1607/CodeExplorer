import LanguageChart from './LanguageChart';
import FileStatsChart from './FileStatsChart';

interface LanguagesSectionProps {
  languages: {
    [key: string]: {
      count: number;
      lines: number;
    };
  };
}

export default function LanguagesSection({ languages }: LanguagesSectionProps) {
  if (!languages || Object.keys(languages).length === 0) {
    return (
      <div className="text-center py-8 text-slate-500 dark:text-slate-400">
        No language data available
      </div>
    );
  }

  const totalLines = Object.values(languages).reduce((sum, lang) => sum + lang.lines, 0);
  const totalFiles = Object.values(languages).reduce((sum, lang) => sum + lang.count, 0);

  const languageColors: { [key: string]: string } = {
    'Python': '#3572A5',
    'JavaScript': '#f1e05a',
    'JavaScript (React)': '#61dafb',
    'TypeScript': '#2b7489',
    'TypeScript (React)': '#2b7489',
    'Java': '#b07219',
    'C++': '#f34b7d',
    'C': '#555555',
    'C/C++ Header': '#555555',
    'C++ Header': '#f34b7d',
    'Go': '#00ADD8',
    'Rust': '#dea584',
    'Ruby': '#701516',
    'PHP': '#4F5D95',
    'C#': '#178600',
    'Swift': '#ffac45',
    'Kotlin': '#A97BFF',
    'Scala': '#c22d40',
    'Vue': '#41b883',
    'Svelte': '#ff3e00',
    'HTML': '#e34c26',
    'CSS': '#563d7c',
    'SCSS': '#c6538c',
    'Markdown': '#083fa1',
    'JSON': '#292929',
    'YAML': '#cb171e',
  };

  const sortedLanguages = Object.entries(languages).sort(
    ([, a], [, b]) => b.lines - a.lines
  );

  return (
    <div className="space-y-8">
      <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
        Language Breakdown
      </h3>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-4 border border-slate-200 dark:border-slate-600">
          <p className="text-sm text-slate-600 dark:text-slate-400">Total Lines</p>
          <p className="text-3xl font-bold text-slate-900 dark:text-white">
            {totalLines.toLocaleString()}
          </p>
        </div>
        <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-4 border border-slate-200 dark:border-slate-600">
          <p className="text-sm text-slate-600 dark:text-slate-400">Total Files</p>
          <p className="text-3xl font-bold text-slate-900 dark:text-white">
            {totalFiles.toLocaleString()}
          </p>
        </div>
      </div>

      {/* Visualizations */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-6 border border-slate-200 dark:border-slate-600">
          <LanguageChart languages={languages} />
        </div>
        <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-6 border border-slate-200 dark:border-slate-600">
          <FileStatsChart languages={languages} />
        </div>
      </div>

      {/* Progress Bars */}
      <div className="space-y-4">
        <h4 className="text-md font-semibold text-slate-800 dark:text-slate-200">
          Distribution
        </h4>
        {sortedLanguages.map(([language, data]) => {
          const percentage = ((data.lines / totalLines) * 100).toFixed(1);
          const color = languageColors[language] || '#666666';

          return (
            <div key={language} className="space-y-2">
              <div className="flex justify-between items-center text-sm">
                <div className="flex items-center gap-2">
                  <div
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: color }}
                  />
                  <span className="font-medium text-slate-900 dark:text-white">
                    {language}
                  </span>
                </div>
                <span className="text-slate-600 dark:text-slate-400">
                  {percentage}% • {data.count} files • {data.lines.toLocaleString()} lines
                </span>
              </div>
              <div className="w-full bg-slate-200 dark:bg-slate-600 rounded-full h-2 overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${percentage}%`,
                    backgroundColor: color,
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
