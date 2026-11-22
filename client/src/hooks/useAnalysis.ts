import { useState, useCallback, useRef } from 'react';

export interface SearchIndexState {
  status: 'idle' | 'building' | 'ready' | 'failed' | 'unavailable';
  searchable: boolean;
  indexed: number;
  total: number;
  error?: string | null;
}

export interface AnalysisState {
  sessionId: string | null;
  repoMeta: any;
  fileTree: any;
  languages: any;
  frameworks: any;
  databases: any;
  dependencies: any;
  callGraph: { [key: string]: any };
  fileDependencies: any;
  complexity: any;
  architecture: any;
  quickstart: any;
  aiReport: any;
  keyFiles: any[];
  entryPoints: any[];
  searchIndex: SearchIndexState;
  warnings: string[];
  progress: number;
  stage: string;
  events: string[];
  status: 'idle' | 'connecting' | 'streaming' | 'complete' | 'error';
  error: string | null;
}

const initialState = (): AnalysisState => ({
  sessionId: null,
  repoMeta: null,
  fileTree: null,
  languages: null,
  frameworks: null,
  databases: null,
  dependencies: null,
  callGraph: {},
  fileDependencies: {},
  complexity: { files: 0, lines: 0, functions: 0, classes: 0, fileList: [] },
  architecture: null,
  quickstart: null,
  aiReport: null,
  keyFiles: [],
  entryPoints: [],
  searchIndex: { status: 'idle', searchable: false, indexed: 0, total: 0 },
  warnings: [],
  progress: 0,
  stage: '',
  events: [],
  status: 'idle',
  error: null,
});

/** Human-readable activity line for the progress log (null = don't log). */
function describe(eventName: string, data: any): string | null {
  switch (eventName) {
    case 'clone_progress':
      return data.total ? `${data.phase} ${Math.round((100 * data.current) / data.total)}%` : data.phase;
    case 'scan_started': return `Found ${data.total_files} source files`;
    case 'file_complexity_batch': return `Analyzed ${data.processed}/${data.total} files`;
    case 'search_index_progress': return `Embedded ${data.indexed}/${data.total} code chunks`;
    case 'search_index_ready': return data.status === 'ready' ? 'Semantic search index ready' : 'Semantic index unavailable';
    case 'warning': return `⚠ ${data.message}`;
    case 'repo_meta': return 'Fetched repository metadata';
    case 'file_tree': return 'Built file tree';
    case 'language_dist': return 'Computed language distribution';
    case 'key_files': return 'Detected key files & entry points';
    case 'framework_detected': return 'Detected frameworks & dependencies';
    case 'file_dependencies': return 'Built file dependency graph';
    case 'call_graph': return 'Built call graph';
    case 'architecture_ready': return 'Generated architecture';
    case 'quickstart_ready': return 'Generated quick start guide';
    case 'ai_report_ready': return 'AI report ready';
    case 'analysis_complete': return 'Analysis complete';
    default: return null;
  }
}

/** Forget the remembered repo so a reload after a fatal error doesn't retry it forever. */
function forgetRepo(repoUrl: string) {
  sessionStorage.removeItem(`codeexplorer_session_${repoUrl}`);
  if (sessionStorage.getItem('codeexplorer_last_repo') === repoUrl) {
    sessionStorage.removeItem('codeexplorer_last_repo');
  }
}

