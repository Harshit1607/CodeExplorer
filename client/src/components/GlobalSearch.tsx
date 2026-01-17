import { useState, useMemo, useCallback, useRef, useEffect } from 'react';

interface FileInfo {
  imports?: string[];
  functions?: string[];
  classes?: string[];
  has_main?: boolean;
  complexity?: {
    score: number;
    level: string;
  };
}

interface SearchResult {
  type: 'file' | 'function' | 'class' | 'import';
  name: string;
  filePath: string;
  language?: string;
  context?: string;
}

interface GlobalSearchProps {
  files: { [key: string]: FileInfo };
  onNavigate?: (filePath: string, type: string, name: string) => void;
}

export default function GlobalSearch({ files, onNavigate }: GlobalSearchProps) {
  const [query, setQuery] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [filterType, setFilterType] = useState<'all' | 'file' | 'function' | 'class'>('all');
  const inputRef = useRef<HTMLInputElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Build searchable index from files
  const searchIndex = useMemo(() => {
    const index: SearchResult[] = [];

    if (!files) return index;

    Object.entries(files).forEach(([filePath, info]) => {
      // Normalize path
      const normalizedPath = filePath.replace(/\\/g, '/');
      const fileName = normalizedPath.split('/').pop() || '';
      const ext = fileName.split('.').pop()?.toLowerCase() || '';

      // Determine language
      let language = 'unknown';
      if (['ts', 'tsx'].includes(ext)) language = 'TypeScript';
      else if (['js', 'jsx'].includes(ext)) language = 'JavaScript';
      else if (ext === 'py') language = 'Python';
      else if (ext === 'java') language = 'Java';
      else if (ext === 'go') language = 'Go';
      else if (ext === 'rs') language = 'Rust';
      else if (ext === 'vue') language = 'Vue';

      // Add file
      index.push({
        type: 'file',
        name: fileName,
        filePath: normalizedPath,
        language,
        context: normalizedPath,
      });

      // Add functions
      if (info?.functions) {
        info.functions.forEach(func => {
          index.push({
            type: 'function',
            name: func,
            filePath: normalizedPath,
            language,
            context: `in ${fileName}`,
          });
        });
      }

      // Add classes
      if (info?.classes) {
        info.classes.forEach(cls => {
          index.push({
            type: 'class',
            name: cls,
            filePath: normalizedPath,
            language,
            context: `in ${fileName}`,
          });
        });
      }
    });

    return index;
  }, [files]);

  // Search results
  const results = useMemo(() => {
    if (!query.trim()) return [];

    const searchTerms = query.toLowerCase().split(/\s+/);

    return searchIndex
      .filter(item => {
        // Filter by type
        if (filterType !== 'all' && item.type !== filterType) return false;

        // Match against name and path
        const searchText = `${item.name} ${item.filePath}`.toLowerCase();
        return searchTerms.every(term => searchText.includes(term));
      })
      .slice(0, 50) // Limit results
      .sort((a, b) => {
        // Prioritize exact matches
        const aExact = a.name.toLowerCase() === query.toLowerCase();
        const bExact = b.name.toLowerCase() === query.toLowerCase();
        if (aExact && !bExact) return -1;
        if (bExact && !aExact) return 1;

        // Then prioritize by type: files > classes > functions
        const typeOrder = { file: 0, class: 1, function: 2, import: 3 };
        const typeDiff = typeOrder[a.type] - typeOrder[b.type];
        if (typeDiff !== 0) return typeDiff;

        // Then by name length (shorter = more relevant)
        return a.name.length - b.name.length;
      });
  }, [query, searchIndex, filterType]);

  // Reset selected index when results change
  useEffect(() => {
    setSelectedIndex(0);
  }, [results]);

  // Keyboard navigation
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (!isOpen) return;

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedIndex(prev => Math.min(prev + 1, results.length - 1));
        break;
      case 'ArrowUp':
        e.preventDefault();
        setSelectedIndex(prev => Math.max(prev - 1, 0));
        break;
      case 'Enter':
        e.preventDefault();
        if (results[selectedIndex]) {
          handleSelect(results[selectedIndex]);
        }
        break;
      case 'Escape':
        e.preventDefault();
        setIsOpen(false);
        setQuery('');
        break;
    }
  }, [isOpen, results, selectedIndex]);

  // Handle selection
  const handleSelect = useCallback((result: SearchResult) => {
    if (onNavigate) {
      onNavigate(result.filePath, result.type, result.name);
    }
    setIsOpen(false);
    setQuery('');
  }, [onNavigate]);

  // Scroll selected item into view
  useEffect(() => {
    if (resultsRef.current && results.length > 0) {
      const selectedEl = resultsRef.current.children[selectedIndex] as HTMLElement;
      if (selectedEl) {
        selectedEl.scrollIntoView({ block: 'nearest' });
      }
    }
  }, [selectedIndex, results.length]);

  // Close when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Keyboard shortcut to focus search (Ctrl/Cmd + K)
  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
        setIsOpen(true);
      }
    };

    document.addEventListener('keydown', handleGlobalKeyDown);
    return () => document.removeEventListener('keydown', handleGlobalKeyDown);
  }, []);

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

  // Stats
  const stats = useMemo(() => {
    const fileCount = searchIndex.filter(i => i.type === 'file').length;
    const funcCount = searchIndex.filter(i => i.type === 'function').length;
    const classCount = searchIndex.filter(i => i.type === 'class').length;
    return { fileCount, funcCount, classCount };
  }, [searchIndex]);

  return (
    <div ref={containerRef} className="relative w-full max-w-2xl">
      {/* Search Input */}
      <div className="relative">
        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
          <svg className="h-5 w-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIsOpen(true);
          }}
          onFocus={() => setIsOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder="Search files, functions, classes... (Ctrl+K)"
          className="w-full pl-10 pr-20 py-3 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-600 rounded-xl shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent text-slate-900 dark:text-white placeholder-slate-400"
        />
        <div className="absolute inset-y-0 right-0 pr-3 flex items-center gap-2">
          {query && (
            <button
              onClick={() => {
                setQuery('');
                inputRef.current?.focus();
              }}
              className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
          <kbd className="hidden sm:inline-flex items-center px-2 py-1 text-xs font-medium text-slate-400 bg-slate-100 dark:bg-slate-700 rounded">
            Ctrl+K
          </kbd>
        </div>
      </div>

      {/* Search Results Dropdown */}
      {isOpen && (
        <div className="absolute z-50 mt-2 w-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-xl overflow-hidden">
          {/* Filter Tabs */}
          <div className="flex border-b border-slate-200 dark:border-slate-700 px-2 py-2 gap-1 bg-slate-50 dark:bg-slate-900/50">
            {[
              { id: 'all', label: 'All', count: stats.fileCount + stats.funcCount + stats.classCount },
              { id: 'file', label: 'Files', count: stats.fileCount },
              { id: 'function', label: 'Functions', count: stats.funcCount },
              { id: 'class', label: 'Classes', count: stats.classCount },
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setFilterType(tab.id as typeof filterType)}
                className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                  filterType === tab.id
                    ? 'bg-blue-500 text-white'
                    : 'text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'
                }`}
              >
                {tab.label}
                <span className="ml-1 opacity-70">({tab.count})</span>
              </button>
            ))}
          </div>

          {/* Results */}
          <div ref={resultsRef} className="max-h-[400px] overflow-y-auto">
            {query.trim() === '' ? (
              <div className="p-4 text-center text-slate-500 dark:text-slate-400">
                <p className="text-sm">Start typing to search across:</p>
                <div className="flex justify-center gap-4 mt-2 text-xs">
                  <span>{stats.fileCount} files</span>
                  <span>{stats.funcCount} functions</span>
                  <span>{stats.classCount} classes</span>
                </div>
              </div>
            ) : results.length === 0 ? (
              <div className="p-4 text-center text-slate-500 dark:text-slate-400">
                <p>No results found for "{query}"</p>
              </div>
            ) : (
              results.map((result, index) => (
                <button
                  key={`${result.type}-${result.filePath}-${result.name}-${index}`}
                  onClick={() => handleSelect(result)}
                  className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-colors ${
                    index === selectedIndex
                      ? 'bg-blue-50 dark:bg-blue-900/30'
                      : 'hover:bg-slate-50 dark:hover:bg-slate-700/50'
                  }`}
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
                      {result.language && (
                        <span className="text-[10px] text-slate-400">{result.language}</span>
                      )}
                    </div>
                    <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
                      {result.context}
                    </p>
                  </div>
                  {index === selectedIndex && (
                    <kbd className="px-2 py-1 text-[10px] bg-slate-100 dark:bg-slate-700 rounded text-slate-500">
                      Enter
                    </kbd>
                  )}
                </button>
              ))
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between px-4 py-2 border-t border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-xs text-slate-500">
            <div className="flex items-center gap-3">
              <span className="flex items-center gap-1">
                <kbd className="px-1.5 py-0.5 bg-slate-200 dark:bg-slate-700 rounded">↑</kbd>
                <kbd className="px-1.5 py-0.5 bg-slate-200 dark:bg-slate-700 rounded">↓</kbd>
                navigate
              </span>
              <span className="flex items-center gap-1">
                <kbd className="px-1.5 py-0.5 bg-slate-200 dark:bg-slate-700 rounded">Enter</kbd>
                select
              </span>
              <span className="flex items-center gap-1">
                <kbd className="px-1.5 py-0.5 bg-slate-200 dark:bg-slate-700 rounded">Esc</kbd>
                close
              </span>
            </div>
            {results.length > 0 && (
              <span>{results.length} results</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
