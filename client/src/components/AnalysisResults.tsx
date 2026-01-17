import { useState, useCallback } from 'react';
import OverviewSection from './OverviewSection';
import QuickStartGuide from './QuickStartGuide';
import ComplexityAnalysis from './ComplexityAnalysis';
import FileTreeSection from './FileTreeSection';
import LanguagesSection from './LanguagesSection';
import DependenciesSection from './DependenciesSection';
import KeyFilesSection from './KeyFilesSection';
import FileDependencies from './FileDependencies';
import GlobalSearch from './GlobalSearch';

interface AnalysisResultsProps {
  data: any;
}

export default function AnalysisResults({ data }: AnalysisResultsProps) {
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
    { id: 'quickstart', label: 'Quick Start', icon: '🚀' },
    { id: 'complexity', label: 'Complexity', icon: '🎯' },
    { id: 'overview', label: 'Overview', icon: '📊' },
    { id: 'structure', label: 'File Structure', icon: '📁' },
    { id: 'languages', label: 'Languages', icon: '💻' },
    { id: 'dependencies', label: 'Dependencies', icon: '📦' },
    { id: 'filedeps', label: 'File Dependencies', icon: '🔗' },
    { id: 'keyfiles', label: 'Key Files', icon: '⭐' },
  ];

  const structureAnalysis = data.structure_analysis || data.analysis;

  return (
    <div className="mt-8 space-y-6">
      {/* Global Search Bar */}
      <div className="flex justify-center">
        <GlobalSearch
          files={structureAnalysis?.files || {}}
          onNavigate={handleSearchNavigate}
        />
      </div>

      {/* Navigation Target Info */}
      {searchNavigationTarget && (
        <div className="bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800 rounded-lg p-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-blue-600 dark:text-blue-400">
              {searchNavigationTarget.type === 'file' ? '📄' : searchNavigationTarget.type === 'function' ? '⚡' : '🔷'}
            </span>
            <div>
              <p className="text-sm font-medium text-blue-900 dark:text-blue-100">
                Navigated to: <span className="font-semibold">{searchNavigationTarget.name}</span>
              </p>
              <p className="text-xs text-blue-600 dark:text-blue-400">{searchNavigationTarget.filePath}</p>
            </div>
          </div>
          <button
            onClick={() => setSearchNavigationTarget(null)}
            className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-200"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg border border-slate-200 dark:border-slate-700 overflow-hidden">
        <div className="border-b border-slate-200 dark:border-slate-700">
          <nav className="flex overflow-x-auto">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`
                  px-6 py-4 text-sm font-medium whitespace-nowrap
                  border-b-2 transition-colors
                  ${
                    activeTab === tab.id
                      ? 'border-blue-600 text-blue-600 dark:text-blue-400'
                      : 'border-transparent text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                  }
                `}
              >
                <span className="mr-2">{tab.icon}</span>
                {tab.label}
              </button>
            ))}
          </nav>
        </div>

        <div className="p-6">
          {activeTab === 'quickstart' && (
            <QuickStartGuide
              entryPoints={structureAnalysis?.entry_points || []}
              keyFiles={structureAnalysis?.key_files || []}
              languages={structureAnalysis?.languages || {}}
              dependencies={structureAnalysis?.dependencies || {}}
              frameworks={structureAnalysis?.frameworks}
              databases={structureAnalysis?.databases}
              readme={structureAnalysis?.readme}
            />
          )}

          {activeTab === 'complexity' && (
            <ComplexityAnalysis
              files={structureAnalysis?.files || {}}
              highlightTarget={searchNavigationTarget}
            />
          )}

          {activeTab === 'overview' && (
            <OverviewSection
              repositoryUrl={data.repository_url}
              scanResults={data.scan_results}
              structureAnalysis={structureAnalysis}
            />
          )}

          {activeTab === 'structure' && (
            <FileTreeSection tree={structureAnalysis?.tree} />
          )}

          {activeTab === 'languages' && (
            <LanguagesSection languages={structureAnalysis?.languages} />
          )}

          {activeTab === 'dependencies' && (
            <DependenciesSection dependencies={structureAnalysis?.dependencies} />
          )}

          {activeTab === 'filedeps' && (
            <FileDependencies
              files={structureAnalysis?.files || {}}
              fileDependencies={structureAnalysis?.file_dependencies || {}}
            />
          )}

          {activeTab === 'keyfiles' && (
            <KeyFilesSection
              keyFiles={structureAnalysis?.key_files}
              entryPoints={structureAnalysis?.entry_points}
            />
          )}
        </div>
      </div>
    </div>
  );
}