export function useAnalysis() {
  const [state, setState] = useState<AnalysisState>(initialState);
  const eventSourceRef = useRef<EventSource | null>(null);

  const startAnalysis = useCallback((repoUrl: string, forceNew = false) => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    if (forceNew) {
      sessionStorage.removeItem(`codeexplorer_session_${repoUrl}`);
    }

    let sessionId = sessionStorage.getItem(`codeexplorer_session_${repoUrl}`);
    if (!sessionId) {
      sessionId = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).substring(2, 15);
      sessionStorage.setItem(`codeexplorer_session_${repoUrl}`, sessionId);
    }
    sessionStorage.setItem('codeexplorer_last_repo', repoUrl);

    setState({ ...initialState(), sessionId, stage: 'Connecting...', status: 'connecting' });

    const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    const es = new EventSource(`${API_BASE_URL}/api/analyze/stream?repo=${encodeURIComponent(repoUrl)}&session_id=${sessionId}`);
    eventSourceRef.current = es;

    es.onopen = () => {
      setState(s => (s.status === 'connecting' ? { ...s, status: 'streaming', stage: 'Connected to server...' } : s));
    };

    es.onmessage = (event) => {
      let msg: any;
      try {
        msg = JSON.parse(event.data);
      } catch (err) {
        console.error('Error parsing SSE:', err, event.data);
        return;
      }
      const { event: eventName, stage, progress, data } = msg;

      setState(s => {
        const line = describe(eventName, data);
        const next: AnalysisState = {
          ...s,
          stage: eventName === 'clone_progress' && data.phase ? `${stage}: ${data.phase}` : stage,
          progress: Math.max(s.progress, progress ?? 0),
          events: line ? [line, ...s.events].slice(0, 50) : s.events,
        };

        switch (eventName) {
          case 'repo_meta':
            next.repoMeta = data;
            break;
          case 'file_tree':
            next.fileTree = data;
            break;
          case 'key_files':
            next.keyFiles = data.key_files || data;
            next.entryPoints = data.entry_points || [];
            break;
          case 'language_dist':
            next.languages = data;
            break;
          case 'framework_detected':
            next.frameworks = data.frameworks;
            next.databases = data.databases;
            if (data.dependencies) next.dependencies = data.dependencies;
            break;
          case 'file_complexity_batch': {
            const files: any[] = data.files || [];
            next.complexity = {
              files: s.complexity.files + files.length,
              lines: s.complexity.lines + files.reduce((n, f) => n + (f.lines || 0), 0),
              functions: s.complexity.functions + files.reduce((n, f) => n + (f.functions?.length || 0), 0),
              classes: s.complexity.classes + files.reduce((n, f) => n + (f.classes?.length || 0), 0),
              fileList: [...(s.complexity.fileList || []), ...files],
            };
            break;
          }
          case 'file_dependencies':
            next.fileDependencies = data;
            break;
          case 'call_graph':
            next.callGraph = data;
            break;
          case 'architecture_ready':
            next.architecture = data;
            break;
          case 'quickstart_ready':
            next.quickstart = data;
            break;
          case 'ai_report_ready':
            next.aiReport = data;
            break;
          case 'search_index_progress':
            next.searchIndex = {
              status: 'building',
              searchable: !!data.searchable,
              indexed: data.indexed || 0,
              total: data.total || 0,
            };
            break;
          case 'search_index_ready':
            next.searchIndex = {
              status: data.status,
              searchable: !!data.searchable,
              indexed: data.indexed_chunks || 0,
              total: data.total_chunks || 0,
              error: data.error,
            };
            break;
          case 'warning':
            next.warnings = [...s.warnings, data.message];
            break;
          case 'analysis_complete':
            next.status = 'complete';
            next.stage = 'Analysis Complete';
            es.close();
            break;
          case 'error':
            // Only fatal errors end the analysis; everything else arrives as `warning`.
            if (s.status !== 'complete') {
              next.error = data.message;
              next.status = 'error';
              es.close();
              forgetRepo(repoUrl);
            }
            break;
        }
        return next;
      });
    };

    es.onerror = (err) => {
      if (es.readyState === EventSource.CLOSED) {
        console.error('SSE Connection Closed:', err);
        setState(s => {
          if (s.status === 'complete' || s.status === 'error') return s;
          forgetRepo(repoUrl);
          return { ...s, status: 'error', error: 'Connection to server lost. Please try again.' };
        });
      } else if (es.readyState === EventSource.CONNECTING) {
        // EventSource reconnects automatically; the server replays history for this session.
        // Reset to avoid double-applying replayed incremental events.
        console.warn('SSE Reconnecting...');
        setState(s => (s.status === 'complete' || s.status === 'error')
          ? s
          : { ...initialState(), sessionId: s.sessionId, stage: 'Reconnecting...', status: 'connecting' });
      }
    };
  }, []);

  const cancelAnalysis = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      setState(s => ({ ...s, status: 'idle', stage: 'Cancelled' }));
    }
  }, []);

  const resetAnalysis = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }
    const lastRepo = sessionStorage.getItem('codeexplorer_last_repo');
    if (lastRepo) {
      sessionStorage.removeItem(`codeexplorer_session_${lastRepo}`);
      sessionStorage.removeItem('codeexplorer_last_repo');
    }
    setState(s => ({ ...s, status: 'idle', stage: '', error: null, progress: 0 }));
  }, []);

  return { state, startAnalysis, cancelAnalysis, resetAnalysis };
}
