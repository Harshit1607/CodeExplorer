import React, { Fragment } from 'react';
import { sourceLink } from '../lib/github';

interface ReportSource {
  file: string;
  start_line: number;
  end_line: number;
  symbol?: string | null;
  reason: string;
  tag?: string;
}

interface ReportGrounding {
  mode: 'code' | 'metadata';
  excerpts: number;
  files: number;
  roles: Record<string, number>;
  semantic_retrieval: boolean;
  index_status: string;
  index_partial: boolean;
  indexed_chunks: number;
  total_chunks: number;
  model?: string;
  citations: Record<string, { file: string; start_line: number; end_line: number }>;
  unverified: string[];
  uncited_sections: string[];
  spans: Record<string, CitationSpan[]>;
}

/** Where a citation sits in a report string (UTF-16 offsets, i.e. JS string indices). */
interface CitationSpan {
  at: number;
  to: number;
  verified: boolean;
  file?: string;
  start_line?: number;
  end_line?: number;
}

interface AIReportData {
  architecture_summary?: string;
  module_breakdown?: string[];
  tech_stack_rationale?: string;
  entry_point_deep_dive?: string;
  onboarding_advice?: string;
  sources?: ReportSource[];
  grounding?: ReportGrounding;
  error?: string;
}

interface AIReportSectionProps {
  report: AIReportData | null;
  isLoading: boolean;
  repoMeta?: any;
  pending?: { waiting_for_index: boolean; max_wait_seconds: number } | null;
  searchIndex?: { status: string; indexed: number; total: number };
}

const ROLE_LABELS: Record<string, string> = {
  entry_point: 'entry points',
  key_module: 'key modules',
  route: 'routes',
  model: 'data models',
  setup: 'setup docs/config',
};

const SECTION_LABELS: Record<string, string> = {
  architecture_summary: 'Architectural Overview',
  module_breakdown: 'Module Breakdown',
  tech_stack_rationale: 'Tech Stack Rationale',
  entry_point_deep_dive: 'Entry Point Deep Dive',
  onboarding_advice: 'Onboarding Advice',
};

/** What the report was actually written from, in one or two sentences. */
function groundingSummary(g?: ReportGrounding): string {
  if (!g) return 'AI-written summary of the repository metadata.';
  if (g.mode !== 'code') {
    return 'Written from repository metadata only (file names, dependencies, README excerpt): no code excerpts were available, so treat its claims as unverified.';
  }
  const roles = Object.keys(g.roles || {}).map(r => ROLE_LABELS[r] || r).join(', ');
  let text = `Written from ${g.excerpts} code excerpt${g.excerpts === 1 ? '' : 's'} in ${g.files} file${g.files === 1 ? '' : 's'}` +
    `${roles ? ` (${roles})` : ''} plus repository metadata, not from the entire repository. Cited lines link to the code it was shown.`;
  if (g.index_partial && g.total_chunks) {
    text += ` The search index was ${Math.round((100 * g.indexed_chunks) / g.total_chunks)}% built when the report was written, so retrieval saw part of the code.`;
  } else if (!g.semantic_retrieval) {
    text += ' Semantic retrieval was unavailable, so excerpts come from detected entry points, key files and routes only.';
  }
  return text;
}

