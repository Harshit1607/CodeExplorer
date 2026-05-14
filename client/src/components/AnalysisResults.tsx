import { useState, useCallback, Fragment } from 'react';
import OverviewSection from './OverviewSection';
import QuickStartGuide from './QuickStartGuide';
import ComplexityAnalysis from './ComplexityAnalysis';
import FileTreeSection from './FileTreeSection';
import LanguagesSection from './LanguagesSection';
import DependenciesSection from './DependenciesSection';
import KeyFilesSection from './KeyFilesSection';
import FileDependencies from './FileDependencies';
import GlobalSearch from './GlobalSearch';
import RepoChat from './RepoChat';
import SemanticSearch from './SemanticSearch';
import CallGraph from './CallGraph';
import ArchitectureDiagram from './ArchitectureDiagram';
import AIReportSection from './AIReportSection';

interface AnalysisResultsProps {
  state: any;
}

export default function AnalysisResults({ state }: AnalysisResultsProps) {
  const [activeTab, setActiveTab] = useState('quickstart');
  const [searchNavigationTarget, setSearchNavigationTarget] = useState<{
    filePath: string;
    type: string;
    name: string;
  } | null>(null);

  // Handle navigation from search results
  const handleSearchNavigate = useCallback((filePath: string, type: string, name: string) => {
    setSearchNavigationTarget({ filePath, type, name });

    // Navigate to appropriate tab based on result type
    if (type === 'file') {
      setActiveTab('structure');
    } else if (type === 'function' || type === 'class') {
      setActiveTab('complexity');
    }
  }, []);

  const tabs = [
    { id: 'quickstart', label: 'Quick Start', icon: 'rocket_launch' },
    { id: 'ai', label: 'AI Insights', icon: 'auto_awesome' },
    { id: 'chat', label: 'Chat', icon: 'forum' },
    { id: 'callgraph', label: 'Call Graph', icon: 'hub' },
    { id: 'filedeps', label: 'File Graph', icon: 'schema' },
    { id: 'search', label: 'Search', icon: 'search' },
    { id: 'architecture', label: 'Architecture', icon: 'architecture' },
    { id: 'complexity', label: 'Complexity', icon: 'speed' },
    { id: 'overview', label: 'Overview', icon: 'dashboard' },
    { id: 'structure', label: 'File Structure', icon: 'folder_open' },
    { id: 'languages', label: 'Languages', icon: 'terminal' },
    { id: 'dependencies', label: 'Dependencies', icon: 'inventory_2' },
    { id: 'keyfiles', label: 'Key Files', icon: 'grade' },
  ];

  // Reconstruct files dict from complexity fileList
  const files = state.complexity?.fileList?.reduce((acc: any, curr: any) => {
    acc[curr.file] = curr;
    return acc;
  }, {}) || {};

  return (
    <div className="mt-8 space-y-6">
      {/* Global Search Bar */}
      <div className="flex justify-center">
        <GlobalSearch
          files={files}
          onNavigate={handleSearchNavigate}
        />
      </div>

      {/* Navigation Target Info */}
      {searchNavigationTarget && (
        <div className="bg-primary-50 dark:bg-primary-900/20 border border-primary-200 dark:border-primary-800 rounded-xl p-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="material-symbols-outlined text-primary-600 dark:text-primary-400">
              {searchNavigationTarget.type === 'file' ? 'description' : searchNavigationTarget.type === 'function' ? 'bolt' : 'category'}
            </span>
            <div>
              <p className="text-sm font-medium text-primary-900 dark:text-primary-100">
                Navigated to: <span className="font-semibold">{searchNavigationTarget.name}</span>
              </p>
              <p className="text-xs text-primary-600 dark:text-primary-400">{searchNavigationTarget.filePath}</p>
            </div>
          </div>
          <button
            onClick={() => setSearchNavigationTarget(null)}
            className="text-primary-600 dark:text-primary-400 hover:text-primary-800 dark:hover:text-primary-200 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      <div className="bg-[var(--bg-secondary)] rounded-xl shadow-lg border border-[var(--border-color)] overflow-hidden">
        <div className="border-b border-[var(--border-color)]">
          <nav className="flex overflow-x-auto scrollbar-hide px-2 items-stretch">
            {tabs.map((tab, index) => (
              <Fragment key={tab.id}>
                <button
                  onClick={() => setActiveTab(tab.id)}
                  className={`
                    px-6 py-4 text-sm font-medium whitespace-nowrap
                    border-b-2 transition-all duration-200 flex items-center gap-2.5 relative
                    ${
                      activeTab === tab.id
                        ? 'border-primary-900 dark:border-primary-100 text-primary-900 dark:text-primary-100 bg-primary-100/50 dark:bg-primary-800/40 font-bold'
                        : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]'
                    }
                  `}
                >
                  <span className="material-symbols-outlined text-[22px] w-6 h-6 flex items-center justify-center">
                    {tab.icon}
                  </span>
                  {tab.label}
                </button>
                {index < tabs.length - 1 && (
                  <div className="flex items-center">
                    <div className="h-[34px] w-[1px] bg-[var(--border-color)] opacity-60" />
                  </div>
                )}
              </Fragment>
            ))}
          </nav>
        </div>

        <div className="p-6">
          {activeTab === 'quickstart' && (
            <QuickStartGuide
              entryPoints={state.entryPoints || []}
              keyFiles={state.keyFiles || []}
              languages={state.languages || {}}
              dependencies={state.dependencies || {}}
              frameworks={state.frameworks}
              databases={state.databases}
              readme={state.quickstart?.readme}
              packageManager={state.quickstart?.package_manager}
              runScripts={state.quickstart?.run_scripts}
            />
          )}

          {activeTab === 'chat' && (
            <RepoChat analysisData={state} />
          )}

          {activeTab === 'ai' && (
            <AIReportSection 
              report={state.aiReport} 
              isLoading={state.status === 'streaming'} 
            />
          )}

          {activeTab === 'search' && (
            <SemanticSearch analysisData={state} />
          )}

          {activeTab === 'architecture' && (
            <ArchitectureDiagram
              architecture={state.architecture || { nodes: [], edges: [], layers: [] }}
            />
          )}

          {activeTab === 'callgraph' && (
            <CallGraph
              callGraph={state.callGraph || {}}
              files={files}
            />
          )}

          {activeTab === 'complexity' && (
            <ComplexityAnalysis
              files={files}
              highlightTarget={searchNavigationTarget}
            />
          )}

          {activeTab === 'overview' && (
            <OverviewSection
              repositoryUrl={state.repoMeta?.url || "Repository"}
              scanResults={{}}
              structureAnalysis={state}
            />
          )}

          {activeTab === 'structure' && (
            <FileTreeSection tree={state.fileTree} />
          )}

          {activeTab === 'languages' && (
            <LanguagesSection languages={state.languages} />
          )}

          {activeTab === 'dependencies' && (
            <DependenciesSection dependencies={state.dependencies} />
          )}

          {activeTab === 'filedeps' && (
            <FileDependencies
              files={files}
              fileDependencies={state.fileDependencies || {}}
            />
          )}

          {activeTab === 'keyfiles' && (
            <KeyFilesSection
              keyFiles={state.keyFiles}
              entryPoints={state.entryPoints}
            />
          )}
        </div>
      </div>
    </div>
  );
}
