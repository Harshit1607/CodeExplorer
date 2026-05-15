import { useState, useEffect } from 'react';

interface RepositoryInputProps {
  onAnalysisStart: (repoUrl: string) => void;
  isLoading: boolean;
  error?: string | null;
  status: 'idle' | 'connecting' | 'streaming' | 'complete' | 'error';
}

export default function RepositoryInput({
  onAnalysisStart,
  isLoading,
  error: externalError,
  status,
}: RepositoryInputProps) {
  const [repoUrl, setRepoUrl] = useState('');
  const [localError, setLocalError] = useState('');

  const error = externalError || localError;

  // Sync internal state with session storage or clear if idle
  useEffect(() => {
    const lastRepo = sessionStorage.getItem('codeexplorer_last_repo');
    if (lastRepo) {
      setRepoUrl(lastRepo);
    } else if (status === 'idle') {
      setRepoUrl('');
    }
  }, [status]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError('');

    if (!repoUrl.trim()) {
      setLocalError('Please enter a repository URL');
      return;
    }

    // Basic GitHub URL validation
    const githubRegex = /^https?:\/\/(www\.)?github\.com\/[\w-]+\/[\w.-]+\/?$/;
    if (!githubRegex.test(repoUrl.trim())) {
      setLocalError('Please enter a valid GitHub repository URL (e.g., https://github.com/user/repo)');
      return;
    }

    onAnalysisStart(repoUrl.trim());
  };

  const getRepoName = (url: string) => {
    try {
      const parts = url.replace(/\/$/, '').split('/');
      if (parts.length >= 2) {
        return `${parts[parts.length - 2]}/${parts[parts.length - 1]}`;
      }
      return url;
    } catch {
      return url;
    }
  };

  const isIdle = status === 'idle';

  if (!isIdle) {
    return (
      <div className="bg-[var(--bg-secondary)] rounded-2xl shadow-xl p-6 border border-[var(--border-color)] transition-all duration-300">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 bg-primary-500/10 rounded-xl flex items-center justify-center border border-primary-500/20">
              <svg className="w-6 h-6 text-primary-500" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 2C6.477 2 2 6.477 2 12c0 4.419 2.865 8.166 6.839 9.489.5.092.682-.217.682-.482 0-.237-.008-.866-.013-1.7-2.782.603-3.369-1.341-3.369-1.341-.454-1.152-1.11-1.459-1.11-1.459-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.294 2.747-1.025 2.747-1.025.546 1.377.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482C19.138 20.161 22 16.416 22 12c0-5.523-4.477-10-10-10z" />
              </svg>
            </div>
            <div>
              <p className="text-sm font-medium text-[var(--text-secondary)] mb-1">
                {status === 'complete' ? 'Analyzing Repository' : 'Currently Analyzing'}
              </p>
              <h2 className="text-xl font-bold text-[var(--text-primary)]">
                {getRepoName(repoUrl)}
              </h2>
            </div>
          </div>
          
          {status === 'error' && error && (
            <div className="flex-1 max-w-md">
              <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-3 flex items-center gap-3">
                 <svg className="w-5 h-5 text-red-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                   <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                 </svg>
                 <p className="text-sm text-red-500 truncate">{error}</p>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-[var(--bg-secondary)] rounded-xl shadow-lg p-6 border border-[var(--border-color)]">
      <div className="mb-4">
        <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-2">
          Analyze Repository
        </h2>
        <p className="text-sm text-[var(--text-secondary)]">
          Enter a public GitHub repository URL to analyze its structure, dependencies, and key files
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="repo-url" className="block text-sm font-medium text-[var(--text-primary)] mb-2">
            Repository URL
          </label>
          <input
            id="repo-url"
            type="text"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            placeholder="https://github.com/username/repository"
            disabled={isLoading}
            className="w-full px-4 py-3 border border-[var(--border-color)] rounded-xl
                     focus:ring-2 focus:ring-primary-500 focus:border-primary-500
                     bg-[var(--bg-tertiary)] text-[var(--text-primary)]
                     placeholder-[var(--text-muted)]
                     disabled:opacity-50 disabled:cursor-not-allowed
                     transition-all duration-200"
          />
        </div>

        {error && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-4">
            <div className="flex items-start gap-3">
              <svg className="w-5 h-5 text-red-600 dark:text-red-400 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
            </div>
          </div>
        )}

        <button
          type="submit"
          disabled={isLoading}
          className="w-full bg-[var(--text-primary)] hover:bg-[var(--text-secondary)]
                   text-[var(--bg-primary)] font-medium py-3 px-6 rounded-xl
                   disabled:opacity-50 disabled:cursor-not-allowed
                   transition-all duration-200 transform hover:scale-[1.02]
                   focus:outline-none focus:ring-2 focus:ring-[var(--text-primary)] focus:ring-offset-2
                   shadow-lg"
        >
          {isLoading ? 'Analyzing...' : 'Analyze Repository'}
        </button>
      </form>

      <div className="mt-6 pt-6 border-t border-[var(--border-color)]">
        <p className="text-xs text-[var(--text-secondary)]">
          <strong>Examples:</strong>
        </p>
        <ul className="mt-2 space-y-1">
          <li className="text-xs text-[var(--text-muted)]">
            • https://github.com/facebook/react
          </li>
          <li className="text-xs text-[var(--text-muted)]">
            • https://github.com/vercel/next.js
          </li>
        </ul>
      </div>
    </div>
  );
}
