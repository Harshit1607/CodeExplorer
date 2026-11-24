import os
import ast
import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Set

from app.core import config
from app.services import source_parser
from app.services import project_manifests
from app.services.import_resolver import ImportResolver
from app.services.fs_utils import inside_repo, read_repo_text


class CodeAnalyzer:
    """
    Comprehensive code analyzer that detects:
    - Languages (with proper names)
    - Frameworks (frontend/backend)
    - Databases
    - Dependencies
    - Entry points
    - File structure
    """

    SKIP_DIRS = {
        ".git", "node_modules", "dist", "build", "__pycache__",
        ".venv", "venv", "env", ".next", "out", "coverage",
        ".pytest_cache", ".mypy_cache", "vendor", "target",
        ".idea", ".vscode", "bower_components",
        # Python / Java / C++ build & vendored-dependency folders
        ".tox", ".nox", ".eggs", "site-packages", ".gradle", ".mvn",
        "cmake-build-debug", "cmake-build-release", "third_party", "3rdparty", ".cargo",
    }

    # Extension to language name mapping
    LANGUAGE_NAMES = {
        ".py": "Python",
        ".pyi": "Python",
        ".js": "JavaScript",
        ".mjs": "JavaScript",
        ".cjs": "JavaScript",
        ".jsx": "JavaScript (React)",
        ".ts": "TypeScript",
        ".mts": "TypeScript",
        ".cts": "TypeScript",
        ".tsx": "TypeScript (React)",
        ".java": "Java",
        ".go": "Go",
        ".rs": "Rust",
        ".rb": "Ruby",
        ".php": "PHP",
        ".cs": "C#",
        ".swift": "Swift",
        ".kt": "Kotlin",
        ".scala": "Scala",
        ".c": "C",
        ".cpp": "C++",
        ".cc": "C++",
        ".cxx": "C++",
        ".h": "C/C++ Header",
        ".hpp": "C++ Header",
        ".hh": "C++ Header",
        ".hxx": "C++ Header",
        ".ipp": "C++ Header",
        ".vue": "Vue",
        ".svelte": "Svelte",
    }

    SOURCE_EXTENSIONS = set(LANGUAGE_NAMES.keys())

    # Files to completely ignore
    IGNORE_FILES = {
        'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
        'composer.lock', 'gemfile.lock', 'cargo.lock', 'poetry.lock',
        '.ds_store', 'thumbs.db',
    }

    # Entry point patterns
    ENTRY_BASENAMES = {
        'main', 'app', 'index', 'application', 'server', 'client',
        'program', 'startup', 'bootstrap', 'init', 'run', 'start',
        'launcher', 'entry', 'root', 'core', 'mod', 'lib',
        '_app', '_document', 'page', 'layout',
        'app.module', 'app.component', 'app-routing.module',
        'manage', 'wsgi', 'asgi', 'settings', 'urls', 'views', 'models',
        'api', 'routes', 'router',
    }

    # API and Route Patterns for Cross-Boundary Call Graph
    API_CALL_REGEX = re.compile(
        r"(?:fetch|axios|api|http)\s*\(\s*['\"`]([^'\"`\?]+).*?['\"`](?:\s*,\s*\{.*?(?:method\s*:\s*['\"](\w+)['\"])?.*?\})?\s*\)|"
        r"(?:axios|api|http)\.(get|post|put|delete|patch)\s*\(\s*['\"`]([^'\"`\?]+).*?['\"`]",
        re.IGNORECASE
    )

    ROUTE_REGEXES = {
        'Express.js': re.compile(r"(?:app|router|route)\.(get|post|put|delete|patch)\s*\(\s*['\"']([^'\"']+)['\"']", re.IGNORECASE),
        'FastAPI': re.compile(r"@(app|router|api)\.(get|post|put|delete|patch)\s*\(\s*['\"']([^'\"']+)['\"']", re.IGNORECASE),
        'Flask': re.compile(r"@app\.route\s*\(\s*['\"']([^'\"']+)['\"'](?:.*methods\s*=\s*\[(.*)\])?", re.IGNORECASE),
        'Django': re.compile(r"path\s*\(\s*['\"']([^'\"']+)['\"']\s*,\s*([\w\.]+)", re.IGNORECASE),
        'Spring Boot': re.compile(r"@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)\s*\(\s*(?:value\s*=\s*)?['\"']([^'\"']+)['\"']", re.IGNORECASE),
        # Rust: #[get("/users/{id}")] async fn handler(...)
        'Actix Web': re.compile(r'#\[(get|post|put|delete|patch)\s*\(\s*"([^"]+)"'),
        'Rocket': re.compile(r'#\[(get|post|put|delete|patch)\s*\(\s*"([^"]+)"'),
        # Rust: .route("/users", get(list_users))
        'Axum': re.compile(r'\.route\s*\(\s*"([^"]+)"\s*,\s*(get|post|put|delete|patch)\s*\(\s*([\w:]+)'),
    }

    DB_QUERY_REGEX = re.compile(
        r"\.(find|findOne|findById|save|create|update|delete|remove|count|aggregate|select|insert|where|first|all)\s*\(|"
        r"objects\.(all|filter|get|create|update|delete)\s*\(|"
        r"(?:SELECT|INSERT|UPDATE|DELETE)\s+.*?\s+FROM\s+",
        re.IGNORECASE
    )

    RESERVED_KEYWORDS = {
        'if', 'else', 'for', 'while', 'do', 'switch', 'case', 'default',
        'break', 'continue', 'return', 'try', 'catch', 'finally', 'throw',
        'function', 'class', 'var', 'let', 'const', 'import', 'export',
        'extends', 'implements', 'interface', 'package', 'public', 'private',
        'protected', 'static', 'async', 'await', 'yield', 'new', 'this',
        'super', 'typeof', 'instanceof', 'void', 'delete', 'in', 'of',
        'boolean', 'number', 'string', 'any', 'void', 'null', 'undefined'
    }

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.files: Dict[str, Dict] = {}
        self.all_imports: List[str] = []
        self.all_npm_deps: Set[str] = set()
        self.all_python_deps: Set[str] = set()
        self.dep_sets: Dict[str, Set[str]] = {}
        self.runtime_dep_sets: Dict[str, Set[str]] = {}
        self._manifest_cache: Optional[Dict[str, List[str]]] = None
        self._entry_cache: Optional[List[str]] = None
        # Temporary storage for full file contents (used for call graph, cleared after)
        self._file_contents: Dict[str, str] = {}
        # Cross-boundary traces
        self.found_routes: List[Dict] = []
        self.found_api_calls: List[Dict] = []
        self.found_db_queries: List[Dict] = []

    def analyze(self) -> Dict[str, Any]:
        """Main analysis entry point."""
        # Collect and analyze source files
        for file_path in self._get_source_files():
            meta = self._analyze_file(file_path)
            if meta:
                rel = str(file_path.relative_to(self.repo_path)).replace("\\", "/")
                self.files[rel] = meta
                self.all_imports.extend(meta.get('imports', []))

        # Extract all dependencies first (needed for framework detection)
        dependencies = self._extract_dependencies()

        # Dependency name sets per ecosystem for framework/db detection
        self._collect_dependency_sets(dependencies)

        # Detect frameworks and databases using collected deps
        frameworks = self._detect_frameworks()
        databases = self._detect_databases()

        # Build file dependency graph
        file_dependencies = self._build_file_dependencies()

        # Build call graph (function-to-function relationships)
        call_graph = self._build_call_graph(file_dependencies, frameworks, databases)

        # Clear temporary content storage to free memory
        self._file_contents.clear()

        # Build architecture model
        from app.services.architecture_service import ArchitectureAnalyzer
        arch_data = {
            'files': self.files,
            'frameworks': frameworks,
            'databases': databases,
            'file_dependencies': file_dependencies,
            'entry_points': self._entry_points(),
        }
        architecture = ArchitectureAnalyzer(arch_data).generate()

        return {
            "languages": self._language_stats(),
            "frameworks": frameworks,
            "databases": databases,
            "dependencies": dependencies,
            "entry_points": self._entry_points(),
            "key_files": self._key_files(),
            "tree": self._build_file_tree(),
            "total_files": len(self.files),
            "complexity": self._complexity(),
            "files": self.files,
            "file_dependencies": file_dependencies,
            "call_graph": call_graph,
            "architecture": architecture,
            "readme": self._extract_readme(),
            "package_manager": self._detect_package_manager(),
            "run_scripts": self._extract_run_scripts(),
            "build_systems": self._build_systems(),
        }

    def _read(self, path) -> Optional[str]:
        """Text of a repository file (path absolute or relative to the repo root), or None when
        it is missing or is a symlink that leads outside the repository."""
        return read_repo_text(self.repo_path, path)

    def _keep_dir(self, name: str) -> bool:
        return name not in self.SKIP_DIRS and not name.endswith(".egg-info")

    def _get_source_files(self) -> List[Path]:
        """Get all source files, excluding ignored directories and files."""
        result = []
        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if self._keep_dir(d)]

            for name in files:
                if name.lower() in self.IGNORE_FILES:
                    continue
                ext = Path(name).suffix.lower()
                if ext in self.SOURCE_EXTENSIONS and inside_repo(self.repo_path, os.path.join(root, name)):
                    result.append(Path(root) / name)

        return result

    # Maximum content size to store (in characters) - ~2000 tokens worth
    MAX_CONTENT_SIZE = 8000

    def _analyze_file(self, path: Path) -> Optional[Dict]:
        """Analyze a single source file."""
        try:
            content = self._read(path)
            if content is None:
                return None  # missing, or a symlink that leads outside the repository
            ext = path.suffix.lower()
            n_lines = len(content.splitlines())
            base = {
                "extension": ext,
                "language": self.LANGUAGE_NAMES.get(ext, "Unknown"),
                "lines": n_lines,
                "size": path.stat().st_size,
            }

            # Minified bundles and huge generated files: count them, but don't parse them. Their
            # "functions" are noise, and the regex fallback (no tree-sitter above its size cap)
            # takes seconds per file. Without stored content they are also left out of the
            # call graph and the search index.
            skipped = self._skip_reason(content, n_lines)
            if skipped:
                return {**base, "imports": [], "functions": [], "classes": [], "has_main": False,
                        "content": "", "content_truncated": True, "skipped": skipped}

            # Store full content for call graph extraction (will be cleared after analysis)
            rel = str(path.relative_to(self.repo_path)).replace("\\", "/")
            self._file_contents[rel] = content

            meta = {
                **base,
                "imports": [],
                "functions": [],
                "classes": [],
                "has_main": False,
                # Store truncated content for LLM context
                "content": content[:self.MAX_CONTENT_SIZE] if len(content) <= self.MAX_CONTENT_SIZE else content[:self.MAX_CONTENT_SIZE] + "\n... [truncated]",
                "content_truncated": len(content) > self.MAX_CONTENT_SIZE
            }

            parsed = source_parser.parse_source(content, ext) if source_parser.supports(ext) else None
            if parsed is not None:
                # Tree-sitter: exact symbols with line ranges, structured imports and call sites.
                meta.update({
                    "imports": parsed.import_strings,
                    "functions": parsed.functions,
                    "classes": parsed.classes,
                    "has_main": parsed.has_main,
                    "symbols": [s.to_dict() for s in parsed.symbols],
                    "import_refs": [r.to_dict() for r in parsed.imports],
                    "parser": "tree-sitter",
                })
                if parsed.package:
                    meta["package"] = parsed.package
                if parsed.type_refs:
                    meta["type_refs"] = sorted(parsed.type_refs)
            elif ext == ".py":
                meta.update(self._analyze_python(content))
            elif ext in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts"}:
                meta.update(self._analyze_js(content))
            elif ext == ".java":
                meta.update(self._analyze_java(content))
            elif ext == ".go":
                meta.update(self._analyze_go(content))

            return meta
        except Exception:
            return None

    @staticmethod
    def _skip_reason(content: str, n_lines: int) -> Optional[str]:
        if len(content) > config.MAX_ANALYZE_BYTES:
            return "too large"
        # Small one-liners are fine to parse; only bundles of real size count as minified.
        if len(content) > 5000 and len(content) / max(n_lines, 1) > config.MAX_AVG_LINE_LENGTH:
            return "minified"
        return None

    def _analyze_python(self, content: str) -> Dict:
        """Analyze Python file."""
        try:
            tree = ast.parse(content)
            imports, funcs, classes = [], [], []

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(a.name for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module)
                elif isinstance(node, ast.FunctionDef):
                    funcs.append(node.name)
                elif isinstance(node, ast.ClassDef):
                    classes.append(node.name)

            return {
                "imports": imports,
                "functions": funcs,
                "classes": classes,
                "has_main": "__main__" in content or "def main" in content
            }
        except:
            return {"imports": [], "functions": [], "classes": [], "has_main": False}

    def _analyze_js(self, content: str) -> Dict:
        """Analyze JavaScript/TypeScript file with comprehensive detection."""
        imports = set()

        # Standard ES6 imports: import X from 'module'
        imports.update(re.findall(r"import\s+.*?\s+from\s+['\"]([^'\"]+)['\"]", content, re.DOTALL))

        # Import only: import 'module' (side effects)
        imports.update(re.findall(r"import\s+['\"]([^'\"]+)['\"]", content))

        # Require statements: require('module')
        imports.update(re.findall(r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", content))

        # Dynamic imports: import('module')
        imports.update(re.findall(r"import\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", content))

        # Re-exports: export * from 'module' or export { x } from 'module'
        imports.update(re.findall(r"export\s+.*?\s+from\s+['\"]([^'\"]+)['\"]", content))

        # Type imports (TypeScript): import type { X } from 'module'
        imports.update(re.findall(r"import\s+type\s+.*?\s+from\s+['\"]([^'\"]+)['\"]", content))

        # Comprehensive function detection
        functions = set()
        # 1. function foo() {}
        functions.update(re.findall(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(", content))
        # 2. const foo = () => {}
        functions.update(re.findall(r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(?:\([^)]*\))?\s*=>", content))
        # 3. const foo = function() {}
        functions.update(re.findall(r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?function\s*[\w\s]*\(", content))
        # 4. class methods: foo() {
        functions.update(re.findall(r"^\s*(?:async\s+)?(?:static\s+)?(?:get\s+|set\s+)?(\w+)\s*\([^)]*\)\s*(?::\s*\w+)?\s*\{", content, re.MULTILINE))
        # 5. Object methods: foo: (args) => { or foo(args) { or foo: function() {
        functions.update(re.findall(r"(\w+)\s*[:\(]\s*(?:async\s*)?(?:function\s*[\w\s]*|\([^)]*\))?\s*(?:=>)?\s*\{", content))

        return {
            "imports": list(imports),
            "functions": [f for f in functions if f.lower() not in self.RESERVED_KEYWORDS],
            "classes": re.findall(r"class\s+(\w+)", content),
            "has_main": any(x in content for x in ["createRoot", "ReactDOM.render", "createApp", "render("])
        }

    def _analyze_java(self, content: str) -> Dict:
        """Analyze Java file."""
        return {
            "imports": re.findall(r"import\s+([\w.]+);", content),
            "functions": re.findall(r"(?:public|private|protected)?\s*(?:static)?\s*\w+\s+(\w+)\s*\([^)]*\)\s*(?:throws\s+\w+\s*)?{", content),
            "classes": re.findall(r"class\s+(\w+)", content),
            "has_main": "public static void main" in content
        }

    def _analyze_go(self, content: str) -> Dict:
        """Analyze Go file."""
        return {
            "imports": re.findall(r'import\s+(?:\(\s*)?["\']([^"\']+)["\']', content),
            "functions": re.findall(r"func\s+(?:\([^)]+\)\s+)?(\w+)", content),
            "classes": [],  # Go doesn't have classes
            "has_main": "func main()" in content
        }

    def _language_stats(self) -> Dict[str, Dict]:
        """Calculate language statistics with proper names."""
        stats = {}
        for meta in self.files.values():
            lang = meta.get("language", "Unknown")
            if lang not in stats:
                stats[lang] = {"count": 0, "lines": 0}
            stats[lang]["count"] += 1
            stats[lang]["lines"] += meta.get("lines", 0)
        return stats

    def _manifests(self) -> Dict[str, List[str]]:
        if getattr(self, "_manifest_cache", None) is None:
            self._manifest_cache = project_manifests.find_manifests(
                str(self.repo_path), self.SKIP_DIRS | {"node_modules", ".git"})
        return self._manifest_cache

    def _extract_dependencies(self) -> Dict[str, Dict[str, List[str]]]:
        """Dependencies from every manifest in the repo, grouped by ecosystem
        (python, javascript, java, rust, cpp, other)."""
        return project_manifests.extract_dependencies(str(self.repo_path), self._manifests())

    def _collect_dependency_sets(self, dependencies: Dict[str, Dict[str, List[str]]]) -> None:
        """Lower-cased dependency names per ecosystem, used by framework/database detection."""
        self.dep_sets = project_manifests.dependency_sets(dependencies)
        # dev/test/build groups excluded: an Express devDependency used as a test server
        # doesn't make the project an Express backend
        self.runtime_dep_sets = project_manifests.dependency_sets(dependencies, runtime_only=True)
        self.all_npm_deps.update(self.dep_sets.get("javascript", set()))
        self.all_python_deps.update(self.dep_sets.get("python", set()))

    def _build_systems(self) -> List[Dict[str, Any]]:
        """Install / build / run / test commands per detected project root."""
        try:
            return project_manifests.build_systems(str(self.repo_path), self._manifests(), self.files,
                                                   getattr(self, "dep_sets", {}))
        except Exception as e:  # never break the quick start over one odd manifest
            print(f"build_systems failed: {e}")
            return []

    def _detect_frameworks(self) -> Dict[str, List[str]]:
        """Detect frontend and backend frameworks."""
        frontend = []
        backend = []

        npm_deps = self.all_npm_deps
        python_deps = self.all_python_deps

        # Check for config files in entire repo
        config_files = set()
        for _, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if self._keep_dir(d)]
            for f in files:
                config_files.add(f.lower())

        # ===== Frontend frameworks =====

        # Next.js
        if 'next.config.js' in config_files or 'next.config.ts' in config_files or 'next.config.mjs' in config_files or 'next' in npm_deps:
            frontend.append('Next.js')
        # React (but not if Next.js already detected)
        elif 'react' in npm_deps or 'react-dom' in npm_deps:
            frontend.append('React')

        # Vue.js
        if 'vue' in npm_deps:
            frontend.append('Vue.js')
        # Nuxt.js
        if 'nuxt' in npm_deps or 'nuxt.config.js' in config_files or 'nuxt.config.ts' in config_files:
            frontend.append('Nuxt.js')

        # Angular
        if '@angular/core' in npm_deps:
            frontend.append('Angular')

        # Svelte
        if 'svelte' in npm_deps:
            frontend.append('Svelte')
        if '@sveltejs/kit' in npm_deps:
            frontend.append('SvelteKit')

        # Build tools
        if 'vite' in npm_deps:
            frontend.append('Vite')

        # CSS frameworks
        if 'tailwindcss' in npm_deps:
            frontend.append('Tailwind CSS')

        # ===== Backend frameworks =====

        # Backends are decided by runtime dependencies: a server framework that only appears in
        # devDependencies / dev extras is a test helper (e.g. ky's test server), not the backend.
        npm_deps = self.runtime_dep_sets.get("javascript", set()) if self.runtime_dep_sets else npm_deps
        python_deps = self.runtime_dep_sets.get("python", set()) if self.runtime_dep_sets else python_deps

        # Python backends
        if 'fastapi' in python_deps:
            backend.append('FastAPI')
        if 'flask' in python_deps:
            backend.append('Flask')
        if 'django' in python_deps or 'manage.py' in config_files:
            backend.append('Django')

        # Node.js backends
        if 'express' in npm_deps:
            backend.append('Express.js')
        if '@nestjs/core' in npm_deps or 'nestjs' in npm_deps:
            backend.append('NestJS')
        if 'koa' in npm_deps:
            backend.append('Koa')
        if '@hapi/hapi' in npm_deps or 'hapi' in npm_deps:
            backend.append('Hapi')

        # Java - Spring Boot (check for specific Spring files/imports)
        if any('springframework' in imp for imp in self.all_imports):
            backend.append('Spring Boot')
        elif 'pom.xml' in config_files or 'build.gradle' in config_files:
            # Check if pom.xml or build.gradle contains spring
            for cfg in ['pom.xml', 'build.gradle']:
                content = (self._read(cfg) or '').lower()
                if 'spring-boot' in content or 'springframework' in content:
                    backend.append('Spring Boot')
                    break

        # Go frameworks - only detect if we actually have Go files
        has_go_files = any(meta.get('language') == 'Go' for meta in self.files.values())
        if has_go_files:
            go_imports = [imp for imp in self.all_imports if 'github.com' in imp or imp.startswith('go/')]
            go_imports_str = ' '.join(go_imports)
            if 'gin-gonic/gin' in go_imports_str:
                backend.append('Gin (Go)')
            if 'gofiber/fiber' in go_imports_str:
                backend.append('Fiber (Go)')
            if 'labstack/echo' in go_imports_str:
                backend.append('Echo (Go)')

        # Ruby on Rails
        if 'gemfile' in config_files:
            if 'rails' in (self._read("Gemfile") or '').lower():
                backend.append('Ruby on Rails')

        # PHP - Laravel
        if 'artisan' in config_files or 'composer.json' in config_files:
            if 'laravel' in (self._read("composer.json") or '').lower():
                backend.append('Laravel')

        self._detect_more_frameworks(frontend, backend, config_files)

        return {
            "frontend": sorted(set(frontend)),
            "backend": sorted(set(backend))
        }

    # Dependency name -> framework, per ecosystem. Matching is on exact names, or on a
    # "group:" / "group." prefix for Java coordinates.
    _FRAMEWORK_RULES = {
        "python": {
            "backend": {"aiohttp": "aiohttp", "tornado": "Tornado", "sanic": "Sanic", "litestar": "Litestar",
                        "starlette": "Starlette", "celery": "Celery", "grpcio": "gRPC"},
            "frontend": {"streamlit": "Streamlit", "gradio": "Gradio", "dash": "Dash", "pyqt5": "Qt (PyQt)",
                         "pyqt6": "Qt (PyQt)", "pyside6": "Qt (PySide)"},
        },
        "javascript": {
            "backend": {"fastify": "Fastify", "hono": "Hono", "@trpc/server": "tRPC", "electron": "Electron"},
            "frontend": {"@remix-run/react": "Remix", "astro": "Astro", "solid-js": "SolidJS",
                         "react-native": "React Native", "expo": "Expo", "@angular/core": "Angular"},
        },
        "rust": {
            "backend": {"actix-web": "Actix Web", "axum": "Axum", "rocket": "Rocket", "warp": "Warp",
                        "poem": "Poem", "tonic": "gRPC (tonic)", "tokio": "Tokio"},
            "frontend": {"tauri": "Tauri", "leptos": "Leptos", "yew": "Yew", "dioxus": "Dioxus",
                         "egui": "egui", "bevy": "Bevy", "iced": "iced"},
        },
        "java": {
            "backend": {"org.springframework.boot": "Spring Boot", "io.quarkus": "Quarkus",
                        "io.micronaut": "Micronaut", "io.vertx": "Vert.x", "io.dropwizard": "Dropwizard",
                        "io.javalin": "Javalin", "jakarta.platform": "Jakarta EE", "io.grpc": "gRPC"},
            "frontend": {"org.openjfx": "JavaFX", "com.android.application": "Android",
                         "com.android.library": "Android", "androidx.compose": "Jetpack Compose"},
        },
        "cpp": {
            "backend": {"drogon": "Drogon", "crow": "Crow", "oatpp": "oat++", "pistache": "Pistache",
                        "grpc": "gRPC", "boost": "Boost"},
            "frontend": {"qt5": "Qt", "qt6": "Qt", "qt": "Qt", "imgui": "Dear ImGui", "wxwidgets": "wxWidgets",
                         "sdl2": "SDL", "sfml": "SFML", "glfw3": "GLFW", "glfw": "GLFW"},
        },
    }

    _ECOSYSTEM_EXTS = {
        "python": (".py",), "javascript": (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts", ".vue", ".svelte"),
        "java": (".java", ".kt", ".scala"), "rust": (".rs",),
        "cpp": (".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx", ".ipp"),
    }

    def _has_sources(self, ecosystem: str) -> bool:
        exts = self._ECOSYSTEM_EXTS.get(ecosystem)
        return exts is None or any(p.endswith(exts) for p in self.files)

    def _detect_more_frameworks(self, frontend: List[str], backend: List[str], config_files: Set[str]) -> None:
        for eco, sides in self._FRAMEWORK_RULES.items():
            for side, rules in sides.items():
                if not self._has_sources(eco):
                    continue  # e.g. an Android packaging script in a C++ library
                deps = self.runtime_dep_sets.get(eco, set()) if side == "backend" else self.dep_sets.get(eco, set())
                if not deps:
                    continue
                target = frontend if side == "frontend" else backend
                for dep_name, framework in rules.items():
                    if eco == "java":
                        hit = any(d == dep_name or d.startswith(dep_name + ":") or d.startswith(dep_name + ".")
                                  for d in deps)
                    else:
                        hit = dep_name in deps
                    if hit:
                        target.append(framework)
        # Spring without Boot
        java = self.dep_sets.get("java", set())
        if "Spring Boot" not in backend and any(d.startswith("org.springframework") for d in java):
            backend.append("Spring")
        if "androidmanifest.xml" in config_files and self._has_sources("java"):
            frontend.append("Android")
        if any(f.endswith(".uproject") for f in config_files):
            frontend.append("Unreal Engine")
        # Starlette is FastAPI's foundation: don't list it twice
        if "FastAPI" in backend and "Starlette" in backend:
            backend.remove("Starlette")

    def _detect_databases(self) -> List[str]:
        """Detect database usage from dependencies and config files."""
        databases = set()

        npm_deps = self.runtime_dep_sets.get("javascript", set()) if self.runtime_dep_sets else self.all_npm_deps
        python_deps = self.runtime_dep_sets.get("python", set()) if self.runtime_dep_sets else self.all_python_deps

        # Check npm dependencies for database packages
        npm_db_mapping = {
            'mongoose': 'MongoDB',
            'mongodb': 'MongoDB',
            'pg': 'PostgreSQL',
            'postgres': 'PostgreSQL',
            'mysql': 'MySQL',
            'mysql2': 'MySQL',
            'redis': 'Redis',
            'ioredis': 'Redis',
            'sqlite3': 'SQLite',
            'better-sqlite3': 'SQLite',
            'sequelize': None,  # ORM, check connection
            'typeorm': None,  # ORM, check connection
            'prisma': None,  # ORM, check schema
            '@prisma/client': None,
            'knex': None,  # Query builder
            '@elastic/elasticsearch': 'Elasticsearch',
            'firebase': 'Firebase',
            'firebase-admin': 'Firebase',
            '@supabase/supabase-js': 'Supabase',
        }

        for dep, db in npm_db_mapping.items():
            if dep in npm_deps and db:
                databases.add(db)

        # Check Python dependencies for database packages
        python_db_mapping = {
            'pymongo': 'MongoDB',
            'motor': 'MongoDB',  # async MongoDB
            'psycopg2': 'PostgreSQL',
            'psycopg2-binary': 'PostgreSQL',
            'asyncpg': 'PostgreSQL',
            'pymysql': 'MySQL',
            'mysqlclient': 'MySQL',
            'mysql-connector-python': 'MySQL',
            'redis': 'Redis',
            'aioredis': 'Redis',
            'sqlite3': 'SQLite',
            'aiosqlite': 'SQLite',
            'sqlalchemy': None,  # ORM
            'django': None,  # Check settings
            'elasticsearch': 'Elasticsearch',
            'firebase-admin': 'Firebase',
        }

        for dep, db in python_db_mapping.items():
            if dep in python_deps and db:
                databases.add(db)

        # Java / Rust / C++ drivers and ORMs
        other_db_rules = {
            "java": {"org.postgresql": "PostgreSQL", "com.mysql": "MySQL", "mysql:mysql-connector-java": "MySQL",
                     "org.mariadb.jdbc": "MySQL", "org.mongodb": "MongoDB", "com.h2database": "H2",
                     "org.xerial:sqlite-jdbc": "SQLite", "redis.clients": "Redis", "io.lettuce": "Redis",
                     "org.springframework.boot:spring-boot-starter-data-redis": "Redis",
                     "org.springframework.boot:spring-boot-starter-data-mongodb": "MongoDB",
                     "com.oracle.database.jdbc": "Oracle", "org.elasticsearch": "Elasticsearch"},
            "rust": {"tokio-postgres": "PostgreSQL", "postgres": "PostgreSQL", "mysql": "MySQL",
                     "mysql_async": "MySQL", "mongodb": "MongoDB", "redis": "Redis", "rusqlite": "SQLite",
                     "sled": "Sled", "rocksdb": "RocksDB", "elasticsearch": "Elasticsearch"},
            "cpp": {"postgresql": "PostgreSQL", "libpq": "PostgreSQL", "libpqxx": "PostgreSQL",
                    "pqxx": "PostgreSQL", "sqlite3": "SQLite", "sqlitecpp": "SQLite", "mysql": "MySQL",
                    "hiredis": "Redis", "redis-plus-plus": "Redis", "mongo-cxx-driver": "MongoDB",
                    "rocksdb": "RocksDB", "leveldb": "LevelDB"},
        }
        for eco, rules in other_db_rules.items():
            deps = self.runtime_dep_sets.get(eco, set())
            for dep_name, db in rules.items():
                if any(d == dep_name or d.startswith(dep_name + ":") or d.startswith(dep_name + ".") for d in deps):
                    databases.add(db)
        # sqlx / diesel / sea-orm pick the database through features: look at Cargo.toml text
        if self.dep_sets.get("rust", set()) & {"sqlx", "diesel", "sea-orm"}:
            for rel in self._manifests().get("cargo", []):
                text = (self._read(rel) or "").lower()
                for needle, db in (("postgres", "PostgreSQL"), ("mysql", "MySQL"), ("sqlite", "SQLite")):
                    if needle in text:
                        databases.add(db)

        # Check Prisma schema for database type
        content = (self._read("prisma/schema.prisma") or '').lower()
        if 'postgresql' in content or 'postgres' in content:
            databases.add('PostgreSQL')
        elif 'mysql' in content:
            databases.add('MySQL')
        elif 'mongodb' in content:
            databases.add('MongoDB')
        elif 'sqlite' in content:
            databases.add('SQLite')

        # Check docker-compose for database services
        for compose_file in ['docker-compose.yml', 'docker-compose.yaml', 'compose.yml', 'compose.yaml']:
            content = (self._read(compose_file) or '').lower()
            if 'postgres' in content:
                databases.add('PostgreSQL')
            if 'mysql' in content or 'mariadb' in content:
                databases.add('MySQL')
            if 'mongo' in content:
                databases.add('MongoDB')
            if 'redis' in content:
                databases.add('Redis')

        # Check .env files for database URLs
        for env_file in ['.env', '.env.example', '.env.local', '.env.development']:
            content = (self._read(env_file) or '').lower()
            if 'mongodb' in content or 'mongo_uri' in content:
                databases.add('MongoDB')
            if 'postgres' in content or 'postgresql' in content:
                databases.add('PostgreSQL')
            if 'mysql' in content:
                databases.add('MySQL')
            if 'redis' in content:
                databases.add('Redis')

        return list(databases)

    # Extensions where file-name conventions (index.ts, app.py, main.go, ...) mark entry points.
    # Rust, Java and C/C++ entry points are structural (fn main, static void main, int main,
    # crate roots), so `mod.rs`, `lib.rs`, `Main.java`, `core.cpp` are not guessed by name.
    _NAME_CONVENTION_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts",
                             ".go", ".rb", ".php", ".vue", ".svelte", ".swift", ".kt", ".scala", ".cs"}

    _SECONDARY_PATH_RE = re.compile(
        r"(^|/)(tests?|__tests__|examples?|samples?|demos?|docs?|fixtures?|benchmarks?|benches|testdata|e2e)(/|$)", re.I)

    def _entry_points(self) -> List[str]:
        """Detect application entry points: strong signals first, then naming conventions."""
        if self._entry_cache is not None:
            return list(self._entry_cache)

        strong: List[str] = []
        weak: List[str] = []
        for path, meta in self.files.items():
            ext = Path(path).suffix.lower()
            basename = Path(path).stem.lower()
            if meta.get("has_main"):
                strong.append(path)
            elif ext == ".rs" and re.search(r"(^|/)src/(main|lib)\.rs$|(^|/)src/bin/[^/]+\.rs$", path):
                strong.append(path)  # crate roots
            elif ext == ".py" and basename in ("__main__", "manage", "wsgi", "asgi"):
                strong.append(path)
            elif ext in self._NAME_CONVENTION_EXTS and basename in self.ENTRY_BASENAMES \
                    and not self._SECONDARY_PATH_RE.search(path):
                weak.append(path)
        strong.extend(self._manifest_entry_points())

        strong_set = set(strong)
        candidates = strong_set | set(weak)
        result = sorted(candidates, key=lambda p: (bool(self._SECONDARY_PATH_RE.search(p)), p not in strong_set, p))
        self._entry_cache = result
        return list(result)

    def _manifest_entry_points(self) -> List[str]:
        """Entry points declared in package.json (main/bin/module) and pyproject [project.scripts]."""
        out = []
        resolver_exts = ("", ".js", ".ts", ".mjs", ".cjs", ".tsx", ".jsx", "/index.js", "/index.ts")
        for rel in self._manifests().get("npm", []):
            try:
                pkg = json.loads(self._read(rel) or "")
            except Exception:
                continue
            base = str(Path(rel).parent).replace("\\", "/")
            base = "" if base == "." else base
            targets = [pkg.get("main"), pkg.get("module")]
            bins = pkg.get("bin")
            targets += list(bins.values()) if isinstance(bins, dict) else [bins]
            for t in targets:
                if not isinstance(t, str):
                    continue
                t = t.lstrip("./")
                for ext in resolver_exts:
                    cand = f"{base}/{t}{ext}" if base else f"{t}{ext}"
                    if cand in self.files:
                        out.append(cand)
                        break
        for rel in self._manifests().get("pyproject", []):
            try:
                import tomllib
                data = tomllib.loads(self._read(rel) or "")
            except Exception:
                continue
            base = str(Path(rel).parent).replace("\\", "/")
            base = "" if base == "." else base
            scripts = (data.get("project") or {}).get("scripts") or {}
            for target in scripts.values():
                module = str(target).split(":")[0].replace(".", "/")
                for cand in (f"{module}.py", f"src/{module}.py", f"{module}/__init__.py", f"src/{module}/__init__.py"):
                    cand = f"{base}/{cand}" if base else cand
                    if cand in self.files:
                        out.append(cand)
                        break
        return out

    def _key_files(self) -> List[str]:
        """Identify key/important files."""
        entry_points = []
        important_files = []

        entry_set = set(self._entry_points())
        for path, meta in self.files.items():
            path_lower = path.lower()

            # Skip test files (pytest, Jest/Vitest, Go, JUnit, Rust/C++ test dirs)
            if any(x in path_lower for x in ['test_', '_test', 'tests/', '/test/', '.test.', '.spec.', '__tests__/']) \
                    or path.endswith(('Test.java', 'Tests.java', 'IT.java')):
                continue

            # Priority 1: Entry point files
            if path in entry_set:
                entry_points.append((path, 1000))
                continue

            # Priority 2: Calculate importance score
            score = (
                len(meta.get("imports", [])) * 2 +
                len(meta.get("classes", [])) * 5 +
                len(meta.get("functions", [])) * 1
            )

            if score >= 8:
                important_files.append((path, score))

        important_files.sort(key=lambda x: x[1], reverse=True)

        result = [f[0] for f in entry_points]
        result.extend([f[0] for f in important_files[:20]])

        return result

    def _build_file_tree(self) -> Dict[str, Any]:
        """Build hierarchical file tree structure."""
        tree = {}

        for file_path, meta in self.files.items():
            parts = Path(file_path).parts
            current = tree

            for i, part in enumerate(parts):
                if i == len(parts) - 1:  # File
                    current[part] = {
                        'type': 'file',
                        'size': meta.get('size', 0),
                        'language': meta.get('language', 'Unknown'),
                        'lines': meta.get('lines', 0)
                    }
                else:  # Directory
                    if part not in current:
                        current[part] = {'type': 'folder', 'children': {}}
                    elif 'children' not in current[part]:
                        current[part] = {'type': 'folder', 'children': {}}
                    current = current[part]['children']

        return tree

    def _complexity(self) -> Dict[str, int]:
        """Calculate overall complexity metrics."""
        return {
            "files": len(self.files),
            "lines": sum(m.get("lines", 0) for m in self.files.values()),
            "functions": sum(len(m.get("functions", [])) for m in self.files.values()),
            "classes": sum(len(m.get("classes", [])) for m in self.files.values()),
        }

    def _build_file_dependencies(self) -> Dict[str, Dict[str, Any]]:
        """
        Build a dependency graph showing what files each file depends on.
        Maps import statements to actual files in the repository.
        """
        file_deps = {}

        # Language-aware resolution for tree-sitter parsed files (Python, JS/TS, Java, Rust, C/C++)
        resolver = None
        if any("import_refs" in m for m in self.files.values()):
            resolver = ImportResolver(self.files, str(self.repo_path))
        file_map = None

        for file_path, meta in self.files.items():
            imports = meta.get('imports', [])
            if resolver is not None and "import_refs" in meta:
                resolved, external = resolver.resolve_file(file_path)
                file_deps[file_path] = {'imports': imports, 'resolved': resolved, 'external': external}
                continue

            # Fallback: generic path matching (Go, Ruby, PHP, ...)
            if file_map is None:
                file_map = self._build_file_map()
            deps = {
                'imports': imports,  # Raw import strings
                'resolved': [],      # Resolved to actual files in repo
                'external': [],      # External packages (not in repo)
            }

            for imp in imports:
                resolved = self._resolve_import(imp, file_path, file_map)
                if resolved:
                    if resolved not in deps['resolved']:
                        deps['resolved'].append(resolved)
                else:
                    # It's an external package
                    if imp not in deps['external']:
                        deps['external'].append(imp)

            file_deps[file_path] = deps

        return file_deps

    def _build_file_map(self) -> Dict[str, str]:
        """
        Build a map from possible import names to actual file paths.
        E.g., 'components/Button' -> 'src/components/Button.tsx'
        """
        file_map = {}

        for file_path in self.files.keys():
            # Normalize path separators
            normalized = file_path.replace('\\', '/')

            # Get various forms of the path that could be used in imports
            path_obj = Path(normalized)
            stem = path_obj.stem  # filename without extension
            parent = str(path_obj.parent).replace('\\', '/') if str(path_obj.parent) != '.' else ''

            # Full path without extension
            no_ext = str(path_obj.with_suffix('')).replace('\\', '/')
            file_map[no_ext] = file_path
            file_map['./' + no_ext] = file_path
            file_map['/' + no_ext] = file_path

            # Full path WITH extension (some imports include extension)
            file_map[normalized] = file_path
            file_map['./' + normalized] = file_path

            # Just the filename (for relative imports)
            file_map[stem] = file_path
            file_map['./' + stem] = file_path

            # For index files, map the directory name
            if stem in ['index', '__init__']:
                if parent:
                    file_map[parent] = file_path
                    file_map['./' + parent] = file_path
                    file_map['/' + parent] = file_path

            # Handle various path formats
            # src/components/Button -> components/Button, Button
            parts = normalized.split('/')
            for i in range(len(parts)):
                partial = '/'.join(parts[i:])
                partial_no_ext = str(Path(partial).with_suffix('')).replace('\\', '/')
                file_map[partial_no_ext] = file_path
                file_map['./' + partial_no_ext] = file_path

                # Also with extension
                file_map[partial] = file_path
                file_map['./' + partial] = file_path

        # Also track common alias paths (src/, @/, etc.)
        for file_path in self.files.keys():
            normalized = file_path.replace('\\', '/')
            # Common aliases like @/components -> src/components
            if normalized.startswith('src/'):
                alias_path = '@/' + normalized[4:]
                alias_no_ext = str(Path(alias_path).with_suffix('')).replace('\\', '/')
                file_map[alias_path] = file_path
                file_map[alias_no_ext] = file_path

        return file_map

    def _resolve_import(self, imp: str, current_file: str, file_map: Dict[str, str]) -> Optional[str]:
        """
        Try to resolve an import string to an actual file in the repository.
        Returns the file path if found, None if it's an external package.
        """
        # Skip obvious external packages
        if imp.startswith('@') and '/' in imp:
            # Scoped npm packages like @types/node, @nestjs/common
            return None
        if not imp.startswith('.') and not imp.startswith('/'):
            # Check if it looks like a node module (no path separators at start)
            # These are likely external: 'react', 'express', 'lodash'
            # But could be aliased paths: 'components/Button'
            pass

        # Clean up the import
        clean_imp = imp.replace('\\', '/')

        # Remove leading ./ or /
        if clean_imp.startswith('./'):
            # Relative import - resolve from current file's directory
            current_dir = str(Path(current_file).parent).replace('\\', '/')
            if current_dir == '.':
                clean_imp = clean_imp[2:]
            else:
                clean_imp = current_dir + '/' + clean_imp[2:]
        elif clean_imp.startswith('../'):
            # Parent directory import
            current_dir = Path(current_file).parent
            while clean_imp.startswith('../'):
                current_dir = current_dir.parent
                clean_imp = clean_imp[3:]
            if str(current_dir) != '.':
                clean_imp = str(current_dir).replace('\\', '/') + '/' + clean_imp
        elif clean_imp.startswith('/'):
            clean_imp = clean_imp[1:]

        # Try to find in file map
        if clean_imp in file_map:
            return file_map[clean_imp]

        # Try with common extensions
        for ext in ['', '.ts', '.tsx', '.js', '.jsx', '.py', '.java', '.go']:
            test_path = clean_imp + ext
            if test_path in file_map:
                return file_map[test_path]

        # Try index files
        for idx in ['/index.ts', '/index.tsx', '/index.js', '/index.jsx', '/index.py', '/__init__.py']:
            test_path = clean_imp + idx
            if test_path in file_map:
                return file_map[test_path]

        # Direct lookup in file map
        return file_map.get(imp)

    def _extract_readme(self) -> Optional[Dict[str, str]]:
        """Extract README content if exists."""
        readme_patterns = ['README.md', 'readme.md', 'README', 'readme.txt', 'README.rst']

        for pattern in readme_patterns:
            content = self._read(pattern)
            if content is not None:
                return {
                    'file': pattern,
                    'content': content[:5000],
                    'full_length': len(content)
                }

        return None

    def _detect_package_manager(self) -> Optional[str]:
        """Detect the package manager used in the project."""
        # Check for lock files (most reliable indicator)
        lock_files = {
            'pnpm-lock.yaml': 'pnpm',
            'yarn.lock': 'yarn',
            'bun.lockb': 'bun',
            'package-lock.json': 'npm',
        }

        for lock_file, manager in lock_files.items():
            if (self.repo_path / lock_file).exists():
                return manager

        # Check if package.json has packageManager field
        pkg_text = self._read('package.json')
        if pkg_text is not None:
            try:
                pkg = json.loads(pkg_text)
                if 'packageManager' in pkg:
                    pm = pkg['packageManager']
                    if 'pnpm' in pm:
                        return 'pnpm'
                    elif 'yarn' in pm:
                        return 'yarn'
                    elif 'bun' in pm:
                        return 'bun'
                    elif 'npm' in pm:
                        return 'npm'
            except:
                pass

        # Default to npm if package.json exists
        if pkg_text is not None:
            return 'npm'

        return None

    def _extract_run_scripts(self) -> Optional[Dict[str, str]]:
        """Extract scripts from package.json."""
        pkg_text = self._read('package.json')
        if pkg_text is None:
            return None

        try:
            pkg = json.loads(pkg_text)
            scripts = pkg.get('scripts', {})
            if scripts:
                # Return important scripts
                important_scripts = {}
                for key in ['start', 'dev', 'serve', 'build', 'test', 'lint']:
                    if key in scripts:
                        important_scripts[key] = scripts[key]
                return important_scripts if important_scripts else None
        except:
            pass

        return None

    # ============================================================
    # Call Graph Methods - Function-to-function call relationships
    # ============================================================

    def _build_call_graph(self, file_dependencies: Dict[str, Dict], frameworks: Dict, databases: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Build a call graph showing which functions call which other functions.
        Also traces cross-boundary calls (Frontend -> API -> Backend -> DB).
        """
        call_graph: Dict[str, Dict[str, Any]] = {}
        self.found_api_calls = []
        self.found_routes = []
        self.found_db_queries = []

        # Phase 1: Build registry of all known functions
        func_registry: Dict[str, List[str]] = {}

        for file_path, meta in self.files.items():
            language = meta.get('language', 'Unknown')
            for func_name in meta.get('functions', []):
                qualified_id = f"{file_path}::{func_name}"
                call_graph[qualified_id] = {
                    "name": func_name,
                    "file": file_path,
                    "calls": [],
                    "called_by": [],
                    "language": language,
                    "type": "function"
                }
                if func_name not in func_registry:
                    func_registry[func_name] = []
                func_registry[func_name].append(qualified_id)

        # Phase 2: Extract backend routes
        self._extract_all_routes(frameworks)

        # Parents of each registered function (class / impl / struct), for qualified calls
        symbol_parents: Dict[str, Set[str]] = {}
        for file_path, meta in self.files.items():
            for sym in meta.get("symbols", []):
                if sym.get("parent") and sym["kind"] in ("function", "method", "macro"):
                    symbol_parents.setdefault(f"{file_path}::{sym['name']}", set()).add(sym["parent"])

        # Barrel files (__init__.py, index.ts, mod.rs, lib.rs) mostly re-export: importing one
        # makes the files *it* imports visible too (`from click import echo` -> utils.py).
        def is_barrel(path: str) -> bool:
            return Path(path).stem in ("__init__", "index", "mod", "lib")
        expanded_deps: Dict[str, Dict] = {}
        for file_path, deps in file_dependencies.items():
            resolved = list(deps.get('resolved', []))
            for dep in list(resolved):
                if is_barrel(dep):
                    resolved.extend(file_dependencies.get(dep, {}).get('resolved', []))
            expanded_deps[file_path] = {'resolved': resolved}

        # Phase 3: Extract call relationships for each file
        for file_path, meta in self.files.items():
            content = self._file_contents.get(file_path, '')
            ext = meta.get('extension', '')

            if "symbols" in meta:  # tree-sitter: real call sites per function
                self._extract_symbol_calls(file_path, meta, content, call_graph, func_registry,
                                           expanded_deps, symbol_parents)
                continue
            if not content:
                continue

            if ext == '.py':
                self._extract_python_calls(file_path, content, call_graph, func_registry, file_dependencies)
            elif ext in {'.js', '.jsx', '.ts', '.tsx'}:
                self._extract_js_calls(file_path, content, call_graph, func_registry, file_dependencies)
            elif ext == '.java':
                self._extract_java_calls(file_path, content, call_graph, func_registry, file_dependencies)
            elif ext == '.go':
                self._extract_go_calls(file_path, content, call_graph, func_registry, file_dependencies)

        # Phase 4: Cross-Boundary Matching & DB Tracing
        self._link_cross_boundary(call_graph, func_registry, databases)

        # Phase 5: Build reverse mapping (called_by)
        # (a set per callee: `x not in list` is quadratic for functions with thousands of callers)
        seen_callers: Dict[str, Set[str]] = {}
        for qualified_id, info in call_graph.items():
            for callee_id in info.get('calls', []):
                if callee_id in call_graph:
                    seen = seen_callers.get(callee_id)
                    if seen is None:
                        seen = seen_callers[callee_id] = set(call_graph[callee_id]['called_by'])
                    if qualified_id not in seen:
                        seen.add(qualified_id)
                        call_graph[callee_id]['called_by'].append(qualified_id)

        return call_graph

    _JS_EXTS = {'.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.mts', '.cts'}
    _SELF_QUALIFIERS = {"self", "this", "Self", "super", "cls"}

    def _extract_symbol_calls(self, file_path: str, meta: Dict, content: str, call_graph: Dict,
                              func_registry: Dict, file_dependencies: Dict,
                              symbol_parents: Dict[str, Set[str]]) -> None:
        """Call edges from parsed call sites (tree-sitter), plus API/DB cross-boundary hints."""
        resolved_deps = set(file_dependencies.get(file_path, {}).get('resolved', []))
        ext = meta.get('extension', '')
        is_js, is_py = ext in self._JS_EXTS, ext in ('.py', '.pyi')
        lines = content.splitlines() if (content and (is_js or is_py)) else []

        for sym in meta.get("symbols", []):
            if sym["kind"] not in ("function", "method", "macro"):
                continue
            caller_id = f"{file_path}::{sym['name']}"
            if caller_id not in call_graph:
                continue
            calls = call_graph[caller_id]['calls']
            for name, qualifier, is_member in sym.get("calls", []):
                if name not in func_registry:
                    continue
                for target_id in self._resolve_symbol_call(name, qualifier, is_member, file_path,
                                                           func_registry, resolved_deps, symbol_parents):
                    if target_id != caller_id and target_id not in calls:
                        calls.append(target_id)

            if lines:
                body = "\n".join(lines[sym["start_line"] - 1: sym["end_line"]])
                if is_js:
                    for api_match in self.API_CALL_REGEX.finditer(body):
                        path = api_match.group(1) or api_match.group(4)
                        method = api_match.group(2) or api_match.group(3) or 'get'
                        if path:
                            self.found_api_calls.append({'caller': caller_id, 'file': file_path,
                                                         'path': path, 'method': method.lower()})
                for db_match in self.DB_QUERY_REGEX.finditer(body):
                    op = db_match.group(1) or db_match.group(2) or 'query'
                    self.found_db_queries.append({'caller': caller_id, 'file': file_path, 'op': op.lower()})

    def _resolve_symbol_call(self, name: str, qualifier: Optional[str], is_member: bool, current_file: str,
                             func_registry: Dict, resolved_deps: Set[str],
                             symbol_parents: Dict[str, Set[str]]) -> List[str]:
        """
        Resolve a call to registered functions:
          self.x() / this.x()   -> same file (same class), else imported files
          Type::x() / Type.x()  -> functions whose parent is Type (impl/class), else module `Type`
          plain / obj.x()       -> same file, then imported files, then unambiguous global matches
        """
        candidates = func_registry.get(name, [])
        if not candidates:
            return []
        same_file = [c for c in candidates if c.startswith(f"{current_file}::")]
        imported = [c for c in candidates if c.split('::', 1)[0] in resolved_deps]

        if qualifier in self._SELF_QUALIFIERS:
            return same_file or imported
        if qualifier:
            by_parent = [c for c in candidates if qualifier in symbol_parents.get(c, ())]
            if by_parent:
                preferred = [c for c in by_parent if c in same_file or c in imported]
                return preferred or by_parent[:3]
            # module / package qualifier: utils.fmt(), click.echo() (package dir), routes::serve()
            by_module = [c for c in candidates
                         if Path(c.split('::', 1)[0]).stem == qualifier or Path(c.split('::', 1)[0]).parent.name == qualifier]
            if by_module:
                preferred = [c for c in by_module if c in imported]
                return preferred or by_module[:3]
        if same_file:
            return same_file
        if imported:
            return imported
        # Unknown receiver / not imported: only link when unambiguous
        if is_member:
            return candidates if len(candidates) == 1 else []
        return candidates if len(candidates) <= 3 else []

    def _extract_python_calls(self, file_path: str, content: str,
                               call_graph: Dict, func_registry: Dict,
                               file_dependencies: Dict):
        """Use AST to extract function calls within each function body in Python."""
        try:
            tree = ast.parse(content)
        except:
            return

        # Get resolved dependencies for this file
        resolved_deps = set(file_dependencies.get(file_path, {}).get('resolved', []))

        # Walk to find all function definitions
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                caller_id = f"{file_path}::{node.name}"
                if caller_id not in call_graph:
                    continue

                # Walk the function body looking for Call nodes
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        callee_name = self._extract_call_name(child)
                        if callee_name and callee_name in func_registry:
                            # Resolve to qualified IDs
                            resolved = self._resolve_call(
                                callee_name, file_path, func_registry, resolved_deps
                            )
                            for target_id in resolved:
                                if target_id != caller_id:  # Skip self-recursion noise
                                    if target_id not in call_graph[caller_id]['calls']:
                                        call_graph[caller_id]['calls'].append(target_id)
                
                # --- Cross-Boundary: DB queries (Python-specific) ---
                for python_db_match in self.DB_QUERY_REGEX.finditer(ast.unparse(node) if hasattr(ast, "unparse") else ""):
                    op = python_db_match.group(1) or python_db_match.group(2) or 'query'
                    self.found_db_queries.append({
                        'caller': caller_id,
                        'file': file_path,
                        'op': op.lower()
                    })

    def _extract_call_name(self, call_node: ast.Call) -> Optional[str]:
        """Extract the function name from an ast.Call node."""
        func = call_node.func
        if isinstance(func, ast.Name):
            return func.id  # Simple call: foo()
        elif isinstance(func, ast.Attribute):
            return func.attr  # Method call: obj.foo() -> "foo"
        return None

    def _extract_js_calls(self, file_path: str, content: str,
                          call_graph: Dict, func_registry: Dict,
                          file_dependencies: Dict):
        """Use regex to find function calls within function bodies in JS/TS."""
        resolved_deps = set(file_dependencies.get(file_path, {}).get('resolved', []))

        # Find function boundaries using regex
        func_pattern = re.compile(
            r'(?:function\s+(\w+)\s*\([^)]*\)\s*\{|'        # function foo() {
            r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>|'  # const foo = () =>
            r'(?:const|let|var)\s+(\w+)\s*=\s*function\s*\(|'  # const foo = function(
            r'(\w+)\s*\([^)]*\)\s*\{)',                         # method() { in class
            re.MULTILINE
        )

        functions_in_file = []

        for match in func_pattern.finditer(content):
            func_name = match.group(1) or match.group(2) or match.group(3) or match.group(4)
            if func_name and func_name.lower() not in self.RESERVED_KEYWORDS:
                start_pos = match.start()
                # Find body end by counting braces
                body_start = content.find('{', match.end() - 10)
                if body_start == -1:
                    # Arrow function without braces - find end of expression
                    body_end = self._find_arrow_end(content, match.end())
                else:
                    body_end = self._find_brace_end(content, body_start)
                if body_end > start_pos:
                    functions_in_file.append((func_name, content[start_pos:body_end]))

        # Build a regex pattern for all known function names (for efficiency)
        known_names = set(func_registry.keys())
        if not known_names:
            return

        call_pattern = re.compile(r'\b([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(')

        # For each function body, search for calls to known functions
        for func_name, body in functions_in_file:
            caller_id = f"{file_path}::{func_name}"
            if caller_id not in call_graph:
                continue

            called_names = set(call_pattern.findall(body))

            for called_name in called_names:
                # Skip very short names to avoid false positives
                if len(called_name) < 2 or called_name not in known_names:
                    continue
                resolved = self._resolve_call(called_name, file_path, func_registry, resolved_deps)
                for target_id in resolved:
                    if target_id != caller_id:
                        if target_id not in call_graph[caller_id]['calls']:
                            call_graph[caller_id]['calls'].append(target_id)
            
            # --- Cross-Boundary: API calls and DB queries ---
            # Detect fetch/axios calls
            for api_match in self.API_CALL_REGEX.finditer(body):
                path = api_match.group(1) or api_match.group(4)
                method = api_match.group(2) or api_match.group(3) or 'get'
                if path:
                    self.found_api_calls.append({
                        'caller': caller_id,
                        'file': file_path,
                        'path': path,
                        'method': method.lower()
                    })
            
            # Detect DB queries (e.g., Mongoose, Prisma)
            for db_match in self.DB_QUERY_REGEX.finditer(body):
                op = db_match.group(1) or db_match.group(2) or 'query'
                self.found_db_queries.append({
                    'caller': caller_id,
                    'file': file_path,
                    'op': op.lower()
                })

    def _extract_java_calls(self, file_path: str, content: str,
                            call_graph: Dict, func_registry: Dict,
                            file_dependencies: Dict):
        """Extract function calls in Java files."""
        resolved_deps = set(file_dependencies.get(file_path, {}).get('resolved', []))

        # Find method boundaries
        method_pattern = re.compile(
            r'(?:public|private|protected)?\s*(?:static)?\s*\w+\s+(\w+)\s*\([^)]*\)\s*(?:throws\s+[\w,\s]+\s*)?\{',
            re.MULTILINE
        )

        methods_in_file = []
        for match in method_pattern.finditer(content):
            method_name = match.group(1)
            if method_name:
                body_start = content.find('{', match.start())
                if body_start != -1:
                    body_end = self._find_brace_end(content, body_start)
                    if body_end > body_start:
                        methods_in_file.append((method_name, content[body_start:body_end]))

        known_names = set(func_registry.keys())
        call_pattern = re.compile(r'\b([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(')

        for method_name, body in methods_in_file:
            caller_id = f"{file_path}::{method_name}"
            if caller_id not in call_graph:
                continue

            called_names = set(call_pattern.findall(body))
            for called_name in called_names:
                if len(called_name) < 2 or called_name not in known_names:
                    continue
                resolved = self._resolve_call(called_name, file_path, func_registry, resolved_deps)
                for target_id in resolved:
                    if target_id != caller_id:
                        if target_id not in call_graph[caller_id]['calls']:
                            call_graph[caller_id]['calls'].append(target_id)

    def _extract_go_calls(self, file_path: str, content: str,
                          call_graph: Dict, func_registry: Dict,
                          file_dependencies: Dict):
        """Extract function calls in Go files."""
        resolved_deps = set(file_dependencies.get(file_path, {}).get('resolved', []))

        # Find function boundaries
        func_pattern = re.compile(r'func\s+(?:\([^)]+\)\s+)?(\w+)\s*\([^)]*\)\s*(?:\([^)]*\)\s*)?\{', re.MULTILINE)

        funcs_in_file = []
        for match in func_pattern.finditer(content):
            func_name = match.group(1)
            if func_name:
                body_start = content.find('{', match.start())
                if body_start != -1:
                    body_end = self._find_brace_end(content, body_start)
                    if body_end > body_start:
                        funcs_in_file.append((func_name, content[body_start:body_end]))

        known_names = set(func_registry.keys())
        call_pattern = re.compile(r'\b([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(')

        for func_name, body in funcs_in_file:
            caller_id = f"{file_path}::{func_name}"
            if caller_id not in call_graph:
                continue

            called_names = set(call_pattern.findall(body))
            for called_name in called_names:
                if len(called_name) < 2 or called_name not in known_names:
                    continue
                resolved = self._resolve_call(called_name, file_path, func_registry, resolved_deps)
                for target_id in resolved:
                    if target_id != caller_id:
                        if target_id not in call_graph[caller_id]['calls']:
                            call_graph[caller_id]['calls'].append(target_id)

    def _find_brace_end(self, content: str, start: int) -> int:
        """Find matching closing brace from a position."""
        depth = 0
        i = start
        in_string = False
        string_char = None

        while i < len(content):
            char = content[i]

            # Handle strings
            if char in '"\'`' and (i == 0 or content[i-1] != '\\'):
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char:
                    in_string = False
                    string_char = None

            if not in_string:
                if char == '{':
                    depth += 1
                elif char == '}':
                    depth -= 1
                    if depth == 0:
                        return i + 1
            i += 1
        return len(content)

    def _find_arrow_end(self, content: str, start: int) -> int:
        """Find end of arrow function expression (no braces)."""
        # Look for common terminators: semicolon, newline followed by non-continuation
        i = start
        paren_depth = 0

        while i < len(content):
            char = content[i]
            if char == '(':
                paren_depth += 1
            elif char == ')':
                paren_depth -= 1
            elif paren_depth == 0:
                if char == ';':
                    return i
                elif char == '\n':
                    # Check if next non-whitespace is a continuation
                    j = i + 1
                    while j < len(content) and content[j] in ' \t':
                        j += 1
                    if j < len(content) and content[j] not in '.?:&|':
                        return i
            i += 1
        return len(content)

    def _resolve_call(self, func_name: str, current_file: str,
                      func_registry: Dict, resolved_deps: Set[str]) -> List[str]:
        """Resolve a function name to qualified IDs, preferring same-file match."""
        candidates = func_registry.get(func_name, [])
        if not candidates:
            return []

        # Prefer same-file match
        same_file = [c for c in candidates if c.startswith(f"{current_file}::")]
        if same_file:
            return same_file

        # Then prefer files that are imported by current file
        imported_matches = [c for c in candidates
                           if c.split('::')[0] in resolved_deps]
        if imported_matches:
            return imported_matches

        # Fallback: return limited candidates to avoid explosion
        return candidates[:3]

    # === Cross-Boundary Trace Helpers ===

    def _extract_all_routes(self, frameworks: Dict):
        """Discover all backend API routes in the codebase, including router prefixes."""
        # Use detected frameworks or try all if none detected
        backend_fws = frameworks.get('backend', [])
        if not backend_fws:
            backend_fws = list(self.ROUTE_REGEXES.keys())
        
        # Maps file path to its common route prefix (detected from include_router/app.use)
        file_prefixes = {}
        
        # Pre-pass: Detect router prefixes in main files
        for file_path, content in self._file_contents.items():
            # FastAPI prefixes: app.include_router(user_router, prefix="/user")
            for m in re.finditer(r'include_router\s*\(\s*(\w+).*?prefix\s*=\s*[\'"]([^\'"]+)[\'"]', content):
                router_name = m.group(1)
                prefix = m.group(2)
                import_match = re.search(r'from\s+([\w\.]+)\s+import\s+.*?\b' + router_name + r'\b', content)
                if import_match:
                    module_path = import_match.group(1).replace('.', '/')
                    file_prefixes[module_path] = prefix

            # Express prefixes: app.use('/user', userRouter)
            for m in re.finditer(r'app\.use\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*(\w+)', content):
                prefix = m.group(1)
                router_name = m.group(2)
                import_match = re.search(r'(?:const|let|var|import).*?\b' + router_name + r'\b.*?from\s+[\'"]([^\'"]+)[\'"]', content)
                if import_match:
                    module_path = import_match.group(1).strip('./').replace('\\', '/')
                    file_prefixes[module_path] = prefix

        for file_path, content in self._file_contents.items():
            # Get prefix for this file if known
            base_prefix = ""
            norm_file_path = file_path.replace('\\', '/')
            for mod, pre in file_prefixes.items():
                if mod in norm_file_path:
                    base_prefix = pre
                    break
            
            for fw in backend_fws:
                regex = self.ROUTE_REGEXES.get(fw)
                if not regex:
                    continue
                
                for match in regex.finditer(content):
                    method = 'get'
                    path = ''
                    handler = ''
                    middlewares = []
                    
                    if fw == 'Express.js':
                        method = match.group(1).lower()
                        path = match.group(2)
                        end_stmt = content.find(')', match.end())
                        if end_stmt != -1:
                            args_segment = content[match.end():end_stmt]
                            found_handlers = re.findall(r'(\w+(?:\.\w+)*)', args_segment)
                            if found_handlers:
                                handler = found_handlers[-1]
                                middlewares = found_handlers[:-1]
                    elif fw == 'FastAPI':
                        method = match.group(2).lower()
                        path = match.group(3)
                        handler = self._find_next_python_function(content, match.end())
                    elif fw == 'Flask':
                        path = match.group(1)
                        method_match = match.group(2)
                        method = 'get' if not method_match or 'GET' in method_match.upper() else 'post'
                        handler = self._find_next_python_function(content, match.end())
                    elif fw == 'Django':
                        path = match.group(1)
                        handler_full = match.group(2)
                        handler = handler_full.split('.')[-1]
                    elif fw == 'Spring Boot':
                        annotation = match.group(1).lower()
                        path = match.group(2)
                        if 'get' in annotation: method = 'get'
                        elif 'post' in annotation: method = 'post'
                        elif 'put' in annotation: method = 'put'
                        elif 'delete' in annotation: method = 'delete'
                        handler_match = re.search(r'public\s+\w+\s+(\w+)\s*\(', content[match.end():])
                        handler = handler_match.group(1) if handler_match else None
                    elif fw in ('Actix Web', 'Rocket'):
                        method = match.group(1).lower()
                        path = match.group(2)
                        handler_match = re.search(r'\bfn\s+(\w+)', content[match.end():])
                        handler = handler_match.group(1) if handler_match else None
                    elif fw == 'Axum':
                        path = match.group(1)
                        method = match.group(2).lower()
                        handler = match.group(3).split('::')[-1]
                    
                    if path and handler:
                        # Combine base_prefix and path
                        full_path = (base_prefix.rstrip('/') + '/' + path.lstrip('/')).strip('/')
                        if not full_path: full_path = "/"
                        
                        # Also keep a version without the base_prefix just in case the prefix detection was wrong
                        self.found_routes.append({
                            'file': file_path,
                            'path': full_path,
                            'original_path': path.strip('/'),
                            'method': method,
                            'handler': handler,
                            'middlewares': middlewares
                        })

    def _find_next_python_function(self, content: str, start_pos: int) -> Optional[str]:
        """Find the next Python function definition after a position."""
        match = re.search(r'def\s+(\w+)', content[start_pos:])
        return match.group(1) if match else None

    def _link_cross_boundary(self, call_graph: Dict, func_registry: Dict, databases: List[str]):
        """Connect frontend API calls to backend routes (with middleware chain) and DB."""
        # Match API calls to Routes
        for api in self.found_api_calls:
            # Create a virtual api-call node
            api_node_id = f"api-call::{api['method'].upper()}::{api['path']}"
            if api_node_id not in call_graph:
                call_graph[api_node_id] = {
                    "name": f"{api['method'].upper()} {api['path']}",
                    "file": api.get('file', '(frontend)'),
                    "calls": [],
                    "called_by": [],
                    "language": "API",
                    "type": "api-call"
                }
            
            # Connect caller to api-call
            caller_id = api['caller']
            if caller_id in call_graph:
                if api_node_id not in call_graph[caller_id]['calls']:
                    call_graph[caller_id]['calls'].append(api_node_id)
            
            # Match to backend route
            matched_route = self._match_route(api['path'], api['method'])
            if matched_route:
                # Start tracking from the API node
                prev_id = api_node_id
                
                # Link middlewares in sequence
                for mw in matched_route.get('middlewares', []):
                    mw_name = mw.split('.')[-1]
                    mw_candidates = func_registry.get(mw_name, [])
                    # Prefer middleware in the same file as the route
                    mw_id = next((c for c in mw_candidates if c.startswith(f"{matched_route['file']}::")), None)
                    if not mw_id and mw_candidates: mw_id = mw_candidates[0]
                    
                    if mw_id:
                        if mw_id not in call_graph[prev_id]['calls']:
                            call_graph[prev_id]['calls'].append(mw_id)
                        call_graph[mw_id]['type'] = 'middleware'
                        prev_id = mw_id
                
                # Final Handler
                handler_name = matched_route['handler']
                # If handler is Class.method, try matching against just 'method' as well
                if '.' in handler_name:
                    method_only = handler_name.split('.')[-1]
                    # Check if qualified ID exists for Class.method
                    route_handler_id = f"{matched_route['file']}::{handler_name}"
                    if route_handler_id not in call_graph:
                        route_handler_id = f"{matched_route['file']}::{method_only}"
                else:
                    route_handler_id = f"{matched_route['file']}::{handler_name}"

                if route_handler_id in call_graph:
                    call_graph[route_handler_id]['type'] = 'route'
                    if route_handler_id not in call_graph[prev_id]['calls']:
                        call_graph[prev_id]['calls'].append(route_handler_id)
                else:
                    # Create a virtual route node if handler not in call graph
                    virtual_route_id = f"route::{matched_route['method'].upper()}::{matched_route['path']}"
                    if virtual_route_id not in call_graph:
                        call_graph[virtual_route_id] = {
                            "name": f"Handler: {matched_route['handler']}",
                            "file": matched_route['file'],
                            "calls": [],
                            "called_by": [],
                            "language": "Backend",
                            "type": "route"
                        }
                    if virtual_route_id not in call_graph[prev_id]['calls']:
                        call_graph[prev_id]['calls'].append(virtual_route_id)

        # Tracing DB Queries
        for db in self.found_db_queries:
            db_node_id = f"db-query::{db['op'].upper()}"
            if db_node_id not in call_graph:
                call_graph[db_node_id] = {
                    "name": f"DB {db['op'].upper()}",
                    "file": "(database space)",
                    "calls": [],
                    "called_by": [],
                    "language": "SQL",
                    "type": "db-query"
                }
            
            caller_id = db['caller']
            if caller_id in call_graph:
                if db_node_id not in call_graph[caller_id]['calls']:
                    call_graph[caller_id]['calls'].append(db_node_id)
                if call_graph[caller_id]['type'] == 'function':
                    call_graph[caller_id]['type'] = 'service'

    def _match_route(self, api_path: str, api_method: str) -> Optional[Dict]:
        """Match an API path to a backend route definition with improved fuzzy matching."""
        # Clean the api_path
        api_path = re.sub(r'^\$\{[^}]+\}/?', '', api_path)
        api_path = re.sub(r'^https?://[^/]+/?', '', api_path)
        api_path = api_path.strip('/').split('?')[0]
        if not api_path: api_path = "/"

        for route in self.found_routes:
            if route['method'].lower() != api_method.lower() and route['method'].lower() != 'any':
                continue
            
            paths_to_try = [route['path'].strip('/'), route.get('original_path', '').strip('/')]
            
            for rp in paths_to_try:
                if not rp: rp = "/"
                
                # 1. Exact match
                if api_path == rp:
                    return route
                
                # 2. Fuzzy prefix match
                if api_path.endswith('/' + rp) or (rp == "/" and api_path in ["api", ""]):
                    return route
                
                # 3. Dynamic parameter matching
                pattern = re.sub(r'[:{][\w-]+}', r'[^/]+', rp)
                pattern = re.sub(r':[\w-]+', r'[^/]+', pattern)
                
                try:
                    if re.fullmatch(pattern, api_path) or api_path.endswith('/' + pattern):
                        return route
                except:
                    continue

        return None
