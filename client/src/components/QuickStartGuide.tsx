interface QuickStartGuideProps {
  entryPoints: string[];
  keyFiles: string[];
  languages: { [key: string]: { count: number; lines: number } };
  dependencies: any;
  frameworks?: { frontend: string[]; backend: string[] };
  databases?: string[];
  readme?: { content: string };
  packageManager?: string;
  runScripts?: { [key: string]: string };
}

export default function QuickStartGuide({
  entryPoints,
  keyFiles,
  languages,
  dependencies,
  frameworks,
  databases,
  packageManager: detectedPM,
  runScripts,
}: QuickStartGuideProps) {
  // Categorize languages into frontend and backend
  const FRONTEND_LANGUAGES = new Set([
    'JavaScript', 'JavaScript (React)', 'TypeScript', 'TypeScript (React)',
    'Vue', 'Svelte',
  ]);
  const BACKEND_LANGUAGES = new Set([
    'Python', 'Java', 'Go', 'Rust', 'Ruby', 'PHP', 'C#',
    'Kotlin', 'Scala', 'C', 'C++', 'Swift',
  ]);

  const sortedLanguages = Object.entries(languages || {})
    .sort(([, a], [, b]) => b.lines - a.lines);

  const primaryFrontendLang = sortedLanguages.find(([lang]) => FRONTEND_LANGUAGES.has(lang))?.[0];
  const primaryBackendLang = sortedLanguages.find(([lang]) => BACKEND_LANGUAGES.has(lang))?.[0];
  const primaryLanguage = sortedLanguages[0]?.[0] || 'Unknown';

  // Show both frontend + backend languages for full-stack projects
  const displayLanguage = (primaryFrontendLang && primaryBackendLang)
    ? `${primaryFrontendLang.replace(' (React)', '')} + ${primaryBackendLang}`
    : primaryLanguage;

  // Get frameworks
  const frontendFrameworks = frameworks?.frontend || [];
  const backendFrameworks = frameworks?.backend || [];
  const allFrameworks = [...frontendFrameworks, ...backendFrameworks];
  const primaryFramework = frontendFrameworks[0] || backendFrameworks[0] || null;

  // Detect project characteristics
  const hasPkgJson = dependencies?.javascript && Object.keys(dependencies.javascript).length > 0;
  const hasRequirements = dependencies?.python && Object.keys(dependencies.python).length > 0;
  const hasGoMod = dependencies?.other?.['go.mod'];
  const hasCargo = dependencies?.other?.['Cargo.toml'];
  const hasPipfile = dependencies?.other?.['Pipfile'];
  const hasPoetry = dependencies?.other?.['pyproject.toml'];

  // Detect tooling
  const hasDocker = keyFiles.some(f => f.toLowerCase().includes('dockerfile') || f.toLowerCase().includes('docker-compose'));
  const hasDockerCompose = keyFiles.some(f => f.toLowerCase().includes('docker-compose'));
  const hasMakefile = keyFiles.some(f => f.toLowerCase() === 'makefile');
  const hasEnvExample = keyFiles.some(f => f.includes('.env.example') || f.includes('.env.sample'));

  // Use detected package manager from analysis, or fall back to npm
  const packageManager = detectedPM || 'npm';

  // Detect if project has separate client/server structure (full-stack)
  const hasClientDir = keyFiles.some(f => f.startsWith('client/') || f.startsWith('frontend/'));
  const hasServerDir = keyFiles.some(f => f.startsWith('server/') || f.startsWith('backend/') || f.startsWith('api/'));
  const isFullStackStructure = hasClientDir && hasServerDir;

  // Detect actual monorepo (workspaces-based, multiple independent packages)
  // A monorepo uses workspaces to manage multiple independent packages, not just client/server splits
  const jsDepKeys = Object.keys(dependencies?.javascript || {});
  const hasWorkspaces = jsDepKeys.some(k => k.includes('workspaces'));
  // Count distinct package.json locations (more than 2 suggests monorepo with multiple packages)
  const packageLocations = jsDepKeys
    .map(k => k.replace(/\/(dev)?[dD]ependencies$/, ''))
    .filter((v, i, a) => a.indexOf(v) === i);
  const hasMultiplePackages = packageLocations.length > 2;
  const isMonorepo = hasWorkspaces || hasMultiplePackages;

  // Determine project type
  const isFullStack = isFullStackStructure || (frontendFrameworks.length > 0 && backendFrameworks.length > 0);

  // Detect documentation
  const hasReadme = keyFiles.some(f => f.toLowerCase().startsWith('readme'));
  const hasContributing = keyFiles.some(f => f.toLowerCase() === 'contributing.md');
  const hasInstallDocs = keyFiles.some(f =>
    ['install.md', 'installation.md', 'setup.md', 'getting-started.md'].includes(f.toLowerCase())
  );
  const hasDocsFolder = keyFiles.some(f => f.toLowerCase().startsWith('docs/'));

  // Get suggested commands based on what we detect
  const getInstallCommand = () => {
    if (hasPkgJson) return `${packageManager} install`;
    if (hasPoetry) return 'poetry install';
    if (hasPipfile) return 'pipenv install';
    if (hasRequirements) return 'pip install -r requirements.txt';
    if (hasCargo) return 'cargo build';
    if (hasGoMod) return 'go mod download';
    return null;
  };

  const getRunCommand = () => {
    // Use actual scripts from package.json if available
    if (runScripts) {
      if (runScripts.dev) return `${packageManager} run dev`;
      if (runScripts.serve) return `${packageManager} run serve`;
      if (runScripts.start) return `${packageManager} start`;
    }

    // Fall back to framework-based guesses
    if (frontendFrameworks.includes('Next.js')) return `${packageManager} run dev`;
    if (frontendFrameworks.includes('React') || frontendFrameworks.includes('Vite')) return `${packageManager} run dev`;
    if (frontendFrameworks.includes('Vue.js')) return `${packageManager} run dev`;
    if (frontendFrameworks.includes('Angular')) return 'ng serve';
    if (backendFrameworks.includes('FastAPI')) return 'uvicorn main:app --reload';
    if (backendFrameworks.includes('Django')) return 'python manage.py runserver';
    if (backendFrameworks.includes('Flask')) return 'flask run';
    if (backendFrameworks.includes('Express.js')) return `${packageManager} start`;
    if (hasPkgJson) return `${packageManager} start`;
    if (hasRequirements && entryPoints[0]) return `python ${entryPoints[0]}`;
    if (hasCargo) return 'cargo run';
    if (hasGoMod && entryPoints[0]) return `go run ${entryPoints[0]}`;
    return null;
  };

  const installCommand = getInstallCommand();
  const runCommand = getRunCommand();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h3 className="text-lg font-semibold text-[var(--text-primary)] mb-2">
          🚀 Quick Start Guide
        </h3>
        <p className="text-sm text-[var(--text-secondary)]">
          Overview and suggested setup for this {primaryFramework || primaryLanguage} project
        </p>
      </div>

      {/* Important: Check Documentation First */}
      <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-xl p-4">
        <div className="flex items-start gap-3">
          <span className="text-xl">⚠️</span>
          <div>
            <h4 className="text-sm font-semibold text-amber-900 dark:text-amber-200 mb-1">
              Always check the official documentation first
            </h4>
            <p className="text-sm text-amber-700 dark:text-amber-300 mb-3">
              The commands below are <strong>estimates based on common patterns</strong>.
              Every project is different - please refer to the repository's documentation for accurate setup instructions.
            </p>
            <div className="flex flex-wrap gap-2">
              {hasReadme && (
                <span className="inline-flex items-center gap-1 px-3 py-1.5 bg-amber-100 dark:bg-amber-800/50 text-amber-800 dark:text-amber-200 rounded-lg text-sm font-medium">
                  📄 Read README.md first
                </span>
              )}
              {hasInstallDocs && (
                <span className="inline-flex items-center gap-1 px-3 py-1.5 bg-amber-100 dark:bg-amber-800/50 text-amber-800 dark:text-amber-200 rounded-lg text-sm font-medium">
                  📄 Check INSTALL/SETUP docs
                </span>
              )}
              {hasContributing && (
                <span className="inline-flex items-center gap-1 px-3 py-1.5 bg-amber-100 dark:bg-amber-800/50 text-amber-800 dark:text-amber-200 rounded-lg text-sm font-medium">
                  📄 See CONTRIBUTING.md
                </span>
              )}
              {hasDocsFolder && (
                <span className="inline-flex items-center gap-1 px-3 py-1.5 bg-amber-100 dark:bg-amber-800/50 text-amber-800 dark:text-amber-200 rounded-lg text-sm font-medium">
                  📁 Browse docs/ folder
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Project Overview */}
      <div className="bg-gradient-to-br from-primary-50 to-accent-deepblue/10 dark:from-primary-900/20 dark:to-accent-deepblue/10 border border-primary-200 dark:border-primary-800 rounded-xl p-6">
        <h4 className="text-md font-semibold text-[var(--text-primary)] mb-3">
          📋 Project Overview
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <p className="text-sm text-[var(--text-secondary)]">{primaryFrontendLang && primaryBackendLang ? 'Languages' : 'Language'}</p>
            <p className="text-lg font-semibold text-[var(--text-primary)]">{displayLanguage}</p>
          </div>
          <div>
            <p className="text-sm text-[var(--text-secondary)]">Type</p>
            <p className="text-lg font-semibold text-[var(--text-primary)]">
              {isMonorepo ? 'Monorepo' : isFullStack ? 'Full Stack' : frontendFrameworks.length > 0 ? 'Frontend' : backendFrameworks.length > 0 ? 'Backend' : 'Project'}
            </p>
          </div>
          {hasPkgJson && (
            <div>
              <p className="text-sm text-[var(--text-secondary)]">Package Manager</p>
              <p className="text-lg font-semibold text-[var(--text-primary)]">{packageManager}</p>
            </div>
          )}
          {databases && databases.length > 0 && (
            <div>
              <p className="text-sm text-[var(--text-secondary)]">Database</p>
              <p className="text-lg font-semibold text-[var(--text-primary)]">{databases[0]}</p>
            </div>
          )}
        </div>

        {/* Tech Stack */}
        {(allFrameworks.length > 0 || hasDocker) && (
          <div className="mt-4 pt-4 border-t border-primary-200 dark:border-primary-700">
            <p className="text-sm text-[var(--text-secondary)] mb-2">Detected Tech Stack</p>
            <div className="flex flex-wrap gap-2">
              {frontendFrameworks.map((fw, idx) => (
                <span key={`fe-${idx}`} className="px-3 py-1 rounded-full text-sm font-medium bg-accent-blue/20 text-accent-blue">
                  🎨 {fw}
                </span>
              ))}
              {backendFrameworks.map((fw, idx) => (
                <span key={`be-${idx}`} className="px-3 py-1 rounded-full text-sm font-medium bg-accent-green/20 text-accent-green">
                  ⚙️ {fw}
                </span>
              ))}
              {databases?.map((db, idx) => (
                <span key={`db-${idx}`} className="px-3 py-1 rounded-full text-sm font-medium bg-accent-orange/20 text-accent-orange">
                  🗄️ {db}
                </span>
              ))}
              {hasDocker && (
                <span className="px-3 py-1 rounded-full text-sm font-medium bg-cyan-100 dark:bg-cyan-900/40 text-cyan-700 dark:text-cyan-300">
                  🐳 Docker
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Suggested Commands */}
      <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h4 className="text-md font-semibold text-[var(--text-primary)]">
            💻 Suggested Commands
          </h4>
          <span className="text-xs px-2 py-1 bg-[var(--bg-tertiary)] text-[var(--text-muted)] rounded-lg">
            May vary - check docs
          </span>
        </div>

        <div className="space-y-4">
          {/* Docker option if available */}
          {hasDockerCompose && (
            <div className="p-3 bg-cyan-50 dark:bg-cyan-900/20 border border-cyan-200 dark:border-cyan-800 rounded-xl">
              <div className="flex items-center gap-2 mb-2">
                <span>🐳</span>
                <span className="font-medium text-cyan-900 dark:text-cyan-200">Docker (if supported)</span>
                <span className="text-xs px-1.5 py-0.5 bg-cyan-200 dark:bg-cyan-800 text-cyan-700 dark:text-cyan-300 rounded">recommended</span>
              </div>
              <code className="block bg-[#0F172A] text-accent-green px-3 py-2 rounded-lg text-sm font-mono">
                docker-compose up
              </code>
            </div>
          )}

          {/* Makefile option */}
          {hasMakefile && (
            <div className="p-3 bg-accent-deepblue/10 border border-accent-deepblue/30 rounded-xl">
              <div className="flex items-center gap-2 mb-2">
                <span>📜</span>
                <span className="font-medium text-accent-deepblue">Makefile available</span>
              </div>
              <code className="block bg-[#0F172A] text-accent-green px-3 py-2 rounded-lg text-sm font-mono">
                make help  # or check Makefile for commands
              </code>
            </div>
          )}

          {/* Standard install/run */}
          {(installCommand || runCommand) && (
            <div className="space-y-3">
              {hasEnvExample && (
                <div>
                  <p className="text-sm font-medium text-[var(--text-primary)] mb-1">1. Setup environment</p>
                  <code className="block bg-[#0F172A] text-accent-green px-3 py-2 rounded-lg text-sm font-mono">
                    cp .env.example .env  # then edit .env
                  </code>
                </div>
              )}

              {installCommand && (
                <div>
                  <p className="text-sm font-medium text-[var(--text-primary)] mb-1">
                    {hasEnvExample ? '2.' : '1.'} Install dependencies
                  </p>
                  <code className="block bg-[#0F172A] text-accent-green px-3 py-2 rounded-lg text-sm font-mono">
                    {installCommand}
                  </code>
                </div>
              )}

              {runCommand && (
                <div>
                  <p className="text-sm font-medium text-[var(--text-primary)] mb-1">
                    {hasEnvExample ? '3.' : installCommand ? '2.' : '1.'} Run the project
                  </p>
                  <code className="block bg-[#0F172A] text-accent-green px-3 py-2 rounded-lg text-sm font-mono">
                    {runCommand}
                  </code>
                  <p className="text-xs text-[var(--text-muted)] mt-1">
                    ⚠️ This is a guess based on {primaryFramework || primaryLanguage}. Check package.json scripts or README for actual command.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Full-stack project note */}
          {isFullStackStructure && !isMonorepo && (
            <div className="p-3 bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-200 dark:border-indigo-800 rounded-xl">
              <div className="flex items-start gap-2">
                <span>🔗</span>
                <div>
                  <span className="font-medium text-indigo-900 dark:text-indigo-200">Full-stack project</span>
                  <p className="text-sm text-indigo-700 dark:text-indigo-300 mt-1">
                    This project has separate client and server directories. You'll likely need to run install and start commands in each directory separately. Check the README for specific instructions.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Monorepo note */}
          {isMonorepo && (
            <div className="p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-xl">
              <div className="flex items-start gap-2">
                <span>📦</span>
                <div>
                  <span className="font-medium text-amber-900 dark:text-amber-200">Monorepo detected</span>
                  <p className="text-sm text-amber-700 dark:text-amber-300 mt-1">
                    This project uses a monorepo structure with multiple packages. Each package may have its own dependencies and scripts. Check the README or root package.json for workspace setup instructions.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* No commands detected */}
          {!installCommand && !runCommand && !hasDockerCompose && !hasMakefile && (
            <div className="text-center py-6 text-[var(--text-secondary)]">
              <p>Unable to determine setup commands automatically.</p>
              <p className="text-sm mt-1">Please check the repository's README or documentation.</p>
            </div>
          )}
        </div>
      </div>

      {/* Entry Points */}
      {entryPoints.length > 0 && (
        <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-xl p-6">
          <h4 className="text-md font-semibold text-[var(--text-primary)] mb-4">
            🎯 Entry Points
          </h4>
          <p className="text-sm text-[var(--text-secondary)] mb-3">
            Start exploring the codebase from these files:
          </p>
          <div className="space-y-2">
            {entryPoints.slice(0, 5).map((file, idx) => (
              <div key={idx} className="flex items-center gap-2 text-sm bg-accent-green/10 border border-accent-green/30 rounded-lg px-3 py-2">
                <span className="text-accent-green">📄</span>
                <code className="font-mono text-[var(--text-primary)]">{file}</code>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Quick Tips */}
      <div className="bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded-xl p-4">
        <h4 className="text-sm font-semibold text-[var(--text-primary)] mb-2 flex items-center gap-2">
          <span>💡</span> Tips
        </h4>
        <ul className="space-y-1 text-sm text-[var(--text-secondary)]">
          {hasReadme && <li>• Start by reading the <strong>README.md</strong></li>}
          {databases && databases.length > 0 && <li>• Ensure <strong>{databases[0]}</strong> is running before starting</li>}
          {primaryFramework && <li>• This uses <strong>{primaryFramework}</strong> - check their docs if unfamiliar</li>}
          <li>• Use the <strong>Chat tab</strong> to ask questions about this codebase</li>
          <li>• Use the <strong>Search tab</strong> to find specific code by concept</li>
        </ul>
      </div>
    </div>
  );
}
