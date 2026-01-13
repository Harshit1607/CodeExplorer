import { useState } from 'react';
import DependencyGraph from './DependencyGraph';

interface DependenciesSectionProps {
  dependencies: {
    python?: { [key: string]: string[] };
    javascript?: { [key: string]: string[] };
    other?: { [key: string]: string[] };
  };
}

export default function DependenciesSection({ dependencies }: DependenciesSectionProps) {
  const [viewMode, setViewMode] = useState<'list' | 'graph'>('list');

  if (!dependencies || Object.keys(dependencies).length === 0) {
    return (
      <div className="text-center py-8 text-slate-500 dark:text-slate-400">
        No dependencies found
      </div>
    );
  }

  const renderDependencyGroup = (title: string, deps: { [key: string]: string[] }, icon: string) => {
    const hasData = deps && Object.keys(deps).length > 0 && Object.values(deps).some(arr => arr.length > 0);

    if (!hasData) return null;

    return (
      <div className="space-y-3">
        <h4 className="text-md font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-2">
          <span>{icon}</span>
          {title}
        </h4>
        {Object.entries(deps).map(([source, packages]) => {
          if (!packages || packages.length === 0) return null;

          return (
            <div key={source} className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-4 border border-slate-200 dark:border-slate-600">
              <h5 className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                {source}
              </h5>
              <div className="flex flex-wrap gap-2">
                {packages.map((pkg, index) => (
                  <span
                    key={index}
                    className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium
                             bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300
                             border border-blue-200 dark:border-blue-800"
                  >
                    {pkg}
                  </span>
                ))}
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">
                {packages.length} package{packages.length !== 1 ? 's' : ''}
              </p>
            </div>
          );
        })}
      </div>
    );
  };

  const hasAnyDependencies =
    (dependencies.python && Object.keys(dependencies.python).length > 0 && Object.values(dependencies.python).some(arr => arr.length > 0)) ||
    (dependencies.javascript && Object.keys(dependencies.javascript).length > 0 && Object.values(dependencies.javascript).some(arr => arr.length > 0)) ||
    (dependencies.other && Object.keys(dependencies.other).length > 0 && Object.values(dependencies.other).some(arr => arr.length > 0));

  if (!hasAnyDependencies) {
    return (
      <div className="text-center py-8 text-slate-500 dark:text-slate-400">
        No dependency files found in this repository
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
          Dependencies
        </h3>
        <div className="flex gap-2 bg-slate-100 dark:bg-slate-700 p-1 rounded-lg">
          <button
            onClick={() => setViewMode('list')}
            className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
              viewMode === 'list'
                ? 'bg-white dark:bg-slate-600 text-slate-900 dark:text-white shadow'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
            }`}
          >
            List View
          </button>
          <button
            onClick={() => setViewMode('graph')}
            className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
              viewMode === 'graph'
                ? 'bg-white dark:bg-slate-600 text-slate-900 dark:text-white shadow'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
            }`}
          >
            Graph View
          </button>
        </div>
      </div>

      {viewMode === 'graph' ? (
        <DependencyGraph dependencies={dependencies} />
      ) : (
        <div className="space-y-6">
          {dependencies.python && renderDependencyGroup('Python Dependencies', dependencies.python, '🐍')}
          {dependencies.javascript && renderDependencyGroup('JavaScript Dependencies', dependencies.javascript, '📦')}
          {dependencies.other && renderDependencyGroup('Other Dependencies', dependencies.other, '🔧')}
        </div>
      )}
    </div>
  );
}
