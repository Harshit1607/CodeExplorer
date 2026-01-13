interface QuickStartGuideProps {
  entryPoints: string[];
  keyFiles: string[];
  languages: { [key: string]: { count: number; lines: number } };
  dependencies: any;
  readme?: { content: string };
}

export default function QuickStartGuide({
  entryPoints,
  keyFiles,
  languages,
  dependencies,
  readme,
}: QuickStartGuideProps) {
  // Determine primary language
  const primaryLanguage = Object.entries(languages || {})
    .sort(([, a], [, b]) => b.lines - a.lines)[0]?.[0] || 'Unknown';

  // Get setup files
  const setupFiles = keyFiles.filter(f =>
    f.toLowerCase().includes('package.json') ||
    f.toLowerCase().includes('requirements.txt') ||
    f.toLowerCase().includes('cargo.toml') ||
    f.toLowerCase().includes('go.mod') ||
    f.toLowerCase().includes('pom.xml')
  );

  // Detect framework
  const detectFramework = () => {
    const deps = dependencies?.javascript?.production || [];
    const pythonDeps = dependencies?.python?.['requirements.txt'] || [];

    if (deps.includes('react')) return 'React';
    if (deps.includes('next')) return 'Next.js';
    if (deps.includes('vue')) return 'Vue.js';
    if (deps.includes('express')) return 'Express.js';
    if (pythonDeps.some((d: string) => d.includes('django'))) return 'Django';
    if (pythonDeps.some((d: string) => d.includes('flask'))) return 'Flask';
    if (pythonDeps.some((d: string) => d.includes('fastapi'))) return 'FastAPI';

    return null;
  };

  const framework = detectFramework();

  // Generate installation command
  const getInstallCommand = () => {
    if (setupFiles.some(f => f.includes('package.json'))) {
      return 'npm install';
    }
    if (setupFiles.some(f => f.includes('requirements.txt'))) {
      return 'pip install -r requirements.txt';
    }
    if (setupFiles.some(f => f.includes('Cargo.toml'))) {
      return 'cargo build';
    }
    if (setupFiles.some(f => f.includes('go.mod'))) {
      return 'go mod download';
    }
    return 'Check README for setup instructions';
  };

  // Generate run command
  const getRunCommand = () => {
    if (framework === 'Next.js') return 'npm run dev';
    if (framework === 'React') return 'npm start';
    if (framework === 'Express.js') return 'npm start';
    if (framework === 'Django') return 'python manage.py runserver';
    if (framework === 'Flask' || framework === 'FastAPI') return 'python app.py';
    if (primaryLanguage === 'Python' && entryPoints.length > 0) {
      return `python ${entryPoints[0]}`;
    }
    if (primaryLanguage === 'JavaScript' && entryPoints.length > 0) {
      return `node ${entryPoints[0]}`;
    }
    return 'Check README for run instructions';
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">
          🚀 Quick Start Guide
        </h3>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Auto-generated onboarding guide based on repository analysis
        </p>
      </div>

      {/* Project Overview */}
      <div className="bg-gradient-to-br from-blue-50 to-purple-50 dark:from-blue-900/20 dark:to-purple-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-6">
        <h4 className="text-md font-semibold text-slate-900 dark:text-white mb-3">
          📋 Project Overview
        </h4>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-sm text-slate-600 dark:text-slate-400">Primary Language</p>
            <p className="text-lg font-semibold text-slate-900 dark:text-white">{primaryLanguage}</p>
          </div>
          {framework && (
            <div>
              <p className="text-sm text-slate-600 dark:text-slate-400">Framework</p>
              <p className="text-lg font-semibold text-slate-900 dark:text-white">{framework}</p>
            </div>
          )}
          <div>
            <p className="text-sm text-slate-600 dark:text-slate-400">Entry Points</p>
            <p className="text-lg font-semibold text-slate-900 dark:text-white">{entryPoints.length}</p>
          </div>
          <div>
            <p className="text-sm text-slate-600 dark:text-slate-400">Languages Used</p>
            <p className="text-lg font-semibold text-slate-900 dark:text-white">
              {Object.keys(languages || {}).length}
            </p>
          </div>
        </div>
      </div>

      {/* Setup Steps */}
      <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-6">
        <h4 className="text-md font-semibold text-slate-900 dark:text-white mb-4">
          ⚙️ Setup Steps
        </h4>
        <ol className="space-y-4">
          <li className="flex gap-4">
            <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-500 text-white flex items-center justify-center font-semibold">
              1
            </div>
            <div className="flex-1">
              <p className="font-medium text-slate-900 dark:text-white mb-1">Clone the repository</p>
              <code className="block bg-slate-100 dark:bg-slate-700 px-3 py-2 rounded text-sm font-mono">
                git clone &lt;repository-url&gt;
              </code>
            </div>
          </li>

          <li className="flex gap-4">
            <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-500 text-white flex items-center justify-center font-semibold">
              2
            </div>
            <div className="flex-1">
              <p className="font-medium text-slate-900 dark:text-white mb-1">Install dependencies</p>
              <code className="block bg-slate-100 dark:bg-slate-700 px-3 py-2 rounded text-sm font-mono">
                {getInstallCommand()}
              </code>
            </div>
          </li>

          <li className="flex gap-4">
            <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-500 text-white flex items-center justify-center font-semibold">
              3
            </div>
            <div className="flex-1">
              <p className="font-medium text-slate-900 dark:text-white mb-1">Run the application</p>
              <code className="block bg-slate-100 dark:bg-slate-700 px-3 py-2 rounded text-sm font-mono">
                {getRunCommand()}
              </code>
            </div>
          </li>
        </ol>
      </div>

      {/* Key Files to Explore */}
      <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-6">
        <h4 className="text-md font-semibold text-slate-900 dark:text-white mb-4">
          📁 Start Exploring Here
        </h4>
        <div className="space-y-3">
          {entryPoints.length > 0 && (
            <div>
              <p className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                Entry Points (Start Here):
              </p>
              <div className="space-y-2">
                {entryPoints.slice(0, 3).map((file, idx) => (
                  <div
                    key={idx}
                    className="flex items-center gap-2 text-sm bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded px-3 py-2"
                  >
                    <span className="text-green-600 dark:text-green-400">🎯</span>
                    <code className="font-mono text-slate-900 dark:text-white">{file}</code>
                  </div>
                ))}
              </div>
            </div>
          )}

          {setupFiles.length > 0 && (
            <div>
              <p className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                Configuration Files:
              </p>
              <div className="space-y-2">
                {setupFiles.slice(0, 3).map((file, idx) => (
                  <div
                    key={idx}
                    className="flex items-center gap-2 text-sm bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded px-3 py-2"
                  >
                    <span className="text-blue-600 dark:text-blue-400">⚙️</span>
                    <code className="font-mono text-slate-900 dark:text-white">{file}</code>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Pro Tips */}
      <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
        <h4 className="text-sm font-semibold text-amber-900 dark:text-amber-200 mb-2 flex items-center gap-2">
          <span>💡</span>
          Pro Tips for Understanding This Codebase
        </h4>
        <ul className="space-y-2 text-sm text-amber-800 dark:text-amber-300">
          <li>
            • Start with <strong>{entryPoints[0] || 'the main entry point'}</strong> to understand the application flow
          </li>
          <li>
            • Check the <strong>Dependencies tab</strong> to see what libraries are used
          </li>
          <li>
            • Review <strong>high complexity files</strong> in the Complexity tab - these may be core logic
          </li>
          {framework && (
            <li>
              • This is a <strong>{framework}</strong> project - familiarize yourself with its patterns
            </li>
          )}
          <li>
            • Use the <strong>File Structure</strong> visualization to navigate the codebase
          </li>
        </ul>
      </div>
    </div>
  );
}
