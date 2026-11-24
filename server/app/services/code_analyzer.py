import os
import ast
import posixpath
import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Set

from app.services import source_parser
from app.services import project_manifests
from app.services import path_classifier
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
        architecture = self._architecture(frameworks, databases, file_dependencies, self._entry_points())

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

            # Store full content for call graph extraction (will be cleared after analysis)
            rel = str(path.relative_to(self.repo_path)).replace("\\", "/")
            self._file_contents[rel] = content

            meta = {
                "extension": ext,
                "language": self.LANGUAGE_NAMES.get(ext, "Unknown"),
                "lines": len(content.splitlines()),
                "size": path.stat().st_size,
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
        """Lower-cased dependency names per ecosystem, used by framework/database detection.
        Only manifests of the product itself count: `examples/celery/requirements.txt` does not
        make the repository a Celery + Redis project."""
        detection = self._primary_dependency_groups(dependencies)
        self.dep_sets = project_manifests.dependency_sets(detection)
        # dev/test/build groups excluded: an Express devDependency used as a test server
        # doesn't make the project an Express backend
        self.runtime_dep_sets = project_manifests.dependency_sets(detection, runtime_only=True)
        self.all_npm_deps.update(self.dep_sets.get("javascript", set()))
        self.all_python_deps.update(self.dep_sets.get("python", set()))

    @staticmethod
    def _primary_dependency_groups(dependencies: Dict[str, Dict[str, List[str]]]) -> Dict[str, Dict[str, List[str]]]:
        """Dependency groups whose manifest lives outside tests / examples / docs. Falls back to
        every group when the repository has no such manifest (a collection of examples)."""
        def manifest_dir(key: str) -> str:
            # "examples/celery/pyproject.toml (dev/optional)", "frontend/dependencies", "dependencies"
            return posixpath.dirname(key.split(" (", 1)[0])

        primary = {eco: {k: v for k, v in groups.items() if not path_classifier.is_secondary_dir(manifest_dir(k))}
                   for eco, groups in dependencies.items()}
        return primary if any(primary.values()) else dependencies

    def _primary_files(self) -> List[str]:
        return path_classifier.primary_paths(self.files)

    def _primary_imports(self) -> List[str]:
        primary = self._primary_files()
        return [imp for p in primary for imp in self.files[p].get("imports", [])]

    # Manifests that mark a sub-project root (Makefiles / CMakeLists.txt sit in every sub-directory)
    _PROJECT_ROOT_MANIFESTS = ("npm", "pyproject", "setuppy", "pipfile", "requirements", "maven", "gradle",
                               "cargo", "gomod", "django")

    def _project_roots(self) -> List[str]:
        """Directories holding a project manifest: the sub-projects of a monorepo."""
        manifests = self._manifests()
        return sorted({posixpath.dirname(p) for kind in self._PROJECT_ROOT_MANIFESTS
                       for p in manifests.get(kind, [])} - {""})

    def _architecture(self, frameworks: Dict, databases: List[str], file_dependencies: Dict,
                      entry_points: List[str]) -> Dict[str, Any]:
        from app.services.architecture_service import ArchitectureAnalyzer
        return ArchitectureAnalyzer({
            'files': self.files,
            'frameworks': frameworks,
            'databases': databases,
            'file_dependencies': file_dependencies,
            'entry_points': entry_points,
            'project_roots': self._project_roots(),
            'framework_families': {k: sorted(v) for k, v in self.framework_families().items()},
        }).generate()

    # Frameworks detected outside _FRAMEWORK_RULES, and the language family they are written in
    _FRAMEWORK_FAMILIES_EXTRA = {
        "Next.js": "javascript", "React": "javascript", "Vue.js": "javascript", "Nuxt.js": "javascript",
        "Angular": "javascript", "Svelte": "javascript", "SvelteKit": "javascript", "Vite": "javascript",
        "Tailwind CSS": "javascript", "Express.js": "javascript", "NestJS": "javascript", "Koa": "javascript",
        "Hapi": "javascript", "FastAPI": "python", "Flask": "python", "Django": "python",
        "Spring Boot": "jvm", "Spring": "jvm", "Android": "jvm", "Gin (Go)": "go", "Fiber (Go)": "go",
        "Echo (Go)": "go", "Ruby on Rails": "ruby", "Laravel": "php", "Unreal Engine": "cpp",
    }
    _ECOSYSTEM_FAMILY = {"python": "python", "javascript": "javascript", "java": "jvm", "rust": "rust", "cpp": "cpp"}

    @classmethod
    def framework_families(cls) -> Dict[str, Set[str]]:
        """Framework name -> language families it belongs to (gRPC exists in several)."""
        out: Dict[str, Set[str]] = {}
        for eco, sides in cls._FRAMEWORK_RULES.items():
            for rules in sides.values():
                for fw in rules.values():
                    out.setdefault(fw, set()).add(cls._ECOSYSTEM_FAMILY[eco])
        for fw, fam in cls._FRAMEWORK_FAMILIES_EXTRA.items():
            out.setdefault(fw, set()).add(fam)
        return out

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

        # Check for config files in the repo (not in tests / examples / docs)
        config_files = set()
        for _, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if self._keep_dir(d) and not path_classifier.is_secondary_dir(d)]
            for f in files:
                config_files.add(f.lower())
        primary_imports = self._primary_imports()

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
        if any('springframework' in imp for imp in primary_imports):
            backend.append('Spring Boot')
        elif 'pom.xml' in config_files or 'build.gradle' in config_files:
            # Check if pom.xml or build.gradle contains spring
            for cfg in ['pom.xml', 'build.gradle']:
                content = (self._read(cfg) or '').lower()
                if 'spring-boot' in content or 'springframework' in content:
                    backend.append('Spring Boot')
                    break

        # Go frameworks - only detect if we actually have Go files
        has_go_files = any(p.endswith('.go') for p in self._primary_files())
        if has_go_files:
            go_imports = [imp for imp in primary_imports if 'github.com' in imp or imp.startswith('go/')]
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
        return exts is None or any(p.endswith(exts) for p in self._primary_files())

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
                    and path_classifier.is_primary(path):
                weak.append(path)
        strong.extend(self._manifest_entry_points())

        strong_set = set(strong)
        candidates = strong_set | set(weak)
        result = sorted(candidates, key=lambda p: (path_classifier.is_secondary(p), p not in strong_set, p))
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
        primary = set(path_classifier.primary_paths(self.files))
        for path, meta in self.files.items():
            # Skip tests, examples, docs and generated files (generated API clients, *.min.js, ...)
            if path not in primary:
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

        Node ids are `file::Class.method` (or `file::function`) so that methods of different
        classes that share a name stay apart. Calls only resolve within one language family.
        """
        call_graph: Dict[str, Dict[str, Any]] = {}
        self.found_api_calls = []
        self.found_routes = []
        self.found_db_queries = []

        # Phase 1: Build registry of all known functions
        func_registry: Dict[str, List[str]] = {}          # bare name -> node ids (all languages)
        self._fam_registry: Dict[tuple, List[str]] = {}   # (language family, bare name) -> node ids
        # node id -> (parent container, owning class): parent is the enclosing class / impl /
        # function; owning class is set only for methods (for `self.x()` and qualified calls).
        symbol_info: Dict[str, tuple] = {}

        for file_path, meta in self.files.items():
            language = meta.get('language', 'Unknown')
            category = path_classifier.classify_path(file_path)
            family = path_classifier.language_family(file_path)
            if "symbols" in meta:
                entries = [(s["name"], self._qualname(s), s.get("parent"), s["kind"] == "method")
                           for s in meta["symbols"] if s["kind"] in source_parser.FUNCTION_KINDS]
            else:
                entries = [(n, n, None, False) for n in meta.get('functions', [])]
            for func_name, qual, parent, is_method in entries:
                qualified_id = f"{file_path}::{qual}"
                if qualified_id in call_graph:
                    continue  # e.g. a property getter and its setter
                call_graph[qualified_id] = {
                    "name": qual,
                    "file": file_path,
                    "calls": [],
                    "called_by": [],
                    "language": language,
                    "type": "function",
                    "category": category,
                }
                func_registry.setdefault(func_name, []).append(qualified_id)
                self._fam_registry.setdefault((family, func_name), []).append(qualified_id)
                symbol_info[qualified_id] = (parent, parent if is_method else None)

        # Phase 2: Extract backend routes
        self._extract_all_routes(frameworks)

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
                                           expanded_deps, symbol_info)
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
        for qualified_id, info in call_graph.items():
            for callee_id in info.get('calls', []):
                if callee_id in call_graph:
                    if qualified_id not in call_graph[callee_id]['called_by']:
                        call_graph[callee_id]['called_by'].append(qualified_id)

        return call_graph

    @staticmethod
    def _qualname(sym: Dict) -> str:
        """`Class.method` for members, `outer.inner` for nested functions, else the bare name
        (the same naming the chunker uses for chunk symbols)."""
        return f"{sym['parent']}.{sym['name']}" if sym.get("parent") else sym["name"]

    def _candidates(self, name: str, current_file: str, func_registry: Dict) -> List[str]:
        """Registered functions named `name` written in the same language family as `current_file`."""
        fam_registry = getattr(self, "_fam_registry", None)
        family = path_classifier.language_family(current_file)
        if fam_registry is not None:
            return fam_registry.get((family, name), [])
        return [c for c in func_registry.get(name, [])
                if path_classifier.language_family(c.split('::', 1)[0]) == family]

    @staticmethod
    def _prefer_primary(current_file: str, candidates: List[str]) -> List[str]:
        """For a call from the product's own code, drop test / example / generated candidates
        when a primary one exists (unresolved-name fallback only)."""
        if not path_classifier.is_primary(current_file):
            return candidates
        primary = [c for c in candidates if path_classifier.is_primary(c.split('::', 1)[0])]
        return primary or candidates

    MAX_AMBIGUOUS_TARGETS = 3

    @classmethod
    def _unambiguous(cls, targets: List[str]) -> List[str]:
        """`obj.save()` with ten classes defining `save` in reach says nothing about which one runs:
        link a few plausible targets, not all of them."""
        return targets if len(targets) <= cls.MAX_AMBIGUOUS_TARGETS else []

    _JS_EXTS = {'.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.mts', '.cts'}
    _SELF_QUALIFIERS = {"self", "this", "Self", "super", "cls"}
    # Languages where a bare `name()` can never call a method (only a function or a constructor)
    _BARE_CALLS_SKIP_METHODS = {"python", "javascript", "rust"}

    def _extract_symbol_calls(self, file_path: str, meta: Dict, content: str, call_graph: Dict,
                              func_registry: Dict, file_dependencies: Dict,
                              symbol_info: Dict[str, tuple]) -> None:
        """Call edges from parsed call sites (tree-sitter), plus API/DB cross-boundary hints."""
        resolved_deps = set(file_dependencies.get(file_path, {}).get('resolved', []))
        ext = meta.get('extension', '')
        is_js, is_py = ext in self._JS_EXTS, ext in ('.py', '.pyi')
        lines = content.splitlines() if (content and (is_js or is_py)) else []
        db_capable = self._db_capable(file_path, meta) if lines else False

        for sym in meta.get("symbols", []):
            if sym["kind"] not in source_parser.FUNCTION_KINDS:
                continue
            caller_id = f"{file_path}::{self._qualname(sym)}"
            if caller_id not in call_graph:
                continue
            caller_class = sym.get("parent") if sym["kind"] == "method" else None
            calls = call_graph[caller_id]['calls']
            for name, qualifier, is_member in sym.get("calls", []):
                if name not in func_registry:
                    continue
                for target_id in self._resolve_symbol_call(name, qualifier, is_member, file_path, caller_class,
                                                           func_registry, resolved_deps, symbol_info):
                    if target_id != caller_id and target_id not in calls:
                        calls.append(target_id)

            if lines:
                body = "\n".join(lines[sym["start_line"] - 1: sym["end_line"]])
                if is_js:
                    for api in self._api_calls(body):
                        self.found_api_calls.append({'caller': caller_id, 'file': file_path, **api})
                for op in self._db_ops(body, 'javascript' if is_js else 'python', db_capable):
                    self.found_db_queries.append({'caller': caller_id, 'file': file_path, 'op': op})

    def _resolve_symbol_call(self, name: str, qualifier: Optional[str], is_member: bool, current_file: str,
                             caller_class: Optional[str], func_registry: Dict, resolved_deps: Set[str],
                             symbol_info: Dict[str, tuple]) -> List[str]:
        """
        Resolve a call to registered functions of the caller's language family:
          self.x() / this.x()   -> a method of the caller's own class, else same file, else imported
          Type::x() / Type.x()  -> functions whose parent is Type (impl/class), else module `Type`
          plain / obj.x()       -> same file, then imported files, then unambiguous global matches
        """
        candidates = self._candidates(name, current_file, func_registry)
        if not candidates:
            return []
        file_of = lambda c: c.split('::', 1)[0]
        parent_of = lambda c: symbol_info.get(c, (None, None))[0]
        class_of = lambda c: symbol_info.get(c, (None, None))[1]
        same_file = [c for c in candidates if file_of(c) == current_file]
        imported = [c for c in candidates if file_of(c) in resolved_deps]

        if qualifier in self._SELF_QUALIFIERS:
            if caller_class:
                own = [c for c in same_file if class_of(c) == caller_class]
                if own:
                    return own
                # Inherited: a method of another class in this file, else of an imported one
                for tier in ([c for c in same_file if class_of(c)], [c for c in imported if class_of(c)]):
                    if tier:
                        return self._unambiguous(tier)
            return self._unambiguous(same_file or imported)
        if qualifier:
            by_parent = [c for c in candidates if parent_of(c) == qualifier]
            if by_parent:
                preferred = [c for c in by_parent if c in same_file or c in imported]
                return preferred or by_parent[:3]
            # module / package qualifier: utils.fmt(), click.echo() (package dir), routes::serve()
            by_module = [c for c in candidates
                         if Path(file_of(c)).stem == qualifier or Path(file_of(c)).parent.name == qualifier]
            if by_module:
                preferred = [c for c in by_module if c in imported]
                return preferred or by_module[:3]
        elif not is_member:
            family = path_classifier.language_family(current_file)
            if family in self._BARE_CALLS_SKIP_METHODS:
                # `open_session()` is never `SomeClass.open_session` (constructors aside)
                bare_ok = lambda c: class_of(c) is None or class_of(c) == name
                candidates = [c for c in candidates if bare_ok(c)]
                same_file = [c for c in same_file if bare_ok(c)]
                imported = [c for c in imported if bare_ok(c)]
            elif caller_class:
                # Java / C++: an unqualified call inside a class targets that class first
                own = [c for c in same_file if class_of(c) == caller_class]
                if own:
                    return own
        if same_file:
            return self._unambiguous(same_file) if is_member else same_file
        if imported:
            return self._unambiguous(imported) if is_member else imported
        # Unknown receiver / not imported: only link when unambiguous
        candidates = self._prefer_primary(current_file, candidates)
        if is_member:
            return candidates if len(candidates) == 1 else []
        return candidates if len(candidates) <= 3 else []

    # ---- Database operations ------------------------------------------------
    # A DB node is only drawn for calls on a known database client / ORM, never for any
    # `.get(` / `.update(` / `.filter(` (dict.update, hmac.update, list filtering, ...).
    _DB_OP_KIND = {
        **{m: "SELECT" for m in (
            "find", "findone", "find_one", "findmany", "findunique", "finduniqueorthrow", "findfirst",
            "findfirstorthrow", "findbyid", "findall", "findbypk", "findandcountall", "findby", "findoneby",
            "get", "scalars", "scalar", "select", "fetch", "fetchone", "fetchall", "fetchmany", "fetchrow",
            "fetchval", "count", "count_documents", "countdocuments", "aggregate", "groupby", "all", "filter",
            "exclude", "first", "last", "values", "values_list", "exists", "in_bulk", "order_by",
            "select_related", "prefetch_related", "annotate", "where")},
        **{m: "INSERT" for m in (
            "add", "add_all", "bulk_save_objects", "insert", "insert_one", "insertone", "insert_many",
            "insertmany", "create", "createmany", "bulkcreate", "bulk_create", "save", "get_or_create",
            "findorcreate")},
        **{m: "UPDATE" for m in (
            "update", "update_one", "updateone", "update_many", "updatemany", "upsert", "merge",
            "replace_one", "replaceone", "find_one_and_update", "findoneandupdate", "findbyidandupdate",
            "update_or_create", "bulk_update", "bulkwrite")},
        **{m: "DELETE" for m in (
            "delete", "remove", "destroy", "delete_one", "deleteone", "delete_many", "deletemany",
            "find_one_and_delete", "findoneanddelete", "findbyidanddelete")},
    }
    # session.exec(...), cursor.execute(...), db.query(...), self.session.add(...), knex.select(...)
    _DB_RECEIVER_RE = re.compile(
        r"(?:(?<![\w.])|(?<=self\.)|(?<=this\.)|(?<=cls\.)|(?<=\bdb\.))"
        r"(?:session|db_session|dbsession|db|database|cursor|cur|conn|connection|engine|tx|trx|pool|em|"
        r"entityManager|knex)\.(execute|executemany|exec|query|scalars|scalar|add|add_all|bulk_save_objects|"
        r"delete|merge|get(?=\s*\(\s*[A-Z][a-z])|update(?<=\bdb\.update)|find|findOne|insert|upsert|select|save|"
        r"remove|fetch|fetchone|fetchall|"
        r"fetchmany|fetchrow|fetchval|raw)\s*\(")
    # Driver / ODM methods whose names only exist on database clients (pymongo, mongoose, sequelize)
    _DB_METHOD_RE = re.compile(
        r"\.(insert_one|insert_many|update_one|update_many|delete_one|delete_many|replace_one|find_one|"
        r"find_one_and_update|find_one_and_delete|count_documents|insertOne|insertMany|updateOne|updateMany|"
        r"deleteOne|deleteMany|replaceOne|countDocuments|findOneAndUpdate|findOneAndDelete|findByIdAndUpdate|"
        r"findByIdAndDelete|bulkWrite|findById|findByPk|findAndCountAll|bulkCreate|bulk_create)\s*\(")
    # Django ORM: Model.objects.filter(...)
    _DJANGO_ORM_RE = re.compile(
        r"\.objects\.(?:using\([^)]*\)\.)?(all|filter|get|create|update|delete|exclude|get_or_create|"
        r"update_or_create|bulk_create|bulk_update|count|aggregate|values|values_list|first|last|order_by|"
        r"select_related|prefetch_related|annotate|exists|in_bulk|raw)\s*\(")
    # Prisma: prisma.user.findMany(...), prisma.$queryRaw`...`
    _PRISMA_RE = re.compile(
        r"\bprisma\.(?:\w+\.(findMany|findUnique|findUniqueOrThrow|findFirst|findFirstOrThrow|create|createMany|"
        r"update|updateMany|upsert|delete|deleteMany|count|aggregate|groupBy)\s*\(|\$(queryRaw|executeRaw|"
        r"queryRawUnsafe|executeRawUnsafe))")
    # Mongoose / Sequelize / TypeORM model statics: User.findOne(...), Post.create(...)
    _MODEL_STATIC_RE = re.compile(
        r"(?<![\w.$])([A-Z]\w*)\.(find|findOne|create|update|destroy|count|aggregate|exists|upsert|where)\s*\(")
    _NON_MODEL_GLOBALS = {"Object", "Array", "Promise", "Math", "JSON", "Date", "Number", "String", "Reflect",
                          "Map", "Set", "WeakMap", "Symbol", "Intl", "Buffer", "React", "Proxy", "URL", "Error"}
    # SQL in a string literal (upper-case keywords, so UI text such as "Select a file from..." is ignored)
    _SQL_LITERAL_RE = re.compile(
        r"['\"`]\s*(?:(SELECT)\s[^'\"`]*?\bFROM\s|(INSERT)\s+INTO\s|(UPDATE)\s+[\w.\"`]+\s+SET\s|(DELETE)\s+FROM\s)")

    _PY_DB_MODULE_RE = re.compile(
        r"^(sqlalchemy|sqlmodel|sqlite3|psycopg|psycopg2|psycopg_pool|asyncpg|aiosqlite|aiomysql|pymongo|motor|"
        r"pymysql|MySQLdb|mysql\.connector|django\.db|peewee|pony|tortoise|mongoengine|beanie|odmantic|databases|"
        r"flask_sqlalchemy|piccolo|duckdb|cassandra|neo4j)(\.|$)")
    _JS_DB_MODULE_RE = re.compile(
        r"^(mongoose|mongodb|@prisma/client|prisma|sequelize|sequelize-typescript|typeorm|knex|pg|pg-promise|"
        r"postgres|mysql|mysql2|mysql2/promise|better-sqlite3|sqlite|sqlite3|drizzle-orm|kysely|objection|"
        r"@mikro-orm/[\w-]+|@supabase/supabase-js|@neondatabase/serverless|@planetscale/database)(/|$)")
    _PY_DB_DEPS = {"sqlalchemy", "sqlmodel", "flask-sqlalchemy", "django", "psycopg2", "psycopg2-binary", "psycopg",
                   "asyncpg", "aiosqlite", "aiomysql", "pymongo", "motor", "pymysql", "mysqlclient",
                   "mysql-connector-python", "peewee", "pony", "tortoise-orm", "mongoengine", "beanie", "odmantic",
                   "databases", "piccolo", "duckdb"}
    _JS_DB_DEPS = {"mongoose", "mongodb", "@prisma/client", "prisma", "sequelize", "sequelize-typescript", "typeorm",
                   "knex", "pg", "pg-promise", "postgres", "mysql", "mysql2", "better-sqlite3", "sqlite", "sqlite3",
                   "drizzle-orm", "kysely", "objection", "@supabase/supabase-js"}
    _JS_MODEL_ORMS = {"mongoose", "sequelize", "sequelize-typescript", "typeorm", "objection"}

    def _db_capable(self, file_path: str, meta: Dict) -> bool:
        """Whether a file talks to a database at all: it imports a database driver / ORM, or its
        ecosystem depends on one. Generic receiver patterns are only trusted in such files."""
        family = path_classifier.language_family(file_path)
        imports = meta.get("imports", [])
        dep_sets = getattr(self, "dep_sets", {}) or {}
        if family == "python":
            return bool(dep_sets.get("python", set()) & self._PY_DB_DEPS) \
                or any(self._PY_DB_MODULE_RE.match(i.lstrip(".")) for i in imports)
        if family == "javascript":
            return bool(dep_sets.get("javascript", set()) & self._JS_DB_DEPS) \
                or any(self._JS_DB_MODULE_RE.match(i) for i in imports)
        return False

    def _db_ops(self, body: str, family: str, capable: bool) -> List[str]:
        """Database operations (SELECT / INSERT / UPDATE / DELETE / QUERY) made in a function body."""
        ops: List[str] = []

        def add(method: Optional[str], default: str = "QUERY"):
            op = self._DB_OP_KIND.get((method or "").lower(), default)
            if op not in ops:
                ops.append(op)

        for m in self._SQL_LITERAL_RE.finditer(body):
            add(None, next(g for g in m.groups() if g))
        if family == "python":
            for m in self._DJANGO_ORM_RE.finditer(body):
                add(m.group(1))
        if family == "javascript":
            for m in self._PRISMA_RE.finditer(body):
                add(m.group(1))
            if (getattr(self, "dep_sets", None) or {}).get("javascript", set()) & self._JS_MODEL_ORMS:
                for m in self._MODEL_STATIC_RE.finditer(body):
                    if m.group(1) not in self._NON_MODEL_GLOBALS:
                        add(m.group(2))
        if capable:
            for m in self._DB_RECEIVER_RE.finditer(body):
                add(m.group(1))
            for m in self._DB_METHOD_RE.finditer(body):
                add(m.group(1))
        return ops

    # ---- Frontend -> backend HTTP calls --------------------------------------
    # Generated API clients (openapi-ts, orval, ...) pass request options: { method: "GET", url: "/api/v1/items/" }
    # or call a verb method with them: client.post<Res, Err>({ url: "/api/v1/login/access-token" })
    _URL_LITERAL_RE = re.compile(r"\burl\s*:\s*(['\"`])(/[^'\"`\s]*)\1")
    _METHOD_LITERAL_RE = re.compile(r"\bmethod\s*:\s*['\"`](\w+)['\"`]", re.I)
    _VERB_CALL_RE = re.compile(r"\.(get|post|put|patch|delete)\b[^(;\n]*\(\s*\{", re.I)

    def _api_calls(self, body: str) -> List[Dict[str, str]]:
        found: List[Dict[str, str]] = []
        for api_match in self.API_CALL_REGEX.finditer(body):
            path = api_match.group(1) or api_match.group(4)
            method = api_match.group(2) or api_match.group(3) or 'get'
            if path:
                found.append({'path': path, 'method': method.lower()})
        for m in self._URL_LITERAL_RE.finditer(body):
            window_start = max(0, m.start() - 300)
            window = body[window_start: m.end() + 300]
            methods = [(abs(mm.start() + window_start - m.start()), mm.group(1))
                       for mm in self._METHOD_LITERAL_RE.finditer(window)]
            methods += [(m.start() - mm.start(), mm.group(1))
                        for mm in self._VERB_CALL_RE.finditer(body, window_start, m.start())]
            method = min(methods)[1] if methods else 'get'
            entry = {'path': m.group(2), 'method': method.lower()}
            if entry not in found:
                found.append(entry)
        return found

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
        db_capable = self._db_capable(file_path, self.files.get(file_path, {}))

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
                body = ast.get_source_segment(content, node) or ""
                for op in self._db_ops(body, "python", db_capable):
                    self.found_db_queries.append({'caller': caller_id, 'file': file_path, 'op': op})

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
        db_capable = self._db_capable(file_path, self.files.get(file_path, {}))

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
            for api in self._api_calls(body):
                self.found_api_calls.append({'caller': caller_id, 'file': file_path, **api})
            for op in self._db_ops(body, "javascript", db_capable):
                self.found_db_queries.append({'caller': caller_id, 'file': file_path, 'op': op})

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
        """Resolve a function name to qualified IDs of the same language family,
        preferring a same-file match, then imported files, then a few global matches."""
        candidates = self._candidates(func_name, current_file, func_registry)
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
        return self._prefer_primary(current_file, candidates)[:3]

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
            # Router-level prefix declared in the file itself:
            # router = APIRouter(prefix="/items"), Blueprint("x", __name__, url_prefix="/x")
            own = self._ROUTER_PREFIX_RE.search(content)
            router_prefix = own.group(1) if own else ""
            
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
                        # Combine base_prefix, the router's own prefix and path
                        own_path = (router_prefix.rstrip('/') + '/' + path.lstrip('/')).strip('/')
                        full_path = (base_prefix.rstrip('/') + '/' + own_path).strip('/')
                        if not full_path: full_path = "/"

                        # Also keep a version without the base_prefix just in case the prefix detection was wrong
                        self.found_routes.append({
                            'file': file_path,
                            'path': full_path,
                            'original_path': own_path,
                            'method': method,
                            'handler': handler,
                            'middlewares': middlewares
                        })

    _ROUTER_PREFIX_RE = re.compile(
        r"\b(?:APIRouter|Blueprint|Router)\s*\([^)]*?\b(?:url_)?prefix\s*=\s*['\"]([^'\"]+)['\"]")

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
                    "type": "api-call",
                    "category": path_classifier.classify_path(api.get('file', '')),
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
                    mw_candidates = self._candidates(mw_name, matched_route['file'], func_registry)
                    # Prefer middleware in the same file as the route
                    mw_id = next((c for c in mw_candidates if c.startswith(f"{matched_route['file']}::")), None)
                    if not mw_id and mw_candidates: mw_id = mw_candidates[0]
                    
                    if mw_id:
                        if mw_id not in call_graph[prev_id]['calls']:
                            call_graph[prev_id]['calls'].append(mw_id)
                        call_graph[mw_id]['type'] = 'middleware'
                        prev_id = mw_id
                
                # Final Handler: `handler`, `Class.method` or `module.handler`, defined in the route file
                handler_name = matched_route['handler']
                route_handler_id = f"{matched_route['file']}::{handler_name}"
                if route_handler_id not in call_graph:
                    in_file = [c for c in self._candidates(handler_name.split('.')[-1], matched_route['file'],
                                                           func_registry)
                               if c.startswith(f"{matched_route['file']}::")]
                    route_handler_id = in_file[0] if in_file else None

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
                            "type": "route",
                            "category": path_classifier.classify_path(matched_route['file']),
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
                    "type": "db-query",
                    "category": path_classifier.PRIMARY,
                }
            
            caller_id = db['caller']
            if caller_id in call_graph:
                if db_node_id not in call_graph[caller_id]['calls']:
                    call_graph[caller_id]['calls'].append(db_node_id)
                if call_graph[caller_id]['type'] == 'function':
                    call_graph[caller_id]['type'] = 'service'

    @staticmethod
    def _path_segments(path: str) -> List[str]:
        """URL path -> lower-case segments, with parameters (`{id}`, `:id`, `<int:id>`, `${id}`)
        as '*'. Leading parameters (a `${API_URL}` base) are dropped."""
        path = re.sub(r'^https?://[^/]+', '', path or '')
        path = path.split('?')[0].split('#')[0]
        segs = []
        for seg in path.strip('/').split('/'):
            if not seg:
                continue
            if seg.startswith(('{', ':', '<', '$')) or '${' in seg:
                segs.append('*')
            else:
                segs.append(seg.lower())
        while segs and segs[0] == '*':
            segs.pop(0)
        return segs

    def _match_route(self, api_path: str, api_method: str) -> Optional[Dict]:
        """Match an API path to a backend route definition. The route path must equal the call's
        path or a suffix of it (the call may carry a base URL / prefix the route does not show);
        parameters match any segment. Exact and more literal matches win."""
        api = self._path_segments(api_path)
        best, best_score = None, None
        for route in self.found_routes:
            if route['method'].lower() != api_method.lower() and route['method'].lower() != 'any':
                continue
            for rp in (route['path'], route.get('original_path', '')):
                segs = self._path_segments(rp)
                if not segs:
                    ok = not api or api == ['api']
                    score = (len(api) == 0, 0, 0)
                elif len(segs) > len(api):
                    continue
                else:
                    tail = api[len(api) - len(segs):]
                    if any(r != a and r != '*' and a != '*' for r, a in zip(segs, tail)):
                        continue
                    ok = True
                    literal = sum(1 for r, a in zip(segs, tail) if r == a and r != '*')
                    if not literal and len(segs) != len(api):
                        continue  # "/{id}" alone says nothing about "/api/v1/users/5"
                    # A parameter in the call matches a parameter in the route better than a
                    # literal: "users/{user_id}" is not "users/me"
                    exact = sum(1 for r, a in zip(segs, tail) if r == a)
                    score = (len(segs) == len(api), len(segs), exact)
                if ok and (best_score is None or score > best_score):
                    best, best_score = route, score
        return best
