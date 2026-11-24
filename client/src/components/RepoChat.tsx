import { useState, useRef, useEffect, Fragment, ReactNode } from 'react';
import axios from 'axios';

interface ChatSource {
  file: string;
  start_line: number;
  end_line: number;
  symbol?: string | null;
  reason: string;
  tag?: 'code' | 'docs' | 'config';
}

interface Message {
  role: 'user' | 'assistant';
  content: string;
  sources?: ChatSource[];
  retrieval?: 'semantic' | 'files' | 'none';
}

/** Slim fallback payload, used by the server only if the analysis session has expired. */
function slimAnalysis(a: any) {
  if (!a) return null;
  return {
    repoMeta: a.repoMeta,
    languages: a.languages,
    frameworks: a.frameworks,
    databases: a.databases,
    dependencies: a.dependencies,
    entryPoints: a.entryPoints,
    keyFiles: a.keyFiles,
    quickstart: a.quickstart,
    complexity: { fileList: a.complexity?.fileList || [] },
  };
}

function sourceLink(repoMeta: any, s: ChatSource): string | null {
  const url: string | undefined = repoMeta?.url;
  if (!url || !url.startsWith('https://github.com/')) return null;
  const branch = repoMeta?.default_branch || 'HEAD';
  return `${url.replace(/\.git$/, '').replace(/\/$/, '')}/blob/${branch}/${s.file}#L${s.start_line}-L${s.end_line}`;
}

