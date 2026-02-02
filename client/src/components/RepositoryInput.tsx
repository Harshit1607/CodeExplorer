import { useState } from 'react';
import axios from 'axios';

interface RepositoryInputProps {
  onAnalysisComplete: (data: any) => void;
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
}

export default function RepositoryInput({
  onAnalysisComplete,
  isLoading,
  setIsLoading,
}: RepositoryInputProps) {
  const [repoUrl, setRepoUrl] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!repoUrl.trim()) {
      setError('Please enter a repository URL');
      return;
    }

    // Basic GitHub URL validation
    const githubRegex = /^https?:\/\/(www\.)?github\.com\/[\w-]+\/[\w.-]+\/?$/;
    if (!githubRegex.test(repoUrl.trim())) {
      setError('Please enter a valid GitHub repository URL (e.g., https://github.com/user/repo)');
      return;
    }

    setIsLoading(true);

    try {
      const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      const response = await axios.post(`${API_BASE_URL}/api/analyze`, {
        repo_url: repoUrl.trim(),
      });

      onAnalysisComplete(response.data);
    } catch (err: any) {
      console.error('Analysis error:', err);
      setError(
        err.response?.data?.detail ||
        'Failed to analyze repository. Please check the URL and try again.'
      );
    } finally {
      setIsLoading(false);
    }
  };

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
          className="w-full bg-gradient-to-r from-primary-600 to-accent-deepblue hover:from-primary-700 hover:to-blue-800
                   text-white font-medium py-3 px-6 rounded-xl
                   disabled:opacity-50 disabled:cursor-not-allowed
                   transition-all duration-200 transform hover:scale-[1.02]
                   focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2
                   shadow-lg shadow-primary-500/25"
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