export default function AIReportSection({ report, isLoading, repoMeta, pending, searchIndex }: AIReportSectionProps) {
  const grounding = report?.grounding;

  /** A citation the server found: verified ones link to GitHub, others are flagged. */
  const renderCitation = (span: CitationSpan, label: string, key: React.Key): React.ReactNode => {
    if (!span.verified || !span.file || !span.start_line) {
      return (
        <span key={key} title="Not in the code excerpts this report was written from"
              className="font-mono text-[0.85em] text-[var(--text-muted)] underline decoration-dotted">
          {label}
        </span>
      );
    }
    const href = sourceLink(repoMeta, span.file, span.start_line, span.end_line);
    if (!href) return <code key={key} className="font-mono text-[0.85em]">{label}</code>;
    return (
      <a key={key} href={href} target="_blank" rel="noreferrer" title={`${span.file} lines ${span.start_line}-${span.end_line}`}
         className="font-mono text-[0.85em] text-[var(--text-primary)] underline underline-offset-2 decoration-primary-400 hover:decoration-2">
        {label}
      </a>
    );
  };

  /** Plain text with the citation spans the server located in it (`grounding.spans[text]`). */
  const renderText = (text: string): React.ReactNode => {
    if (!grounding) return text;
    const spans = grounding.spans?.[text] || [];
    let pos = 0;
    // Inline `code` spans first; a span that is exactly a citation is still a citation.
    return text.split(/(`[^`\n]+`)/g).map((segment, i) => {
      const from = pos;
      pos += segment.length;
      const inside = spans.filter(s => s.at >= from && s.to <= pos);
      if (segment.length > 2 && segment.startsWith('`') && segment.endsWith('`')) {
        const only = inside.length === 1 && inside[0].at === from + 1 && inside[0].to === pos - 1;
        return only
          ? renderCitation(inside[0], segment.slice(1, -1), i)
          : <code key={i} className="px-1 py-0.5 rounded bg-black/10 dark:bg-white/10 font-mono text-[0.85em]">{segment.slice(1, -1)}</code>;
      }
      const parts: React.ReactNode[] = [];
      let last = from;
      inside.forEach((s, j) => {
        if (s.at > last) parts.push(text.slice(last, s.at));
        parts.push(renderCitation(s, text.slice(s.at, s.to), j));
        last = s.to;
      });
      if (last < pos) parts.push(text.slice(last, pos));
      return <Fragment key={i}>{parts}</Fragment>;
    });
  };

  // Helper to safely render content that might be strings or objects (AI hallucination protection)
  const renderContent = (content: any): React.ReactNode => {
    if (!content) return null;
    if (typeof content === 'string') return renderText(content);
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
            <strong className="font-semibold text-[var(--text-primary)]">{String(entries[0][1])}</strong>: {renderText(String(entries[1][1]))}
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
          <h3 className="text-xl font-bold text-[var(--text-primary)]">Generating AI Insights...</h3>
          <p className="text-[var(--text-secondary)] mt-2 max-w-md">
            {pending?.waiting_for_index && searchIndex?.status === 'building'
              ? `Waiting for the code index (${searchIndex.total ? Math.round((100 * searchIndex.indexed) / searchIndex.total) : 0}% embedded) so the report can quote and cite real code. After ${pending.max_wait_seconds}s it uses the part already indexed.`
              : pending
                ? 'Retrieving entry points, key modules, routes and models, then writing the report...'
                : 'The report starts once the static analysis is done; it is written from retrieved code.'}
          </p>
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
          <p className="text-[var(--text-secondary)]">{groundingSummary(grounding)}</p>
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
      
      {report.sources && report.sources.length > 0 && (
        <div className="bg-[var(--bg-tertiary)] rounded-2xl p-5 border border-[var(--border-color)]">
          <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-1">Code this report was written from</h3>
          {grounding && (
            <p className="text-xs text-[var(--text-secondary)] mb-3">
              {Object.keys(grounding.citations || {}).length} citation{Object.keys(grounding.citations || {}).length === 1 ? '' : 's'} point into these excerpts
              {grounding.unverified?.length > 0 && <>; {grounding.unverified.length} (dotted) point elsewhere and could not be checked</>}
              {grounding.uncited_sections?.length > 0 && (
                <>; no checked citation in: {grounding.uncited_sections.map(s => SECTION_LABELS[s] || s).join(', ')}</>
              )}.
            </p>
          )}
          <div className="flex flex-wrap gap-1.5">
            {report.sources.map((s, i) => {
              const href = sourceLink(repoMeta, s.file, s.start_line, s.end_line);
              const label = `${s.file.split('/').pop()}:${s.start_line}-${s.end_line}`;
              const title = `${s.file}${s.symbol ? ` · ${s.symbol}` : ''} (${ROLE_LABELS[s.reason] || s.reason})`;
              const cls = 'px-2 py-0.5 text-[11px] font-mono rounded-full bg-[var(--bg-secondary)] border border-[var(--border-color)] text-[var(--text-secondary)]';
              return href ? (
                <a key={i} href={href} target="_blank" rel="noreferrer" title={title}
                   className={`${cls} hover:text-primary-600 dark:hover:text-primary-400 hover:border-primary-400`}>
                  {label}
                </a>
              ) : (
                <span key={i} title={title} className={cls}>{label}</span>
              );
            })}
          </div>
        </div>
      )}

      <div className="pt-4 text-center">
        <p className="text-xs text-[var(--text-tertiary)] italic">
          Report generated by AI{grounding?.model ? ` (${grounding.model})` : ''}. It can still be wrong: check the cited lines.
        </p>
      </div>
    </div>
  );
}
