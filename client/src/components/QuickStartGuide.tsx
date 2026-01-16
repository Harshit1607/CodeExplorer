interface QuickStartGuideProps {
  entryPoints: string[];
  keyFiles: string[];
  languages: { [key: string]: { count: number; lines: number } };
  dependencies: any;
  frameworks?: { frontend: string[]; backend: string[] };
  databases?: string[];
  readme?: { content: string };
}

export default function QuickStartGuide({
  entryPoints,
  keyFiles,
  languages,
  dependencies,
  frameworks,
  databases,
  readme,
}: QuickStartGuideProps) {
  // Determine primary language
  const primaryLanguage = Object.entries(languages || {})
    .sort(([, a], [, b]) => b.lines - a.lines)[0]?.[0] || 'Unknown';

  // Get all frameworks from backend detection
  const frontendFrameworks = frameworks?.frontend || [];
  const backendFrameworks = frameworks?.backend || [];
  const allFrameworks = [...frontendFrameworks, ...backendFrameworks];
  const primaryFramework = frontendFrameworks[0] || backendFrameworks[0] || null;

  // Check for dependency files
  const hasPkgJson = dependencies?.javascript && Object.keys(dependencies.javascript).length > 0;
  const hasRequirements = dependencies?.python && Object.keys(dependencies.python).length > 0;
  const hasGoMod = dependencies?.other?.['go.mod'];
  const hasCargo = dependencies?.other?.['Cargo.toml'];

  // Generate installation command
  const getInstallCommand = () => {
    if (hasPkgJson) {
      return 'npm install';
    }
    if (hasRequirements) {
      return 'pip install -r requirements.txt';
    }
    if (hasCargo) {
      return 'cargo build';
    }
    if (hasGoMod) {
      return 'go mod download';
    }
    return 'Check README for setup instructions';
  };

  // Generate run command based on detected frameworks
  const getRunCommand = () => {
    // Frontend frameworks
    if (frontendFrameworks.includes('Next.js')) return 'npm run dev';
    if (frontendFrameworks.includes('React') || frontendFrameworks.includes('Vite')) return 'npm run dev';
    if (frontendFrameworks.includes('Vue.js')) return 'npm run dev';
    if (frontendFrameworks.includes('Angular')) return 'ng serve';
    if (frontendFrameworks.includes('Svelte') || frontendFrameworks.includes('SvelteKit')) return 'npm run dev';

    // Backend frameworks
    if (backendFrameworks.includes('FastAPI')) return 'uvicorn main:app --reload';
    if (backendFrameworks.includes('Django')) return 'python manage.py runserver';
    if (backendFrameworks.includes('Flask')) return 'flask run';
    if (backendFrameworks.includes('Express.js')) return 'npm start';
    if (backendFrameworks.includes('NestJS')) return 'npm run start:dev';
    if (backendFrameworks.includes('Spring Boot')) return 'mvn spring-boot:run';
    if (backendFrameworks.includes('Gin (Go)') || backendFrameworks.includes('Fiber (Go)')) return 'go run main.go';
    if (backendFrameworks.includes('Ruby on Rails')) return 'rails server';
    if (backendFrameworks.includes('Laravel')) return 'php artisan serve';

    // Fallback based on language
    if (primaryLanguage.includes('Python') && entryPoints.length > 0) {
      return `python ${entryPoints[0]}`;
    }
    if ((primaryLanguage.includes('JavaScript') || primaryLanguage.includes('TypeScript')) && entryPoints.length > 0) {
      return `node ${entryPoints[0]}`;
    }
    if (primaryLanguage === 'Go' && entryPoints.length > 0) {
      return `go run ${entryPoints[0]}`;
    }
    if (primaryLanguage === 'Rust') {
      return 'cargo run';
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
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <p className="text-sm text-slate-600 dark:text-slate-400">Primary Language</p>
            <p className="text-lg font-semibold text-slate-900 dark:text-white">{primaryLanguage}</p>
          </div>
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
          {databases && databases.length > 0 && (
            <div>
              <p className="text-sm text-slate-600 dark:text-slate-400">Database</p>
              <p className="text-lg font-semibold text-slate-900 dark:text-white">{databases[0]}</p>
            </div>
          )}
        </div>

        {/* Tech Stack */}
        {allFrameworks.length > 0 && (
          <div className="mt-4 pt-4 border-t border-blue-200 dark:border-blue-700">
            <p className="text-sm text-slate-600 dark:text-slate-400 mb-2">Tech Stack</p>
            <div className="flex flex-wrap gap-2">
              {frontendFrameworks.map((fw, idx) => (
                <span
                  key={`fe-${idx}`}
                  className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium
                           bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200"
                >
                  {fw}
                </span>
              ))}
              {backendFrameworks.map((fw, idx) => (
                <span
                  key={`be-${idx}`}
                  className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium
                           bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-200"
                >
                  {fw}
                </span>
              ))}
              {databases?.map((db, idx) => (
                <span
                  key={`db-${idx}`}
                  className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium
                           bg-orange-100 dark:bg-orange-900/40 text-orange-800 dark:text-orange-200"
                >
                  {db}
                </span>
              ))}
            </div>
          </div>
        )}
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

          {keyFiles.length > 0 && (
            <div>
              <p className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                Key Files:
              </p>
              <div className="space-y-2">
                {keyFiles.slice(0, 5).map((file, idx) => (
                  <div
                    key={idx}
                    className="flex items-center gap-2 text-sm bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded px-3 py-2"
                  >
                    <span className="text-blue-600 dark:text-blue-400">📄</span>
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
          {primaryFramework && (
            <li>
              • This is a <strong>{primaryFramework}</strong> project - familiarize yourself with its patterns
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
