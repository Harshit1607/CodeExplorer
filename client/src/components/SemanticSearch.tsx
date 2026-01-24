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
  const [activeFilter, setActiveFilter] = useState<string | null>(null);

  const handleSearch = async (searchQuery?: string) => {
    const q = searchQuery || query;
    if (!q.trim() || isLoading) return;

    setIsLoading(true);
    setError('');
    setActiveFilter(null);

    try {
      const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      const response = await axios.post(`${API_BASE_URL}/api/search`, {
        query: q.trim(),
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

  const handleSuggestionClick = (suggestion: string) => {
    setQuery(suggestion);
    handleSearch(suggestion);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSearch();
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
      case 'function': return 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300';
      case 'class': return 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300';
      case 'import': return 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300';
      default: return 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300';
    }
  };

  const getScoreColor = (score: number) => {
    if (score >= 20) return 'text-green-600 dark:text-green-400';
    if (score >= 10) return 'text-blue-600 dark:text-blue-400';
    if (score >= 5) return 'text-amber-600 dark:text-amber-400';
    return 'text-slate-500 dark:text-slate-400';
  };

  const suggestedSearches = [
    { label: "Authentication", query: "auth login" },
    { label: "API Endpoints", query: "api endpoint route" },
    { label: "Database", query: "database query model" },
    { label: "Components", query: "component ui" },
    { label: "Utilities", query: "util helper" },
    { label: "Configuration", query: "config settings" },
    { label: "Error Handling", query: "error handle exception" },
    { label: "Testing", query: "test spec" },
  ];

  const filteredResults = activeFilter
    ? results?.results.filter(r => r.type === activeFilter) || []
    : results?.results || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2 flex items-center gap-2">
          <span>🔍</span> Semantic Code Search
        </h3>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Search by concept - finds related code even if names don't match exactly
        </p>
      </div>

      {/* Search Form */}
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g., 'authentication', 'database queries', 'error handling'..."
              disabled={isLoading}
              className="w-full pl-10 pr-4 py-3 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-600 rounded-xl
                       text-slate-900 dark:text-white placeholder-slate-400
                       focus:ring-2 focus:ring-blue-500 focus:border-transparent
                       disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <svg className="h-5 w-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
          </div>
          <button
            type="submit"
            disabled={isLoading || !query.trim()}
            className="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-xl
                     disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isLoading ? (
              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
            ) : (
              'Search'
            )}
          </button>
        </div>

        {/* Suggested Searches */}
        <div className="flex flex-wrap gap-2">
          {suggestedSearches.map((item, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => handleSuggestionClick(item.query)}
              disabled={isLoading}
              className="px-3 py-1.5 text-xs bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300
                       rounded-full hover:bg-blue-100 dark:hover:bg-blue-900/40 hover:text-blue-700 dark:hover:text-blue-300
                       transition-colors disabled:opacity-50"
            >
              {item.label}
            </button>
          ))}
        </div>
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
          {/* Results Header */}
          <div className="flex items-center justify-between flex-wrap gap-3">
            <p className="text-sm text-slate-600 dark:text-slate-400">
              Found <span className="font-semibold text-slate-900 dark:text-white">{results.total_results}</span> results
              for "<span className="font-medium">{results.query}</span>"
            </p>

            {/* Type Filters */}
            {results.total_results > 0 && (
              <div className="flex gap-1">
                <button
                  onClick={() => setActiveFilter(null)}
                  className={`px-3 py-1 text-xs rounded-full transition-colors ${
                    activeFilter === null
                      ? 'bg-blue-600 text-white'
                      : 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600'
                  }`}
                >
                  All ({results.total_results})
                </button>
                {Object.entries(results.grouped).map(([type, items]) => (
                  <button
                    key={type}
                    onClick={() => setActiveFilter(type)}
                    className={`px-3 py-1 text-xs rounded-full transition-colors flex items-center gap-1 ${
                      activeFilter === type
                        ? 'bg-blue-600 text-white'
                        : 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600'
                    }`}
                  >
                    <span>{getTypeIcon(type)}</span>
                    {type}s ({items.length})
                  </button>
                ))}
              </div>
            )}
          </div>

          {results.total_results === 0 ? (
            <div className="text-center py-12 bg-slate-50 dark:bg-slate-800/50 rounded-xl">
              <div className="text-4xl mb-3">🔍</div>
              <p className="text-slate-600 dark:text-slate-400 mb-2">No results found</p>
              <p className="text-sm text-slate-500 dark:text-slate-500">Try different keywords or browse the suggested searches above</p>
            </div>
          ) : (
            <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
              <div className="max-h-[500px] overflow-y-auto divide-y divide-slate-100 dark:divide-slate-700/50">
                {filteredResults.map((result, idx) => (
                  <div
                    key={idx}
                    className="flex items-start gap-3 px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors"
                  >
                    {/* Icon */}
                    <span className="text-xl mt-0.5">{getTypeIcon(result.type)}</span>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-slate-900 dark:text-white">
                          {result.name}
                        </span>
                        <span className={`px-2 py-0.5 text-[10px] font-medium rounded-full ${getTypeColor(result.type)}`}>
                          {result.type}
                        </span>
                      </div>
                      <p className="text-sm text-slate-500 dark:text-slate-400 truncate mt-0.5">
                        {result.file_path}
                      </p>
                    </div>

                    {/* Score */}
                    <div className={`text-sm font-medium ${getScoreColor(result.score)}`}>
                      {result.score}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Legend */}
          {results.total_results > 0 && (
            <div className="flex items-center justify-end gap-4 text-xs text-slate-500 dark:text-slate-400">
              <span>Relevance score:</span>
              <span className="text-green-600 dark:text-green-400">High (20+)</span>
              <span className="text-blue-600 dark:text-blue-400">Medium (10-19)</span>
              <span className="text-amber-600 dark:text-amber-400">Low (5-9)</span>
            </div>
          )}
        </div>
      )}

      {/* Empty State */}
      {!results && !isLoading && (
        <div className="text-center py-12 bg-slate-50 dark:bg-slate-800/50 rounded-xl">
          <div className="text-5xl mb-4">🧠</div>
          <h4 className="text-lg font-medium text-slate-900 dark:text-white mb-2">
            Smart Code Search
          </h4>
          <p className="text-sm text-slate-600 dark:text-slate-400 max-w-md mx-auto mb-4">
            Search by concept, not just exact names. For example, searching "auth" will find
            login functions, JWT handlers, session managers, and more.
          </p>
          <div className="flex flex-wrap justify-center gap-2">
            <span className="px-3 py-1 text-xs bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 rounded-full">
              "database" → models, queries, schemas
            </span>
            <span className="px-3 py-1 text-xs bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 rounded-full">
              "error" → handlers, exceptions, catch
            </span>
            <span className="px-3 py-1 text-xs bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 rounded-full">
              "api" → routes, controllers, endpoints
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
