import os
import ast
import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Set


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
        ".idea", ".vscode", "bower_components"
    }

    # Extension to language name mapping
    LANGUAGE_NAMES = {
        ".py": "Python",
        ".js": "JavaScript",
        ".jsx": "JavaScript (React)",
        ".ts": "TypeScript",
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
        ".h": "C/C++ Header",
        ".hpp": "C++ Header",
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

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.files: Dict[str, Dict] = {}
        self.all_imports: List[str] = []
        self.all_npm_deps: Set[str] = set()
        self.all_python_deps: Set[str] = set()
        # Temporary storage for full file contents (used for call graph, cleared after)
        self._file_contents: Dict[str, str] = {}

    def analyze(self) -> Dict[str, Any]:
        """Main analysis entry point."""
        # Collect and analyze source files
        for file_path in self._get_source_files():
            meta = self._analyze_file(file_path)
            if meta:
                rel = str(file_path.relative_to(self.repo_path))
                self.files[rel] = meta
                self.all_imports.extend(meta.get('imports', []))

        # Extract all dependencies first (needed for framework detection)
        dependencies = self._extract_dependencies()

        # Collect all npm and python deps for framework/db detection
        for deps in dependencies.get('javascript', {}).values():
            self.all_npm_deps.update(deps)
        for deps in dependencies.get('python', {}).values():
            self.all_python_deps.update(d.lower() for d in deps)

        # Detect frameworks and databases using collected deps
        frameworks = self._detect_frameworks()
        databases = self._detect_databases()

        # Build file dependency graph
        file_dependencies = self._build_file_dependencies()

        # Build call graph (function-to-function relationships)
        call_graph = self._build_call_graph(file_dependencies)

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
        }

    def _get_source_files(self) -> List[Path]:
        """Get all source files, excluding ignored directories and files."""
        result = []
        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]

            for name in files:
                if name.lower() in self.IGNORE_FILES:
                    continue
                ext = Path(name).suffix.lower()
                if ext in self.SOURCE_EXTENSIONS:
                    result.append(Path(root) / name)

        return result

    # Maximum content size to store (in characters) - ~2000 tokens worth
    MAX_CONTENT_SIZE = 8000

    def _analyze_file(self, path: Path) -> Optional[Dict]:
        """Analyze a single source file."""
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            ext = path.suffix.lower()

            # Store full content for call graph extraction (will be cleared after analysis)
            rel = str(path.relative_to(self.repo_path))
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

            if ext == ".py":
                meta.update(self._analyze_python(content))
            elif ext in {".js", ".jsx", ".ts", ".tsx"}:
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
        """Analyze JavaScript/TypeScript file with comprehensive import detection."""
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

        return {
            "imports": list(imports),
            "functions": re.findall(r"(?:function|const|let|var)\s+(\w+)\s*(?:=\s*(?:async\s*)?\(|=\s*function|\()", content),
            "classes": re.findall(r"class\s+(\w+)", content),
            "has_main": "createRoot" in content or "ReactDOM.render" in content or "createApp" in content
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

    def _extract_dependencies(self) -> Dict[str, Dict[str, List[str]]]:
        """Extract dependencies from ALL config files in the repo."""
        dependencies = {
            "python": {},
            "javascript": {},
            "other": {}
        }

        # Find all package.json files (for monorepos)
        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            rel_root = Path(root).relative_to(self.repo_path)

            for filename in files:
                file_path = Path(root) / filename

                # JavaScript - package.json
                if filename == 'package.json':
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            pkg = json.load(f)
                            prefix = str(rel_root) if str(rel_root) != '.' else ''

                            if pkg.get('dependencies'):
                                key = f"{prefix}/dependencies" if prefix else "dependencies"
                                dependencies["javascript"][key] = list(pkg['dependencies'].keys())
                            if pkg.get('devDependencies'):
                                key = f"{prefix}/devDependencies" if prefix else "devDependencies"
                                dependencies["javascript"][key] = list(pkg['devDependencies'].keys())
                    except:
                        pass

                # Python - requirements.txt
                if filename.lower() in ['requirements.txt', 'requirements-dev.txt', 'requirements.dev.txt']:
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            deps = []
                            for line in f:
                                line = line.strip()
                                if line and not line.startswith('#') and not line.startswith('-'):
                                    pkg = re.split(r'[=<>!~\[]', line)[0].strip()
                                    if pkg:
                                        deps.append(pkg)
                            if deps:
                                prefix = str(rel_root) if str(rel_root) != '.' else ''
                                key = f"{prefix}/{filename}" if prefix else filename
                                dependencies["python"][key] = deps
                    except:
                        pass

                # Python - pyproject.toml
                if filename == 'pyproject.toml':
                    try:
                        content = file_path.read_text()
                        # Look for dependencies in [project.dependencies] or [tool.poetry.dependencies]
                        deps = []
                        in_deps_section = False
                        for line in content.split('\n'):
                            if '[project.dependencies]' in line or '[tool.poetry.dependencies]' in line:
                                in_deps_section = True
                                continue
                            if in_deps_section:
                                if line.startswith('['):
                                    break
                                match = re.match(r'^([a-zA-Z0-9_-]+)\s*=', line.strip())
                                if match:
                                    deps.append(match.group(1))
                        if deps:
                            prefix = str(rel_root) if str(rel_root) != '.' else ''
                            key = f"{prefix}/pyproject.toml" if prefix else "pyproject.toml"
                            dependencies["python"][key] = deps
                    except:
                        pass

        # Go - go.mod (root only)
        go_mod_path = self.repo_path / "go.mod"
        if go_mod_path.exists():
            try:
                content = go_mod_path.read_text()
                deps = re.findall(r'^\s*([\w./-]+)\s+v', content, re.MULTILINE)
                if deps:
                    dependencies["other"]["go.mod"] = deps
            except:
                pass

        # Rust - Cargo.toml (root only)
        cargo_path = self.repo_path / "Cargo.toml"
        if cargo_path.exists():
            try:
                content = cargo_path.read_text()
                deps = re.findall(r'^\s*([a-zA-Z0-9_-]+)\s*=', content, re.MULTILINE)
                if deps:
                    dependencies["other"]["Cargo.toml"] = [d for d in deps if d not in ['name', 'version', 'edition', 'authors']]
            except:
                pass

        return dependencies

    def _detect_frameworks(self) -> Dict[str, List[str]]:
        """Detect frontend and backend frameworks."""
        frontend = []
        backend = []

        npm_deps = self.all_npm_deps
        python_deps = self.all_python_deps

        # Check for config files in entire repo
        config_files = set()
        for _, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
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
                cfg_path = self.repo_path / cfg
                if cfg_path.exists():
                    try:
                        content = cfg_path.read_text().lower()
                        if 'spring-boot' in content or 'springframework' in content:
                            backend.append('Spring Boot')
                            break
                    except:
                        pass

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
            gemfile_path = self.repo_path / "Gemfile"
            if gemfile_path.exists():
                try:
                    content = gemfile_path.read_text().lower()
                    if 'rails' in content:
                        backend.append('Ruby on Rails')
                except:
                    pass

        # PHP - Laravel
        if 'artisan' in config_files or 'composer.json' in config_files:
            composer_path = self.repo_path / "composer.json"
            if composer_path.exists():
                try:
                    content = composer_path.read_text().lower()
                    if 'laravel' in content:
                        backend.append('Laravel')
                except:
                    pass

        return {
            "frontend": list(set(frontend)),
            "backend": list(set(backend))
        }

    def _detect_databases(self) -> List[str]:
        """Detect database usage from dependencies and config files."""
        databases = set()

        npm_deps = self.all_npm_deps
        python_deps = self.all_python_deps

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

        # Check Prisma schema for database type
        prisma_schema = self.repo_path / "prisma" / "schema.prisma"
        if prisma_schema.exists():
            try:
                content = prisma_schema.read_text().lower()
                if 'postgresql' in content or 'postgres' in content:
                    databases.add('PostgreSQL')
                elif 'mysql' in content:
                    databases.add('MySQL')
                elif 'mongodb' in content:
                    databases.add('MongoDB')
                elif 'sqlite' in content:
                    databases.add('SQLite')
            except:
                pass

        # Check docker-compose for database services
        for compose_file in ['docker-compose.yml', 'docker-compose.yaml', 'compose.yml', 'compose.yaml']:
            compose_path = self.repo_path / compose_file
            if compose_path.exists():
                try:
                    content = compose_path.read_text().lower()
                    if 'postgres' in content:
                        databases.add('PostgreSQL')
                    if 'mysql' in content or 'mariadb' in content:
                        databases.add('MySQL')
                    if 'mongo' in content:
                        databases.add('MongoDB')
                    if 'redis' in content:
                        databases.add('Redis')
                except:
                    pass

        # Check .env files for database URLs
        for env_file in ['.env', '.env.example', '.env.local', '.env.development']:
            env_path = self.repo_path / env_file
            if env_path.exists():
                try:
                    content = env_path.read_text().lower()
                    if 'mongodb' in content or 'mongo_uri' in content:
                        databases.add('MongoDB')
                    if 'postgres' in content or 'postgresql' in content:
                        databases.add('PostgreSQL')
                    if 'mysql' in content:
                        databases.add('MySQL')
                    if 'redis' in content:
                        databases.add('Redis')
                except:
                    pass

        return list(databases)

    def _entry_points(self) -> List[str]:
        """Detect application entry points."""
        result = []
        for path, meta in self.files.items():
            basename = Path(path).stem.lower()

            if basename in self.ENTRY_BASENAMES:
                result.append(path)
                continue

            if meta.get("has_main"):
                result.append(path)

        return sorted(set(result))

    def _key_files(self) -> List[str]:
        """Identify key/important files."""
        entry_points = []
        important_files = []

        for path, meta in self.files.items():
            basename = Path(path).stem.lower()
            path_lower = path.lower()

            # Skip test files
            if any(x in path_lower for x in ['test_', '_test', 'tests/', '/test/', '.test.', '.spec.']):
                continue

            # Priority 1: Entry point files
            if basename in self.ENTRY_BASENAMES or meta.get("has_main"):
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

        # Create a map of possible module names to file paths
        file_map = self._build_file_map()

        for file_path, meta in self.files.items():
            imports = meta.get('imports', [])
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
            readme_path = self.repo_path / pattern
            if readme_path.exists():
                try:
                    content = readme_path.read_text(encoding='utf-8', errors='ignore')
                    return {
                        'file': pattern,
                        'content': content[:5000],
                        'full_length': len(content)
                    }
                except:
                    continue

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
        pkg_json_path = self.repo_path / 'package.json'
        if pkg_json_path.exists():
            try:
                with open(pkg_json_path, 'r', encoding='utf-8') as f:
                    pkg = json.load(f)
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
        if pkg_json_path.exists():
            return 'npm'

        return None

    def _extract_run_scripts(self) -> Optional[Dict[str, str]]:
        """Extract scripts from package.json."""
        pkg_json_path = self.repo_path / 'package.json'
        if not pkg_json_path.exists():
            return None

        try:
            with open(pkg_json_path, 'r', encoding='utf-8') as f:
                pkg = json.load(f)
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

    def _build_call_graph(self, file_dependencies: Dict[str, Dict]) -> Dict[str, Dict[str, Any]]:
        """
        Build a call graph showing which functions call which other functions.
        Returns a dict mapping qualified function IDs to their call relationships.
        """
        call_graph: Dict[str, Dict[str, Any]] = {}

        # Phase 1: Build registry of all known functions
        # Maps function_name -> list of qualified_ids (handles name collisions)
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
                }
                if func_name not in func_registry:
                    func_registry[func_name] = []
                func_registry[func_name].append(qualified_id)

        # Phase 2: Extract call relationships for each file
        for file_path, meta in self.files.items():
            content = self._file_contents.get(file_path, '')
            if not content:
                continue

            ext = meta.get('extension', '')

            if ext == '.py':
                self._extract_python_calls(file_path, content, call_graph, func_registry, file_dependencies)
            elif ext in {'.js', '.jsx', '.ts', '.tsx'}:
                self._extract_js_calls(file_path, content, call_graph, func_registry, file_dependencies)
            elif ext == '.java':
                self._extract_java_calls(file_path, content, call_graph, func_registry, file_dependencies)
            elif ext == '.go':
                self._extract_go_calls(file_path, content, call_graph, func_registry, file_dependencies)

        # Phase 3: Build reverse mapping (called_by)
        for qualified_id, info in call_graph.items():
            for callee_id in info['calls']:
                if callee_id in call_graph:
                    if qualified_id not in call_graph[callee_id]['called_by']:
                        call_graph[callee_id]['called_by'].append(qualified_id)

        return call_graph

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
            if func_name:
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

        # For each function body, search for calls to known functions
        for func_name, body in functions_in_file:
            caller_id = f"{file_path}::{func_name}"
            if caller_id not in call_graph:
                continue

            for known_name in known_names:
                # Skip very short names to avoid false positives
                if len(known_name) < 2:
                    continue
                if re.search(r'\b' + re.escape(known_name) + r'\s*\(', body):
                    resolved = self._resolve_call(known_name, file_path, func_registry, resolved_deps)
                    for target_id in resolved:
                        if target_id != caller_id:
                            if target_id not in call_graph[caller_id]['calls']:
                                call_graph[caller_id]['calls'].append(target_id)

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
        for method_name, body in methods_in_file:
            caller_id = f"{file_path}::{method_name}"
            if caller_id not in call_graph:
                continue

            for known_name in known_names:
                if len(known_name) < 2:
                    continue
                if re.search(r'\b' + re.escape(known_name) + r'\s*\(', body):
                    resolved = self._resolve_call(known_name, file_path, func_registry, resolved_deps)
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
        for func_name, body in funcs_in_file:
            caller_id = f"{file_path}::{func_name}"
            if caller_id not in call_graph:
                continue

            for known_name in known_names:
                if len(known_name) < 2:
                    continue
                if re.search(r'\b' + re.escape(known_name) + r'\s*\(', body):
                    resolved = self._resolve_call(known_name, file_path, func_registry, resolved_deps)
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
