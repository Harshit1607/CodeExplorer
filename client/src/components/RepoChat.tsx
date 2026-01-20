import { useState, useRef, useEffect } from 'react';
import axios from 'axios';

interface Message {
  role: 'user' | 'assistant';
  content: string;
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
      case 429:
        return {
          message: 'Rate limit reached. Please wait before sending another message.',
          type: 'rate_limit',
          canRetry: true,
          retryAfter: 30,
        };
      case 401:
        return {
          message: 'AI service authentication failed. Please contact support.',
          type: 'auth',
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
      const response = await axios.post(`${API_BASE_URL}/api/chat`, {
        question: userMessage,
        analysis_data: analysisData,
        chat_history: messages,
      });

      // Add assistant response
      setMessages(prev => [...prev, { role: 'assistant', content: response.data.response }]);
    } catch (err: any) {
      console.error('Chat error:', err);
      const errorInfo = parseError(err);
      setError(errorInfo);

      if (errorInfo.retryAfter) {
        setRetryCountdown(errorInfo.retryAfter);
      }

      // Remove the user message if we failed
      setMessages(prev => prev.slice(0, -1));
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  const suggestedQuestions = [
    "What does this repository do?",
    "What are the main entry points?",
    "What frameworks does this project use?",
    "How is the code organized?",
  ];

  return (
    <div className="flex flex-col h-[500px] bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50">
        <div className="flex items-center gap-2">
          <span className="text-lg">💬</span>
          <h3 className="font-semibold text-slate-900 dark:text-white">Chat with Repository</h3>
        </div>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
          Ask questions about the codebase structure, dependencies, and more
        </p>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center">
            <div className="text-4xl mb-3">🤖</div>
            <p className="text-slate-600 dark:text-slate-400 mb-4">
              Ask me anything about this repository!
            </p>
            <div className="space-y-2">
              <p className="text-xs text-slate-500 dark:text-slate-500">Try asking:</p>
              <div className="flex flex-wrap justify-center gap-2">
                {suggestedQuestions.map((q, idx) => (
                  <button
                    key={idx}
                    onClick={() => setInput(q)}
                    className="px-3 py-1.5 text-xs bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-full hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
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
                className={`max-w-[80%] px-4 py-2 rounded-2xl ${
                  msg.role === 'user'
                    ? 'bg-blue-600 text-white rounded-br-md'
                    : 'bg-slate-100 dark:bg-slate-700 text-slate-900 dark:text-white rounded-bl-md'
                }`}
              >
                <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
              </div>
            </div>
          ))
        )}

        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-slate-100 dark:bg-slate-700 px-4 py-3 rounded-2xl rounded-bl-md">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className={`rounded-lg p-3 ${
            error.type === 'rate_limit'
              ? 'bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800'
              : 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800'
          }`}>
            <div className="flex items-start gap-2">
              <span className="text-lg">
                {error.type === 'rate_limit' ? '⏳' : error.type === 'unavailable' ? '🔧' : '⚠️'}
              </span>
              <div className="flex-1">
                <p className={`text-sm font-medium ${
                  error.type === 'rate_limit'
                    ? 'text-yellow-800 dark:text-yellow-200'
                    : 'text-red-700 dark:text-red-300'
                }`}>
                  {error.message}
                </p>
                {retryCountdown > 0 && (
                  <p className="text-xs text-yellow-600 dark:text-yellow-400 mt-1">
                    You can try again in {retryCountdown} seconds
                  </p>
                )}
                {error.canRetry && retryCountdown === 0 && (
                  <button
                    onClick={() => setError(null)}
                    className="text-xs text-blue-600 dark:text-blue-400 hover:underline mt-1"
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
      <form onSubmit={handleSubmit} className="p-4 border-t border-slate-200 dark:border-slate-700">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={retryCountdown > 0 ? `Wait ${retryCountdown}s...` : "Ask about the repository..."}
            disabled={isLoading || retryCountdown > 0}
            className="flex-1 px-4 py-2 bg-slate-100 dark:bg-slate-700 border-0 rounded-full
                     text-slate-900 dark:text-white placeholder-slate-400
                     focus:ring-2 focus:ring-blue-500 focus:outline-none
                     disabled:opacity-50 disabled:cursor-not-allowed"
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim() || retryCountdown > 0}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-full
                     disabled:opacity-50 disabled:cursor-not-allowed
                     transition-colors flex items-center gap-2"
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
