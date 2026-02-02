import { useState } from 'react';
import RepositoryInput from './components/RepositoryInput';
import AnalysisResults from './components/AnalysisResults';
import { useTheme } from './context/ThemeContext';

function App() {
  const [analysisData, setAnalysisData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);
  const { theme, toggleTheme } = useTheme();

  const handleAnalysisComplete = (data: any) => {
    setAnalysisData(data);
  };

  return (
    <div className="min-h-screen flex flex-col bg-[var(--bg-primary)]">
      <header className="bg-[var(--bg-secondary)] shadow-sm border-b border-[var(--border-color)]">
        <div className="px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-primary-500 to-accent-deepblue rounded-xl flex items-center justify-center shadow-lg shadow-primary-500/25">
                <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                </svg>
              </div>
              <div>
                <h1 className="text-2xl font-bold text-[var(--text-primary)]">
                  CodeExplorer
                </h1>
                <p className="text-xs text-[var(--text-secondary)]">
                  Repository-grounded codebase intelligence
                </p>
              </div>
            </div>

            {/* Theme Toggle */}
            <button
              onClick={toggleTheme}
              className="relative flex items-center gap-2 px-3 py-2 rounded-xl bg-[var(--bg-tertiary)] border border-[var(--border-color)] hover:border-primary-400 transition-all duration-200"
              aria-label="Toggle theme"
            >
              <div className="flex items-center gap-2">
                {/* Sun icon */}
                <svg
                  className={`w-4 h-4 transition-all duration-200 ${
                    theme === 'light' ? 'text-amber-500' : 'text-[var(--text-muted)]'
                  }`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"
                  />
                </svg>

                {/* Toggle track */}
                <div className="relative w-10 h-5 rounded-full bg-[var(--border-color)] transition-colors duration-200">
                  <div
                    className={`absolute top-0.5 w-4 h-4 rounded-full bg-primary-500 shadow-md transition-all duration-200 ${
                      theme === 'dark' ? 'left-5' : 'left-0.5'
                    }`}
                  />
                </div>

                {/* Moon icon */}
                <svg
                  className={`w-4 h-4 transition-all duration-200 ${
                    theme === 'dark' ? 'text-primary-400' : 'text-[var(--text-muted)]'
                  }`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"
                  />
                </svg>
              </div>
            </button>
          </div>
        </div>
      </header>

      <main className={`flex-1 max-w-[1800px] mx-auto px-4 sm:px-6 lg:px-8 w-full ${
        !analysisData && !isLoading ? 'flex flex-col justify-center py-8' : 'py-8'
      }`}>
        <div className={!analysisData && !isLoading ? 'w-full' : ''}>
          <RepositoryInput
            onAnalysisComplete={handleAnalysisComplete}
            isLoading={isLoading}
            setIsLoading={setIsLoading}
          />

          {isLoading && (
            <div className="mt-8 text-center">
              <div className="inline-flex items-center gap-3 bg-[var(--bg-secondary)] px-6 py-4 rounded-xl shadow-lg border border-[var(--border-color)]">
                <div className="animate-spin rounded-full h-6 w-6 border-2 border-primary-500 border-t-transparent"></div>
                <span className="text-[var(--text-primary)]">Analyzing repository...</span>
              </div>
            </div>
          )}
        </div>

        {analysisData && !isLoading && (
          <AnalysisResults data={analysisData} />
        )}
      </main>

      <footer className="mt-auto border-t border-[var(--border-color)] bg-[var(--bg-secondary)]">
        <div className="max-w-[1800px] mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <p className="text-center text-sm text-[var(--text-secondary)]">
            CodeExplorer - Free repository analysis tool
          </p>
        </div>
      </footer>
    </div>
  );
}

export default App;
