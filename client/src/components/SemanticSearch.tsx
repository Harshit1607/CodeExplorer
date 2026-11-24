import { useState } from 'react';
import axios from 'axios';
import { sourceLink } from '../lib/github';

type SearchMode = 'hybrid' | 'semantic' | 'keyword';

interface SearchResult {
  type: string;
  name: string;
  file_path: string;
  context: string;
  score: number;
  match: 'keyword' | 'semantic' | 'hybrid';
  similarity?: number | null;
  start_line?: number | null;
  end_line?: number | null;
  snippet?: string | null;
}

interface SearchResponse {
  query: string;
  total_results: number;
  results: SearchResult[];
  grouped: { [key: string]: SearchResult[] };
  mode: SearchMode;
}

interface SemanticSearchProps {
  analysisData: any;
}

const MODES: { id: SearchMode; label: string; hint: string }[] = [
  { id: 'hybrid', label: 'Hybrid', hint: 'Meaning + names (recommended)' },
  { id: 'semantic', label: 'Semantic', hint: 'Code embeddings only' },
  { id: 'keyword', label: 'Keyword', hint: 'Names and concepts only' },
];

const TYPE_LABELS: Record<string, string> = {
  function: 'functions', class: 'classes', file: 'files', import: 'imports', docs: 'docs', config: 'config',
};

const suggestedSearches = [
  { label: 'Authentication', query: 'where is user authentication handled' },
  { label: 'API Endpoints', query: 'http api route handlers' },
  { label: 'Database', query: 'database queries and models' },
  { label: 'Config', query: 'load configuration and environment variables' },
  { label: 'Error Handling', query: 'error handling and retries' },
  { label: 'Entry Point', query: 'application startup and initialization' },
  { label: 'UI Components', query: 'ui component rendering' },
  { label: 'Tests', query: 'test spec' },
  { label: 'Deploy', query: 'how to deploy and configure the project' },
];

