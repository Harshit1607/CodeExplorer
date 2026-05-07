import React from 'react';

interface AIReportData {
  architecture_summary?: string;
  module_breakdown?: string[];
  tech_stack_rationale?: string;
  entry_point_deep_dive?: string;
  onboarding_advice?: string;
  error?: string;
}

interface AIReportSectionProps {
  report: AIReportData | null;
  isLoading: boolean;
}

export default function AIReportSection({ report, isLoading }: AIReportSectionProps) {
  // Helper to safely render content that might be strings or objects (AI hallucination protection)
  const renderContent = (content: any): React.ReactNode => {
    if (!content) return null;
    if (typeof content === 'string') return content;
    if (Array.isArray(content)) {
      return (
        <ul className="list-disc pl-4 space-y-1">
          {content.map((item, i) => (
            <li key={i}>{renderContent(item)}</li>
          ))}
        </ul>
      );
    }
    if (typeof content === 'object') {
      // Handle common hallucinated patterns: {module, description}, {tips, description}, etc.
      const entries = Object.entries(content);
      if (entries.length === 2) {
        return (
          <span>
            <strong className="font-semibold text-[var(--text-primary)]">{String(entries[0][1])}</strong>: {String(entries[1][1])}
          </span>
        );
      }
      return JSON.stringify(content);
    }
    return String(content);
  };

  if (isLoading && !report) {
    return (
      <div className="flex flex-col items-center justify-center py-20 space-y-4">
        <div className="relative">
          <div className="w-16 h-16 border-4 border-primary-200 border-t-primary-600 rounded-full animate-spin"></div>
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-xl">🤖</span>
          </div>
        </div>
        <div className="text-center">
          <h3 className="text-xl font-bold text-[var(--text-primary)]">Generating AI Intelligence...</h3>
          <p className="text-[var(--text-secondary)] mt-2">Our senior architect is reviewing the codebase structure.</p>
        </div>
      </div>
    );
  }

  if (!report) {
    return (
      <div className="text-center py-20">
        <div className="text-5xl mb-4">💤</div>
        <h3 className="text-xl font-bold text-[var(--text-primary)]">No AI Report Yet</h3>
        <p className="text-[var(--text-secondary)] mt-2">Analysis must complete to generate the AI intelligence report.</p>
      </div>
    );
  }

  if (report.error) {
    return (
      <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-6 text-center">
        <div className="text-3xl mb-3">⚠️</div>
        <h3 className="text-lg font-bold text-red-800 dark:text-red-300">AI Analysis Failed</h3>
        <p className="text-red-600 dark:text-red-400 mt-1">{report.error}</p>
        <p className="text-sm mt-4 text-red-500/70">Check if your GROQ_API_KEY is correctly configured in the backend.</p>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="flex items-center gap-4 mb-2">
        <div className="p-3 bg-primary-100 dark:bg-primary-900/30 rounded-2xl text-2xl">
          🧠
        </div>
        <div>
          <h2 className="text-2xl font-bold text-[var(--text-primary)]">Architectural Intelligence</h2>
          <p className="text-[var(--text-secondary)]">AI-powered insights derived from static analysis of the entire repository.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Architecture Summary */}
        <div className="col-span-1 md:col-span-2 bg-[var(--bg-tertiary)] rounded-2xl p-6 border border-[var(--border-color)] shadow-sm hover:shadow-md transition-shadow">
          <div className="flex items-center gap-2 mb-4">
            <span className="text-xl">🏗️</span>
            <h3 className="text-lg font-bold text-[var(--text-primary)]">Architectural Overview</h3>
          </div>
          <div className="prose prose-sm dark:prose-invert max-w-none text-[var(--text-secondary)] leading-relaxed whitespace-pre-wrap">
            {renderContent(report.architecture_summary)}
          </div>
        </div>

        {/* Tech Stack Rationale */}
        <div className="bg-[var(--bg-tertiary)] rounded-2xl p-6 border border-[var(--border-color)] shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <span className="text-xl">🛠️</span>
            <h3 className="text-lg font-bold text-[var(--text-primary)]">Tech Stack Rationale</h3>
          </div>
          <div className="text-sm text-[var(--text-secondary)] leading-relaxed">
            {renderContent(report.tech_stack_rationale)}
          </div>
        </div>

        {/* Entry Point Deep Dive */}
        <div className="bg-[var(--bg-tertiary)] rounded-2xl p-6 border border-[var(--border-color)] shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <span className="text-xl">🚀</span>
            <h3 className="text-lg font-bold text-[var(--text-primary)]">Entry Point Deep Dive</h3>
          </div>
          <div className="text-sm text-[var(--text-secondary)] leading-relaxed">
            {renderContent(report.entry_point_deep_dive)}
          </div>
        </div>

        {/* Module Breakdown */}
        <div className="col-span-1 md:col-span-2 bg-[var(--bg-tertiary)] rounded-2xl p-6 border border-[var(--border-color)] shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <span className="text-xl">📦</span>
            <h3 className="text-lg font-bold text-[var(--text-primary)]">Module Breakdown</h3>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {Array.isArray(report.module_breakdown) ? (
              report.module_breakdown.map((item, idx) => (
                <div key={idx} className="flex gap-3 p-3 bg-[var(--bg-secondary)] rounded-xl border border-[var(--border-color)]">
                  <span className="text-primary-500 font-bold">•</span>
                  <div className="text-sm text-[var(--text-primary)]">
                    {renderContent(item)}
                  </div>
                </div>
              ))
            ) : (
              <div className="text-sm text-[var(--text-secondary)] col-span-2">
                {renderContent(report.module_breakdown)}
              </div>
            )}
          </div>
        </div>

        {/* Onboarding Advice */}
        <div className="col-span-1 md:col-span-2 bg-gradient-to-br from-primary-50 to-white dark:from-primary-900/10 dark:to-[var(--bg-tertiary)] rounded-2xl p-6 border border-primary-200 dark:border-primary-800 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <span className="text-xl">💡</span>
            <h3 className="text-lg font-bold text-primary-900 dark:text-primary-100">Contribution & Onboarding Advice</h3>
          </div>
          <div className="text-sm text-primary-800/80 dark:text-primary-200/80 leading-relaxed whitespace-pre-wrap">
            {renderContent(report.onboarding_advice)}
          </div>
        </div>
      </div>
      
      <div className="pt-4 text-center">
        <p className="text-xs text-[var(--text-tertiary)] italic">
          Report generated by AI (Llama 3 70B) based on static code analysis of the repository structure and content.
        </p>
      </div>
    </div>
  );
}
