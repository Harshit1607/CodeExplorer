
import { useState } from 'react';
import OverviewSection from './OverviewSection';
import FileTreeSection from './FileTreeSection';
import LanguagesSection from './LanguagesSection';
import DependenciesSection from './DependenciesSection';
import KeyFilesSection from './KeyFilesSection';

interface AnalysisResultsProps {
  data: any;
}

export default function AnalysisResults({ data }: AnalysisResultsProps) {
  const [activeTab, setActiveTab] = useState('overview');

  const tabs = [
    { id: 'overview', label: 'Overview', icon: '📊' },
    { id: 'structure', label: 'File Structure', icon: '📁' },
    { id: 'languages', label: 'Languages', icon: '💻' },
    { id: 'dependencies', label: 'Dependencies', icon: '📦' },
    { id: 'keyfiles', label: 'Key Files', icon: '⭐' },
  ];

  const structureAnalysis = data.structure_analysis || data.analysis;

  return (
    <div className="mt-8 space-y-6">
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