/** Inline `code` and **bold**. */
function renderInline(text: string): ReactNode[] {
  return text.split(/(`[^`\n]+`|\*\*[^*\n]+\*\*)/g).map((part, i) => {
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return <code key={i} className="px-1 py-0.5 rounded bg-black/10 dark:bg-white/10 font-mono text-[0.85em]">{part.slice(1, -1)}</code>;
    }
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}

/** Minimal Markdown: fenced code blocks, headings, inline code and bold. */
function MessageBody({ content }: { content: string }) {
  const blocks = content.split(/```[\w+-]*\n?/);
  return (
    <div className="text-sm space-y-2">
      {blocks.map((block, i) =>
        i % 2 === 1 ? (
          <pre key={i} className="text-xs bg-black/5 dark:bg-black/30 border border-[var(--border-color)] rounded-lg p-3 overflow-x-auto font-mono whitespace-pre">
            {block.replace(/\n$/, '')}
          </pre>
        ) : (
          <div key={i} className="whitespace-pre-wrap">
            {block.split('\n').map((line, j, arr) => {
              const heading = line.match(/^#{1,4}\s+(.*)$/);
              return (
                <Fragment key={j}>
                  {heading ? <span className="font-semibold">{renderInline(heading[1])}</span> : renderInline(line)}
                  {j < arr.length - 1 && '\n'}
                </Fragment>
              );
            })}
          </div>
        )
      )}
    </div>
  );
}

interface RepoChatProps {
  analysisData: any;
}

// Error types for different scenarios
interface ErrorInfo {
  message: string;
  type: 'rate_limit' | 'auth' | 'unavailable' | 'too_large' | 'generic';
  canRetry: boolean;
  retryAfter?: number;
}

export default function RepoChat({ analysisData }: RepoChatProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ErrorInfo | null>(null);
  const [retryCountdown, setRetryCountdown] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Countdown timer for rate limit
  useEffect(() => {
    if (retryCountdown > 0) {
      const timer = setTimeout(() => setRetryCountdown(retryCountdown - 1), 1000);
      return () => clearTimeout(timer);
    } else if (retryCountdown === 0 && error?.type === 'rate_limit') {
      setError(null);
    }
  }, [retryCountdown, error]);

  const parseError = (err: any): ErrorInfo => {
    const status = err.response?.status;
    const detail = err.response?.data?.detail || '';

    switch (status) {
      case 429: {
        const retryAfter = parseInt(err.response?.headers?.['retry-after'] ?? '', 10);
        return {
          message: detail || 'Rate limit reached. Please wait before sending another message.',
          type: 'rate_limit',
          canRetry: true,
          retryAfter: Number.isFinite(retryAfter) && retryAfter > 0 ? Math.min(retryAfter, 300) : 30,
        };
      }
      case 401:
        return {
          message: 'AI service authentication failed. Please contact support.',
          type: 'auth',
          canRetry: false,
        };
      case 413:
        return {
          message: 'Your analysis session has expired. Re-run the analysis to keep chatting.',
          type: 'generic',
          canRetry: false,
        };
      case 503:
        return {
          message: 'AI service is temporarily unavailable. Please try again later.',
          type: 'unavailable',
          canRetry: true,
        };
      case 400:
        if (detail.includes('too large')) {
          return {
            message: 'The repository is too large for chat. Try asking about specific files.',
            type: 'too_large',
            canRetry: false,
          };
        }
        return {
          message: detail || 'Invalid request. Please try rephrasing your question.',
          type: 'generic',
          canRetry: true,
        };
      default:
        return {
          message: detail || 'Something went wrong. Please try again.',
          type: 'generic',
          canRetry: true,
        };
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading || retryCountdown > 0) return;

    const userMessage = input.trim();
    setInput('');
    setError(null);

    // Add user message
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setIsLoading(true);

    try {
      const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      const sessionId = analysisData?.sessionId;
      const send = (withData: boolean) => axios.post(`${API_BASE_URL}/api/chat`, {
        question: userMessage,
        session_id: sessionId,
        analysis_data: withData ? slimAnalysis(analysisData) : undefined,
        chat_history: messages.map(({ role, content }) => ({ role, content })),
      });
      // The server uses its own session data; only resend the analysis once it has expired.
      let response;
      try {
        response = await send(!sessionId);
      } catch (err: any) {
        if (!sessionId || err.response?.status !== 404) throw err;
        response = await send(true);
      }

      setMessages(prev => [...prev, {
        role: 'assistant',
        content: response.data.response,
        sources: response.data.sources || [],
        retrieval: response.data.retrieval,
      }]);
    } catch (err: any) {
      console.error('Chat error:', err);
      const errorInfo = parseError(err);
      setError(errorInfo);

      if (errorInfo.retryAfter) {
        setRetryCountdown(errorInfo.retryAfter);
      }

      // Take the question out of the history and put it back in the input box, so it can be resent.
      setMessages(prev => prev.slice(0, -1));
      setInput(prev => (prev.trim() ? prev : userMessage));
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  const suggestedQuestions = [
    "What does this repository do?",
    "Explain how the main entry point works",
    "How does the authentication flow work?",
    "Show me the key functions and explain what they do",
    "How do I run this locally and deploy it?",
  ];

  return (
    <div className="flex flex-col h-[640px] bg-[var(--bg-secondary)] rounded-xl border border-[var(--border-color)] overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[var(--border-color)] bg-[var(--bg-tertiary)]">
        <div className="flex items-center gap-2">
          <span className="text-lg">💬</span>
          <h3 className="font-semibold text-[var(--text-primary)]">Chat with Repository</h3>
        </div>
        <p className="text-xs text-[var(--text-secondary)] mt-1">
          {analysisData?.searchIndex?.status === 'ready'
            ? `Answers are grounded in the most relevant code, retrieved from ${analysisData.searchIndex.total} indexed chunks`
            : analysisData?.searchIndex?.status === 'building'
              ? `Indexing code for better answers (${analysisData.searchIndex.indexed}/${analysisData.searchIndex.total})...`
              : 'Ask about code syntax, implementation details, how functions work, and more'}
        </p>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center">
            <div className="text-4xl mb-3">🤖</div>
            <p className="text-[var(--text-secondary)] mb-4">
              Ask me anything about this repository!
            </p>
            <div className="space-y-2">
              <p className="text-xs text-[var(--text-muted)]">Try asking:</p>
              <div className="flex flex-wrap justify-center gap-2">
                {suggestedQuestions.map((q, idx) => (
                  <button
                    key={idx}
                    onClick={() => setInput(q)}
                    className="px-3 py-1.5 text-xs bg-[var(--bg-tertiary)] text-[var(--text-primary)] rounded-full hover:bg-primary-100 dark:hover:bg-primary-900/30 hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          messages.map((msg, idx) => (
            <div
              key={idx}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[85%] min-w-0 px-4 py-2 rounded-2xl ${
                  msg.role === 'user'
                    ? 'bg-primary-600 text-white rounded-br-md'
                    : 'bg-[var(--bg-tertiary)] text-[var(--text-primary)] rounded-bl-md'
                }`}
              >
                {msg.role === 'user'
                  ? <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                  : <MessageBody content={msg.content} />}

                {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && (
                  <div className="mt-3 pt-2 border-t border-[var(--border-color)]">
                    <p className="text-[11px] text-[var(--text-muted)] mb-1.5">
                      Sources ({msg.retrieval === 'semantic' ? 'retrieved for this question' : 'selected files'})
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {msg.sources.map((s, i) => {
                        const href = sourceLink(analysisData?.repoMeta, s);
                        const label = `${s.tag === 'docs' || s.tag === 'config' ? '📘 ' : ''}${s.file.split('/').pop()}:${s.start_line}-${s.end_line}`;
                        const title = `${s.file}${s.symbol ? ` · ${s.symbol}` : ''} (${s.reason})`;
                        const cls = 'px-2 py-0.5 text-[11px] font-mono rounded-full bg-[var(--bg-secondary)] border border-[var(--border-color)] text-[var(--text-secondary)]';
                        return href ? (
                          <a key={i} href={href} target="_blank" rel="noreferrer" title={title}
                             className={`${cls} hover:text-primary-600 dark:hover:text-primary-400 hover:border-primary-400`}>
                            {s.symbol && (s.tag ?? 'code') === 'code' ? `${s.symbol.split('.').pop()} · ` : ''}{label}
                          </a>
                        ) : (
                          <span key={i} title={title} className={cls}>{label}</span>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))
        )}

        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-[var(--bg-tertiary)] px-4 py-3 rounded-2xl rounded-bl-md">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-primary-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                <div className="w-2 h-2 bg-primary-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                <div className="w-2 h-2 bg-primary-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className={`rounded-xl p-3 ${
            error.type === 'rate_limit'
              ? 'bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800'
              : 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800'
          }`}>
            <div className="flex items-start gap-2">
              <span className="text-lg">
                {error.type === 'rate_limit' ? '⏳' : error.type === 'unavailable' ? '🔧' : '⚠️'}
              </span>
              <div className="flex-1">
                <p className={`text-sm font-medium ${
                  error.type === 'rate_limit'
                    ? 'text-amber-800 dark:text-amber-200'
                    : 'text-red-700 dark:text-red-300'
                }`}>
                  {error.message}
                </p>
                {retryCountdown > 0 && (
                  <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                    You can try again in {retryCountdown} seconds
                  </p>
                )}
                {error.canRetry && retryCountdown === 0 && (
                  <button
                    onClick={() => setError(null)}
                    className="text-xs text-primary-600 dark:text-primary-400 hover:underline mt-1"
                  >
                    Dismiss
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="p-4 border-t border-[var(--border-color)]">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={retryCountdown > 0 ? `Wait ${retryCountdown}s...` : "Ask about the repository..."}
            disabled={isLoading || retryCountdown > 0}
            className="flex-1 px-4 py-2 bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded-full
                     text-[var(--text-primary)] placeholder-[var(--text-muted)]
                     focus:ring-2 focus:ring-primary-500 focus:border-primary-500 focus:outline-none
                     disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200"
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim() || retryCountdown > 0}
            className="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-full
                     disabled:opacity-50 disabled:cursor-not-allowed
                     transition-colors flex items-center gap-2 shadow-lg shadow-primary-500/25"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
            </svg>
            <span className="hidden sm:inline">Send</span>
          </button>
        </div>
      </form>
    </div>
  );
}
