import os
import uuid
import json
import time
import httpx
import threading
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from git import Repo, GitCommandError
from pathlib import Path
import shutil
import asyncio

from app.services.code_analyzer import CodeAnalyzer
from app.services.architecture_service import ArchitectureAnalyzer
from app.services.ai_analyzer import AIAnalyzer

def format_sse(event: str, stage: str, progress: int, data: dict) -> str:
    msg = {
        "event": event,
        "stage": stage,
        "progress": progress,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    return f"data: {json.dumps(msg)}\n\n"

class StreamingPipeline:
    def __init__(self, repo_url: str, session_id: str = None):
        self.repo_url = repo_url.strip()
        self.repo_id = session_id or str(uuid.uuid4())
        
        if os.name == 'nt':
            self.base_dir = os.path.join(os.environ.get('TEMP', 'C:\\temp'), "codeexplorer")
        else:
            self.base_dir = "/tmp/codeexplorer"
            
        self.repo_path = os.path.join(self.base_dir, self.repo_id)
        
        self.history = []
        self.clients = set()
        self.is_done = False
        self.executor = ThreadPoolExecutor(max_workers=8)
        
        # We'll instantiate the analyzer after creating the path
        os.makedirs(self.base_dir, exist_ok=True)
        self.analyzer = CodeAnalyzer(self.repo_path)
        self.clone_done = threading.Event()
        
        self.analyzed_files = set()
        self.lock = threading.Lock()
        self.errors = []
        
    async def broadcast(self, event_str: str):
        self.history.append(event_str)
        for q in self.clients:
            await q.put(event_str)
            
    def register_client(self, q: asyncio.Queue):
        self.clients.add(q)
        
    def unregister_client(self, q: asyncio.Queue):
        if q in self.clients:
            self.clients.remove(q)
        
    async def run(self):
        heartbeat_task = asyncio.create_task(self._heartbeat())
        try:
            await self._fetch_repo_meta()
            
            clone_task = asyncio.create_task(self._clone_repo())
            scan_task = asyncio.create_task(self._watch_and_scan())
            
            await clone_task
            self.clone_done.set()
            await scan_task
            
            await self._run_deep_analysis()
            
            print(f"[{self.repo_id}] Analysis complete, broadcasting final event...")
            await self.broadcast(format_sse("analysis_complete", "Complete", 100, {"message": "All done"}))
            self.is_done = True
            
        except Exception as e:
            await self.broadcast(format_sse("error", "Pipeline", 100, {"message": str(e)}))
            self.is_done = True
        finally:
            heartbeat_task.cancel()
            self._cleanup()
            
    async def _heartbeat(self):
        try:
            while not self.is_done:
                await asyncio.sleep(5)  # More frequent heartbeats
                await self.broadcast(": heartbeat\n\n")
        except asyncio.CancelledError:
            pass

    async def _fetch_repo_meta(self):
        try:
            parts = self.repo_url.rstrip('/').split('/')
            if len(parts) >= 2:
                owner, name = parts[-2], parts[-1]
                if name.endswith('.git'): name = name[:-4]
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(f"https://api.github.com/repos/{owner}/{name}")
                    if resp.status_code == 200:
                        meta = resp.json()
                        await self.broadcast(format_sse("repo_meta", "Stage 1", 5, {
                            "url": self.repo_url,
                            "name": meta.get("name"),
                            "description": meta.get("description"),
                            "stars": meta.get("stargazers_count"),
                            "language": meta.get("language"),
                            "size": meta.get("size"),
                            "default_branch": meta.get("default_branch")
                        }))
        except Exception as e:
            self.errors.append(str(e))
            await self.broadcast(format_sse("error", "Stage 1", 5, {"message": str(e)}))

    async def _clone_repo(self):
        loop = asyncio.get_event_loop()
        def _clone():
            try:
                os.makedirs(self.repo_path, exist_ok=True)
                Repo.clone_from(self.repo_url, self.repo_path, depth=1)
            except Exception as e:
                self.errors.append(f"Clone failed: {e}")
        await loop.run_in_executor(self.executor, _clone)

    async def _watch_and_scan(self):
        while not self.clone_done.is_set():
            if os.path.exists(self.repo_path):
                files_found = self._get_unprocessed_files()
                if files_found:
                    await self._process_batch(files_found)
            await asyncio.sleep(0.5)
            
        # Final pass
        files_found = self._get_unprocessed_files()
        if files_found:
            await self._process_batch(files_found)
            
        tree = self.analyzer._build_file_tree()
        await self.broadcast(format_sse("file_tree", "Stage 2", 15, tree))
        
    def _get_unprocessed_files(self):
        if not os.path.exists(self.repo_path): return []
        current_files = []
        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in self.analyzer.SKIP_DIRS]
            for name in files:
                if name.lower() in self.analyzer.IGNORE_FILES: continue
                ext = Path(name).suffix.lower()
                if ext in self.analyzer.SOURCE_EXTENSIONS:
                    path = Path(root) / name
                    if str(path) not in self.analyzed_files:
                        current_files.append(path)
        return current_files

    async def _process_batch(self, files):
        loop = asyncio.get_event_loop()
        def _process():
            for f in files:
                with self.lock:
                    if str(f) in self.analyzed_files:
                        continue
                    self.analyzed_files.add(str(f))
                
                meta = self.analyzer._analyze_file(f)
                if meta:
                    rel = str(f.relative_to(self.repo_path)).replace("\\", "/")
                    with self.lock:
                        self.analyzer.files[rel] = meta
                        self.analyzer.all_imports.extend(meta.get('imports', []))
                    
                    complexity = {
                        "file": rel,
                        "lines": meta.get("lines", 0),
                        "functions": meta.get("functions", []),
                        "classes": meta.get("classes", [])
                    }
                    asyncio.run_coroutine_threadsafe(
                        self.broadcast(format_sse("file_complexity", "Stage 2", 85, complexity)),
                        loop
                    )
        await loop.run_in_executor(self.executor, _process)

    async def _run_deep_analysis(self):
        loop = asyncio.get_event_loop()
        
        def _lang():
            lang = self.analyzer._language_stats()
            asyncio.run_coroutine_threadsafe(self.broadcast(format_sse("language_dist", "Stage 3", 30, lang)), loop)
        await loop.run_in_executor(self.executor, _lang)
        
        def _keys():
            keys = self.analyzer._key_files()
            # Also emit entry points
            eps = self.analyzer._entry_points()
            asyncio.run_coroutine_threadsafe(self.broadcast(format_sse("key_files", "Stage 3", 20, {
                "key_files": keys,
                "entry_points": eps
            })), loop)
        await loop.run_in_executor(self.executor, _keys)
        
        def _deps():
            deps = self.analyzer._extract_dependencies()
            for ds in deps.get('javascript', {}).values(): self.analyzer.all_npm_deps.update(ds)
            for ds in deps.get('python', {}).values(): self.analyzer.all_python_deps.update(d.lower() for d in ds)
            
            fw = self.analyzer._detect_frameworks()
            db = self.analyzer._detect_databases()
            asyncio.run_coroutine_threadsafe(self.broadcast(format_sse("framework_detected", "Stage 3", 40, {"frameworks": fw, "databases": db, "dependencies": deps})), loop)
            return deps, fw, db
            
        deps, fw, db = await loop.run_in_executor(self.executor, _deps)
        
        def _file_deps():
            fd = self.analyzer._build_file_dependencies()
            for src, data in fd.items():
                for target in data['resolved']:
                    edge = {"source": src, "target": target}
                    asyncio.run_coroutine_threadsafe(self.broadcast(format_sse("dependency_edge", "Stage 3", 60, edge)), loop)
            return fd
        file_deps = await loop.run_in_executor(self.executor, _file_deps)
        
        def _call_graph():
            cg = self.analyzer._build_call_graph(file_deps, fw, db)
            # Emit nodes first
            for func_id, node_data in cg.items():
                asyncio.run_coroutine_threadsafe(self.broadcast(format_sse("call_node", "Stage 3", 70, {
                    "id": func_id,
                    "data": node_data
                })), loop)
                # Emit edges
                for target in node_data.get("calls", []):
                    asyncio.run_coroutine_threadsafe(self.broadcast(format_sse("call_edge", "Stage 3", 75, {
                        "source": func_id,
                        "target": target
                    })), loop)
            return cg
        call_graph = await loop.run_in_executor(self.executor, _call_graph)
        
        def _arch():
            arch_data = {
                'files': self.analyzer.files,
                'frameworks': fw,
                'databases': db,
                'file_dependencies': file_deps,
                'entry_points': self.analyzer._entry_points(),
            }
            arch = ArchitectureAnalyzer(arch_data).generate()
            asyncio.run_coroutine_threadsafe(self.broadcast(format_sse("architecture_ready", "Stage 3", 92, arch)), loop)
        await loop.run_in_executor(self.executor, _arch)
        
        def _qs():
            qs = {
                "readme": self.analyzer._extract_readme(),
                "package_manager": self.analyzer._detect_package_manager(),
                "run_scripts": self.analyzer._extract_run_scripts()
            }
            asyncio.run_coroutine_threadsafe(self.broadcast(format_sse("quickstart_ready", "Stage 3", 96, qs)), loop)
            return qs
        qs = await loop.run_in_executor(self.executor, _qs)

        async def _ai_report():
            # Gather all current results for the AI context
            analysis_data = {
                "repoMeta": {
                    "url": self.repo_url,
                    "name": self.repo_url.split('/')[-1]
                },
                "languages": self.analyzer._language_stats(),
                "frameworks": fw,
                "databases": db,
                "entryPoints": self.analyzer._entry_points(),
                "keyFiles": self.analyzer._key_files(),
                "complexity": {
                    "fileList": [
                        {
                            "file": rel,
                            "lines": m.get("lines", 0),
                            "functions": m.get("functions", []),
                            "classes": m.get("classes", [])
                        } for rel, m in self.analyzer.files.items()
                    ]
                },
                "quickstart": qs
            }
            
            ai = AIAnalyzer(analysis_data)
            report = await ai.generate_report()
            await self.broadcast(format_sse("ai_report_ready", "Stage 4", 99, report))

        # Run AI report generation
        await _ai_report()

    def _cleanup(self):
        try:
            if os.path.exists(self.repo_path):
                shutil.rmtree(self.repo_path, ignore_errors=True)
        except:
            pass
        self.executor.shutdown(wait=False)
