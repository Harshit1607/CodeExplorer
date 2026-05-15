import { useEffect } from 'react';
import RepositoryInput from './components/RepositoryInput';
import AnalysisResults from './components/AnalysisResults';
import { useTheme } from './context/ThemeContext';
import { useAnalysis } from './hooks/useAnalysis';

function App() {
  const { theme, toggleTheme } = useTheme();
  const { state: analysisState, startAnalysis, resetAnalysis } = useAnalysis();

  const handleAnalysisStart = (repoUrl: string) => {
    startAnalysis(repoUrl, true);
  };

  useEffect(() => {
    const lastRepo = sessionStorage.getItem('codeexplorer_last_repo');
    if (lastRepo && analysisState.status === 'idle') {
      startAnalysis(lastRepo, false);
    }
  }, [startAnalysis]);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      document.documentElement.style.setProperty('--mouse-x', `${e.clientX}px`);
      document.documentElement.style.setProperty('--mouse-y', `${e.clientY}px`);
    };

    window.addEventListener('mousemove', handleMouseMove);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
    };
  }, []);

  const showResults = analysisState.status === 'streaming' || analysisState.status === 'complete';
  const showLoading = analysisState.status === 'connecting' || analysisState.status === 'streaming';

  return (
    <>
      <div className="mirrored-bg"></div>
      <div className="min-h-screen flex flex-col bg-transparent relative z-10">
        <header className="bg-[var(--bg-secondary)] shadow-sm border-b border-[var(--border-color)]">
          <div className="px-4 sm:px-6 lg:px-8 py-4">
            <div className="flex items-center justify-between">
              <div 
                className="flex items-center gap-3 cursor-pointer group"
                onClick={resetAnalysis}
                title="Go to Home / Start New Analysis"
              >
                <div className="w-10 h-10 bg-[var(--text-primary)] rounded-xl flex items-center justify-center shadow-lg group-hover:scale-105 transition-transform">
                  <svg className="w-6 h-6 text-[var(--bg-primary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                  </svg>
                </div>
                <div>
                  <h1 className="text-2xl font-bold text-[var(--text-primary)] group-hover:text-primary-500 transition-colors">
                    CodeExplorer
                  </h1>
                  <p className="text-xs text-[var(--text-secondary)]">
                    Repository-grounded codebase intelligence
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-4">
                {(showResults || showLoading) && (
                  <button
                    onClick={resetAnalysis}
                    className="px-4 py-2 text-sm font-medium text-[var(--text-primary)] bg-[var(--bg-tertiary)] border border-[var(--border-color)] hover:border-primary-400 hover:text-primary-500 rounded-lg transition-colors flex items-center gap-2"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
                    </svg>
                    New Analysis
                  </button>
                )}
                {/* Theme Toggle */}
              <button
                onClick={toggleTheme}
                className="relative flex items-center gap-2 px-3 py-2 rounded-xl bg-[var(--bg-tertiary)] border border-[var(--border-color)] hover:border-primary-400 transition-all duration-200"
                aria-label="Toggle theme"
              >
                <div className="flex items-center gap-2">
                  {/* Sun icon */}
                  <svg
                    className={`w-4 h-4 transition-all duration-200 ${theme === 'light' ? 'text-amber-500' : 'text-[var(--text-muted)]'
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
                      className={`absolute top-0.5 w-4 h-4 rounded-full bg-primary-500 shadow-md transition-all duration-200 ${theme === 'dark' ? 'left-5' : 'left-0.5'
                        }`}
                    />
                  </div>

                  {/* Moon icon */}
                  <svg
                    className={`w-4 h-4 transition-all duration-200 ${theme === 'dark' ? 'text-primary-400' : 'text-[var(--text-muted)]'
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
          </div>
        </header>

        <main className={`flex-1 max-w-[1800px] mx-auto px-4 sm:px-6 lg:px-8 w-full ${!showResults && !showLoading ? 'flex flex-col justify-center py-8' : 'py-8'
          }`}>
          <div className={!showResults && !showLoading ? 'w-full' : ''}>
            <RepositoryInput
              onAnalysisStart={handleAnalysisStart}
              isLoading={showLoading}
              error={analysisState.error}
              status={analysisState.status}
            />

            {showLoading && (
              <div className="mt-8">
                <div className="bg-[var(--bg-secondary)] p-6 rounded-xl shadow-lg border border-[var(--border-color)]">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-[var(--text-primary)]">{analysisState.stage}</span>
                    <span className="text-sm font-medium text-primary-500">{analysisState.progress}%</span>
                  </div>
                  <div className="w-full bg-[var(--bg-tertiary)] rounded-full h-2.5">
                    <div 
                      className="bg-primary-500 h-2.5 rounded-full transition-all duration-300" 
                      style={{ width: `${analysisState.progress}%` }}
                    ></div>
                  </div>
                  <div className="mt-4 max-h-32 overflow-y-auto text-xs text-[var(--text-muted)] space-y-1">
                    {analysisState.events.slice(0, 5).map((ev, i) => (
                      <div key={i}>✓ Received: {ev}</div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          {showResults && (
            <AnalysisResults state={analysisState} />
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
    </>
  );
}

export default App;
