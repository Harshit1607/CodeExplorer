import { useState, useCallback, useRef } from 'react';

export interface AnalysisState {
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
  progress: number;
  stage: string;
  events: string[];
  status: 'idle' | 'connecting' | 'streaming' | 'complete' | 'error';
  error: string | null;
}

export function useAnalysis() {
  const [state, setState] = useState<AnalysisState>({
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
    progress: 0,
    stage: '',
    events: [],
    status: 'idle',
    error: null,
  });

  const eventSourceRef = useRef<EventSource | null>(null);

  const startAnalysis = useCallback((repoUrl: string, forceNew = false) => {
    // Reset state
    setState({
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
      progress: 0,
      stage: 'Connecting...',
      events: [],
      status: 'connecting',
      error: null,
    });

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

    const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    const es = new EventSource(`${API_BASE_URL}/api/analyze/stream?repo=${encodeURIComponent(repoUrl)}&session_id=${sessionId}`);
    eventSourceRef.current = es;

    es.onopen = () => {
      setState(s => ({ ...s, status: 'streaming', stage: 'Connected to server...' }));
    };

    es.onmessage = (event) => {
      // Handle heartbeat
      if (event.data === ": heartbeat") return;
      
      try {
        const msg = JSON.parse(event.data);
        const { event: eventName, stage, progress, data } = msg;

        setState(s => {
          const next = { ...s, stage, progress, events: [eventName, ...s.events].slice(0, 50) };
          
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
            case 'dependency_edge':
              // Incremental graph update for dependencies
              const src = data.source;
              next.fileDependencies = { ...s.fileDependencies };
              if (!next.fileDependencies[src]) {
                next.fileDependencies[src] = { resolved: [], external: [], imports: [] };
              }
              if (!next.fileDependencies[src].resolved.includes(data.target)) {
                next.fileDependencies[src].resolved.push(data.target);
              }
              break;
            case 'call_node':
              next.callGraph = { ...s.callGraph, [data.id]: data.data };
              break;
            case 'call_edge':
              next.callGraph = { ...s.callGraph };
              if (next.callGraph[data.source] && !next.callGraph[data.source].calls.includes(data.target)) {
                next.callGraph[data.source].calls.push(data.target);
              }
              if (next.callGraph[data.target] && !next.callGraph[data.target].called_by.includes(data.source)) {
                next.callGraph[data.target].called_by.push(data.source);
              }
              // If target node doesn't exist, create a stub
              if (!next.callGraph[data.target]) {
                 next.callGraph[data.target] = { name: data.target, file: '', calls: [], called_by: [data.source], language: '' };
              }
              // If source node doesn't exist, create a stub
              if (!next.callGraph[data.source]) {
                 next.callGraph[data.source] = { name: data.source, file: '', calls: [data.target], called_by: [], language: '' };
              }
              break;
            case 'file_complexity':
              next.complexity = { ...s.complexity };
              next.complexity.files += 1;
              next.complexity.lines += data.lines || 0;
              next.complexity.functions += data.functions?.length || 0;
              next.complexity.classes += data.classes?.length || 0;
              next.complexity.fileList = [...(s.complexity.fileList || []), data];
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
            case 'analysis_complete':
              next.status = 'complete';
              next.stage = 'Analysis Complete';
              es.close();
              break;
            case 'error':
              if (s.status !== 'complete') {
                 next.error = data.message;
                 next.status = 'error';
                 es.close();
              }
              break;
          }
          return next;
        });
      } catch (err) {
        console.error('Error parsing SSE:', err, event.data);
      }
    };

    es.onerror = (err) => {
      // Don't treat a normal close or reconnection attempt as a fatal error immediately
      if (es.readyState === EventSource.CLOSED) {
        console.error('SSE Connection Closed:', err);
        setState(s => {
          if (s.status === 'complete' || s.status === 'error') return s;
          return { ...s, status: 'error', error: 'Connection to server lost. Please try again.' };
        });
      } else if (es.readyState === EventSource.CONNECTING) {
        console.warn('SSE Reconnecting...');
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
