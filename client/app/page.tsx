'use client';

import { useState } from 'react';
import RepositoryInput from '@/components/RepositoryInput';
import AnalysisResults from '@/components/AnalysisResults';

export default function Home() {
  const [analysisData, setAnalysisData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleAnalysisComplete = (data: any) => {
    setAnalysisData(data);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
      <header className="bg-white dark:bg-slate-800 shadow-sm border-b border-slate-200 dark:border-slate-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
              </svg>
            </div>
            <div>
              <h1 className="text-3xl font-bold text-slate-900 dark:text-white">
                CodeExplorer
              </h1>
              <p className="text-sm text-slate-600 dark:text-slate-400">
                Repository-grounded codebase intelligence
              </p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <RepositoryInput
          onAnalysisComplete={handleAnalysisComplete}
          isLoading={isLoading}
          setIsLoading={setIsLoading}
        />

        {isLoading && (
          <div className="mt-8 text-center">
            <div className="inline-flex items-center gap-3 bg-white dark:bg-slate-800 px-6 py-4 rounded-lg shadow-lg">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
              <span className="text-slate-700 dark:text-slate-300">Analyzing repository...</span>
            </div>
          </div>
        )}

        {analysisData && !isLoading && (
          <AnalysisResults data={analysisData} />
        )}
      </main>

      <footer className="mt-16 border-t border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <p className="text-center text-sm text-slate-600 dark:text-slate-400">
            CodeExplorer - Free and open-source repository analysis tool
          </p>
        </div>
      </footer>
    </div>
  );
}