export default function SemanticSearch({ analysisData }: SemanticSearchProps) {
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState<SearchMode>('hybrid');
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [activeFilter, setActiveFilter] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const index = analysisData?.searchIndex || { status: 'idle', searchable: false, indexed: 0, total: 0 };
  const vectorsUsable = index.searchable;

  const handleSearch = async (searchQuery?: string, searchMode: SearchMode = mode) => {
    const q = (searchQuery ?? query).trim();
    if (!q || isLoading) return;

    setIsLoading(true);
    setError('');
    setActiveFilter(null);
    setExpanded(new Set());

    try {
      const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      const sessionId = analysisData?.sessionId;
      const send = (withData: boolean) => axios.post(`${API_BASE_URL}/api/search`, {
        query: q,
        mode: searchMode,
        session_id: sessionId,
        // Slim fallback, only once the server session has expired (keyword search only).
        analysis_data: withData ? { complexity: { fileList: analysisData?.complexity?.fileList || [] } } : undefined,
      });
      let response;
      try {
        response = await send(!sessionId);
      } catch (err: any) {
        if (!sessionId || err.response?.status !== 404) throw err;
        response = await send(true);
      }
      setResults(response.data);
    } catch (err: any) {
      console.error('Search error:', err);
      setError(err.response?.status === 413
        ? 'Your analysis session has expired. Re-run the analysis to search again.'
        : err.response?.data?.detail || 'Search failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSuggestionClick = (suggestion: string) => {
    setQuery(suggestion);
    handleSearch(suggestion);
  };

  const handleModeChange = (m: SearchMode) => {
    setMode(m);
    if (results) handleSearch(results.query, m);
  };

  const toggleExpanded = (idx: number) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx); else next.add(idx);
      return next;
    });
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'file': return '📄';
      case 'function': return '⚡';
      case 'class': return '🔷';
      case 'import': return '📦';
      case 'docs': return '📘';
      case 'config': return '⚙️';
      default: return '📌';
    }
  };

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'file': return 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300';
      case 'function': return 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300';
      case 'class': return 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300';
      case 'import': return 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300';
      case 'docs': return 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300';
      case 'config': return 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300';
      default: return 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300';
    }
  };

  const getMatchBadge = (match: string) => {
    switch (match) {
      case 'hybrid': return { label: 'meaning + name', cls: 'text-emerald-700 dark:text-emerald-300 border-emerald-300 dark:border-emerald-700' };
      case 'semantic': return { label: 'meaning', cls: 'text-violet-700 dark:text-violet-300 border-violet-300 dark:border-violet-700' };
      default: return { label: 'name', cls: 'text-slate-600 dark:text-slate-400 border-slate-300 dark:border-slate-600' };
    }
  };

  const getScoreColor = (score: number) => {
    if (score >= 70) return 'text-green-600 dark:text-green-400';
    if (score >= 40) return 'text-blue-600 dark:text-blue-400';
    if (score >= 20) return 'text-amber-600 dark:text-amber-400';
    return 'text-slate-500 dark:text-slate-400';
  };

  const filteredResults = activeFilter
    ? results?.results.filter(r => r.type === activeFilter) || []
    : results?.results || [];

  const indexPct = index.total ? Math.round((100 * index.indexed) / index.total) : 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2 flex items-center gap-2">
            <span>🔍</span> Semantic Code Search
          </h3>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Describe what the code does — results combine vector embeddings of the source, docs and config files with name and concept matching
          </p>
        </div>

        {/* Index status */}
        <div className="text-xs min-w-[220px]">
          {index.status === 'building' && (
            <div>
              <div className="flex justify-between text-slate-600 dark:text-slate-400 mb-1">
                <span>Building semantic index{vectorsUsable ? ' (partial results available)' : '…'}</span>
                <span>{indexPct}%</span>
              </div>
              <div className="w-full bg-slate-200 dark:bg-slate-700 rounded-full h-1.5">
                <div className="bg-violet-500 h-1.5 rounded-full transition-all duration-300" style={{ width: `${indexPct}%` }} />
              </div>
            </div>
          )}
          {index.status === 'ready' && (
            <span className="inline-flex items-center gap-1.5 text-emerald-700 dark:text-emerald-400">
              <span className="w-2 h-2 rounded-full bg-emerald-500" /> Semantic index ready · {index.total} chunks
            </span>
          )}
          {(index.status === 'failed' || index.status === 'unavailable') && (
            <span className="inline-flex items-center gap-1.5 text-amber-700 dark:text-amber-400" title={index.error || ''}>
              <span className="w-2 h-2 rounded-full bg-amber-500" /> Semantic index unavailable — keyword search only
            </span>
          )}
          {index.status === 'idle' && (
            <span className="text-slate-500 dark:text-slate-400">Semantic index starts after files are scanned</span>
          )}
        </div>
      </div>

      {/* Search Form */}
      <form onSubmit={(e) => { e.preventDefault(); handleSearch(); }} className="space-y-3">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g., 'where are passwords hashed', 'retry failed http requests', 'parseConfig'..."
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

        <div className="flex items-center justify-between gap-3 flex-wrap">
          {/* Suggested Searches */}
          <div className="flex flex-wrap gap-2">
            {suggestedSearches.map((item) => (
              <button
                key={item.label}
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

          {/* Mode toggle */}
          <div className="inline-flex rounded-lg border border-slate-300 dark:border-slate-600 overflow-hidden text-xs">
            {MODES.map((m) => {
              const disabled = m.id !== 'keyword' && !vectorsUsable;
              return (
                <button
                  key={m.id}
                  type="button"
                  title={disabled ? 'Semantic index not ready yet' : m.hint}
                  disabled={disabled || isLoading}
                  onClick={() => handleModeChange(m.id)}
                  className={`px-3 py-1.5 transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                    mode === m.id
                      ? 'bg-blue-600 text-white'
                      : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700'
                  }`}
                >
                  {m.label}
                </button>
              );
            })}
          </div>
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
          <div className="flex items-center justify-between flex-wrap gap-3">
            <p className="text-sm text-slate-600 dark:text-slate-400">
              Found <span className="font-semibold text-slate-900 dark:text-white">{results.total_results}</span> results
              for "<span className="font-medium">{results.query}</span>"
              <span className="ml-2 text-xs text-slate-500">({results.mode} search)</span>
            </p>

            {results.total_results > 0 && (
              <div className="flex gap-1 flex-wrap">
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
                    {TYPE_LABELS[type] || type} ({items.length})
                  </button>
                ))}
              </div>
            )}
          </div>

          {results.total_results === 0 ? (
            <div className="text-center py-12 bg-slate-50 dark:bg-slate-800/50 rounded-xl">
              <div className="text-4xl mb-3">🔍</div>
              <p className="text-slate-600 dark:text-slate-400 mb-2">No results found</p>
              <p className="text-sm text-slate-500 dark:text-slate-500">Try describing the behaviour in plain words, or browse the suggested searches above</p>
            </div>
          ) : (
            <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
              <div className="max-h-[600px] overflow-y-auto divide-y divide-slate-100 dark:divide-slate-700/50">
                {filteredResults.map((result, idx) => {
                  const badge = getMatchBadge(result.match);
                  const link = sourceLink(analysisData?.repoMeta, result.file_path, result.start_line, result.end_line);
                  const isOpen = expanded.has(idx);
                  return (
                    <div key={`${result.type}:${result.file_path}:${result.name}:${idx}`} className="px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors">
                      <div className="flex items-start gap-3">
                        <span className="text-xl mt-0.5">{getTypeIcon(result.type)}</span>

                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-semibold text-slate-900 dark:text-white font-mono text-sm">{result.name}</span>
                            <span className={`px-2 py-0.5 text-[10px] font-medium rounded-full ${getTypeColor(result.type)}`}>
                              {result.type}
                            </span>
                            <span className={`px-2 py-0.5 text-[10px] font-medium rounded-full border ${badge.cls}`}>
                              {badge.label}
                            </span>
                          </div>
                          <p className="text-sm text-slate-500 dark:text-slate-400 truncate mt-0.5">
                            {link ? (
                              <a href={link} target="_blank" rel="noreferrer" className="hover:text-blue-600 dark:hover:text-blue-400 hover:underline">
                                {result.file_path}{result.start_line ? `:${result.start_line}-${result.end_line}` : ''}
                              </a>
                            ) : (
                              <>{result.file_path}{result.start_line ? `:${result.start_line}-${result.end_line}` : ''}</>
                            )}
                          </p>
                          {result.snippet && (
                            <button
                              type="button"
                              onClick={() => toggleExpanded(idx)}
                              className="mt-1 text-xs text-blue-600 dark:text-blue-400 hover:underline"
                            >
                              {isOpen ? 'Hide code' : 'Show code'}
                            </button>
                          )}
                        </div>

                        <div className={`text-sm font-medium tabular-nums ${getScoreColor(result.score)}`} title={
                          result.similarity != null ? `cosine similarity ${result.similarity}` : 'keyword match'
                        }>
                          {Math.round(result.score)}
                        </div>
                      </div>

                      {isOpen && result.snippet && (
                        <pre className="mt-2 ml-9 text-xs leading-relaxed bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-700 rounded-lg p-3 overflow-x-auto text-slate-800 dark:text-slate-200">
                          {result.snippet.split('\n').map((ln, i) => (
                            <div key={i} className="whitespace-pre">
                              <span className="inline-block w-10 pr-3 text-right text-slate-400 select-none">
                                {result.start_line ? result.start_line + i : ''}
                              </span>
                              {ln}
                            </div>
                          ))}
                        </pre>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {results.total_results > 0 && (
            <div className="flex items-center justify-end gap-4 text-xs text-slate-500 dark:text-slate-400 flex-wrap">
              <span>Relevance (100 = top match on every signal):</span>
              <span className="text-green-600 dark:text-green-400">High (70+)</span>
              <span className="text-blue-600 dark:text-blue-400">Medium (40–69)</span>
              <span className="text-amber-600 dark:text-amber-400">Low (20–39)</span>
            </div>
          )}
        </div>
      )}

      {/* Empty State */}
      {!results && !isLoading && (
        <div className="text-center py-12 bg-slate-50 dark:bg-slate-800/50 rounded-xl">
          <div className="text-5xl mb-4">🧠</div>
          <h4 className="text-lg font-medium text-slate-900 dark:text-white mb-2">
            Search by meaning
          </h4>
          <p className="text-sm text-slate-600 dark:text-slate-400 max-w-md mx-auto mb-4">
            Every function and class is embedded as a vector, so you can describe behaviour instead of guessing names.
            Exact identifiers still work too.
          </p>
          <div className="flex flex-wrap justify-center gap-2">
            <span className="px-3 py-1 text-xs bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 rounded-full">
              "read environment variables" → resolve_envvar_value()
            </span>
            <span className="px-3 py-1 text-xs bg-sky-100 dark:bg-sky-900/40 text-sky-700 dark:text-sky-300 rounded-full">
              "retry on rate limit" → error handlers
            </span>
            <span className="px-3 py-1 text-xs bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 rounded-full">
              "makeContext" → exact symbol
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
