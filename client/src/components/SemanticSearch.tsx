import { useState } from 'react';
import axios from 'axios';

interface SearchResult {
  type: string;
  name: string;
  file_path: string;
  context: string;
  score: number;
}

interface SearchResponse {
  query: string;
  total_results: number;
  results: SearchResult[];
  grouped: { [key: string]: SearchResult[] };
}

interface SemanticSearchProps {
  analysisData: any;
}

export default function SemanticSearch({ analysisData }: SemanticSearchProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || isLoading) return;

    setIsLoading(true);
    setError('');

    try {
      const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      const response = await axios.post(`${API_BASE_URL}/api/search`, {
        query: query.trim(),
        analysis_data: analysisData,
      });

      setResults(response.data);
    } catch (err: any) {
      console.error('Search error:', err);
      setError(err.response?.data?.detail || 'Search failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'file': return '📄';
      case 'function': return '⚡';
      case 'class': return '🔷';
      case 'import': return '📦';
      default: return '📌';
    }
  };

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'file': return 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300';
      case 'function': return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300';
      case 'class': return 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300';
      case 'import': return 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300';
      default: return 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300';
    }
  };

  const suggestedSearches = [
    "authentication logic",
    "database queries",
    "API endpoints",
    "error handling",
    "configuration",
    "utility functions",
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2 flex items-center gap-2">
          <span>🔍</span> Semantic Search
        </h3>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Search for code by concept - find authentication, API endpoints, error handling, and more
        </p>
      </div>

      {/* Search Form */}
      <form onSubmit={handleSearch} className="space-y-4">
        <div className="relative">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by concept (e.g., 'authentication', 'database queries')..."
            disabled={isLoading}
            className="w-full pl-12 pr-4 py-3 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-600 rounded-xl
                     text-slate-900 dark:text-white placeholder-slate-400
                     focus:ring-2 focus:ring-blue-500 focus:border-transparent
                     disabled:opacity-50 disabled:cursor-not-allowed"
          />
          <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
            <svg className="h-5 w-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>
        </div>

        {/* Suggested Searches */}
        <div className="flex flex-wrap gap-2">
          <span className="text-xs text-slate-500 dark:text-slate-400">Try:</span>
          {suggestedSearches.map((search, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => setQuery(search)}
              className="px-3 py-1 text-xs bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded-full hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
            >
              {search}
            </button>
          ))}
        </div>

        <button
          type="submit"
          disabled={isLoading || !query.trim()}
          className="w-full bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700
                   text-white font-medium py-3 px-6 rounded-xl
                   disabled:opacity-50 disabled:cursor-not-allowed
                   transition-all duration-200 flex items-center justify-center gap-2"
        >
          {isLoading ? (
            <>
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
              Searching...
            </>
          ) : (
            <>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              Search
            </>
          )}
        </button>
      </form>

      {/* Error */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
          <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
        </div>
      )}

      {/* Results */}
      {results && (
        <div className="space-y-4">
          {/* Results Summary */}
          <div className="flex items-center justify-between">
            <p className="text-sm text-slate-600 dark:text-slate-400">
              Found <span className="font-semibold text-slate-900 dark:text-white">{results.total_results}</span> results for "{results.query}"
            </p>
          </div>

          {results.total_results === 0 ? (
            <div className="text-center py-8">
              <div className="text-4xl mb-3">🔍</div>
              <p className="text-slate-600 dark:text-slate-400">No results found. Try a different search term.</p>
            </div>
          ) : (
            <>
              {/* Grouped Results */}
              <div className="grid gap-4 md:grid-cols-2">
                {Object.entries(results.grouped).map(([type, items]) => (
                  <div key={type} className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-4">
                    <h4 className="text-sm font-semibold text-slate-900 dark:text-white mb-3 flex items-center gap-2">
                      <span>{getTypeIcon(type)}</span>
                      {type.charAt(0).toUpperCase() + type.slice(1)}s
                      <span className="text-xs font-normal text-slate-500">({items.length})</span>
                    </h4>
                    <ul className="space-y-2">
                      {items.slice(0, 5).map((item, idx) => (
                        <li key={idx} className="flex items-start gap-2">
                          <span className={`px-1.5 py-0.5 text-[10px] font-medium rounded ${getTypeColor(type)}`}>
                            {Math.round(item.score)}
                          </span>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-slate-900 dark:text-white truncate">
                              {item.name}
                            </p>
                            <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
                              {item.context}
                            </p>
                          </div>
                        </li>
                      ))}
                      {items.length > 5 && (
                        <li className="text-xs text-slate-500 dark:text-slate-400 pl-6">
                          +{items.length - 5} more
                        </li>
                      )}
                    </ul>
                  </div>
                ))}
              </div>

              {/* All Results List */}
              <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
                <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50">
                  <h4 className="text-sm font-semibold text-slate-900 dark:text-white">All Results (by relevance)</h4>
                </div>
                <div className="max-h-[400px] overflow-y-auto">
                  {results.results.map((result, idx) => (
                    <div
                      key={idx}
                      className="flex items-center gap-3 px-4 py-3 border-b border-slate-100 dark:border-slate-700/50 last:border-b-0 hover:bg-slate-50 dark:hover:bg-slate-700/30"
                    >
                      <span className="text-lg">{getTypeIcon(result.type)}</span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-slate-900 dark:text-white truncate">
                            {result.name}
                          </span>
                          <span className={`px-1.5 py-0.5 text-[10px] font-medium rounded ${getTypeColor(result.type)}`}>
                            {result.type}
                          </span>
                        </div>
                        <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
                          {result.file_path}
                        </p>
                      </div>
                      <div className="text-xs text-slate-400 dark:text-slate-500">
                        {Math.round(result.score)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
