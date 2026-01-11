import os
import ast
import re
import json
import toml
from pathlib import Path
from typing import Dict, List, Set, Optional, Any

class CodeAnalyzer:
    """Analyzes code files to extract structure, imports, functions, and classes."""

    # Directories to skip during analysis
    SKIP_DIRS = {
        '.git', 'node_modules', 'dist', 'build', '__pycache__',
        '.venv', 'venv', 'env', '.next', 'out', 'coverage',
        '.pytest_cache', '.mypy_cache', 'vendor', 'target'
    }

    # Common entry point patterns
    ENTRY_POINT_PATTERNS = [
        'main.py', 'app.py', '__main__.py', 'run.py', 'server.py',
        'index.js', 'index.ts', 'main.js', 'main.ts', 'app.js', 'app.ts',
        'index.jsx', 'index.tsx', 'server.js', 'server.ts'
    ]

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.file_metadata = {}
        self.language_stats = {}

    def analyze(self) -> Dict:
        """Main analysis method that orchestrates the entire code analysis."""
        files = self._get_all_files()

        for file_path in files:
            metadata = self._analyze_file(file_path)
            if metadata:
                relative_path = str(file_path.relative_to(self.repo_path))
                self.file_metadata[relative_path] = metadata

                # Update language stats
                lang = metadata['language']
                if lang not in self.language_stats:
                    self.language_stats[lang] = {'count': 0, 'lines': 0}
                self.language_stats[lang]['count'] += 1
                self.language_stats[lang]['lines'] += metadata.get('lines', 0)

        entry_points = self._detect_entry_points()
        key_files = self._identify_key_files()

        # NEW: Build file tree structure
        file_tree = self._build_file_tree()

        # NEW: Extract README content
        readme_content = self._extract_readme()

        # NEW: Parse dependencies
        dependencies = self._parse_dependencies()

        # NEW: Detect license
        license_info = self._detect_license()

        return {
            'total_files': len(self.file_metadata),
            'languages': self.language_stats,
            'entry_points': entry_points,
            'key_files': key_files,
            'tree': file_tree,
            'readme': readme_content,
            'dependencies': dependencies,
            'license': license_info,
            'files': self.file_metadata
        }

    def _get_all_files(self) -> List[Path]:
        """Recursively get all code files, skipping ignored directories."""
        files = []
        for root, dirs, filenames in os.walk(self.repo_path):
            # Remove skip directories from search
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]

            for filename in filenames:
                file_path = Path(root) / filename
                if self._is_code_file(filename):
                    files.append(file_path)

        return files

    def _is_code_file(self, filename: str) -> bool:
        """Check if file is a code file we want to analyze."""
        code_extensions = {
            '.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.cpp', '.c',
            '.h', '.hpp', '.go', '.rs', '.rb', '.php', '.cs', '.swift',
            '.kt', '.scala', '.sh', '.bash', '.yaml', '.yml', '.json',
            '.toml', '.md', '.sql', '.html', '.css', '.scss', '.vue'
        }
        return Path(filename).suffix.lower() in code_extensions

    def _analyze_file(self, file_path: Path) -> Optional[Dict]:
        """Analyze a single file and return its metadata."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            ext = file_path.suffix.lower()
            language = self._get_language(ext)

            metadata = {
                'path': str(file_path.relative_to(self.repo_path)),
                'language': language,
                'extension': ext,
                'size': file_path.stat().st_size,
                'lines': len(content.splitlines())
            }

            # Language-specific analysis
            if ext == '.py':
                metadata.update(self._analyze_python(content))
            elif ext in ['.js', '.jsx', '.ts', '.tsx']:
                metadata.update(self._analyze_javascript(content))

            return metadata

        except Exception as e:
            # Skip files that can't be read
            return None

    def _get_language(self, ext: str) -> str:
        """Map file extension to language name."""
        lang_map = {
            '.py': 'Python',
            '.js': 'JavaScript',
            '.jsx': 'JavaScript',
            '.ts': 'TypeScript',
            '.tsx': 'TypeScript',
            '.java': 'Java',
            '.cpp': 'C++',
            '.c': 'C',
            '.go': 'Go',
            '.rs': 'Rust',
            '.rb': 'Ruby',
            '.php': 'PHP',
            '.cs': 'C#',
            '.swift': 'Swift',
            '.kt': 'Kotlin',
            '.md': 'Markdown',
            '.json': 'JSON',
            '.yaml': 'YAML',
            '.yml': 'YAML',
            '.html': 'HTML',
            '.css': 'CSS',
            '.scss': 'SCSS'
        }
        return lang_map.get(ext, 'Other')

    def _analyze_python(self, content: str) -> Dict:
        """Analyze Python file using AST."""
        try:
            tree = ast.parse(content)

            imports = []
            functions = []
            classes = []

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)
                elif isinstance(node, ast.FunctionDef):
                    functions.append({
                        'name': node.name,
                        'line': node.lineno,
                        'is_async': isinstance(node, ast.AsyncFunctionDef)
                    })
                elif isinstance(node, ast.ClassDef):
                    classes.append({
                        'name': node.name,
                        'line': node.lineno,
                        'methods': [m.name for m in node.body if isinstance(m, ast.FunctionDef)]
                    })

            return {
                'imports': list(set(imports)),
                'functions': functions,
                'classes': classes,
                'has_main': any(f['name'] == '__main__' or
                              (f['name'] == 'main' and f.get('line', 0) > 0)
                              for f in functions) or '__main__' in content
            }
        except:
            return {'imports': [], 'functions': [], 'classes': []}

    def _analyze_javascript(self, content: str) -> Dict:
        """Analyze JavaScript/TypeScript file using regex patterns."""
        # Basic import detection
        import_pattern = r'(?:import|require)\s*(?:\{[^}]+\}|\w+)\s*from\s*[\'"]([^\'"]+)[\'"]'
        imports = re.findall(import_pattern, content)

        # Function detection
        func_pattern = r'(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(|(\w+)\s*:\s*(?:async\s*)?\()'
        functions = []
        for match in re.finditer(func_pattern, content):
            func_name = match.group(1) or match.group(2) or match.group(3)
            if func_name:
                functions.append({
                    'name': func_name,
                    'line': content[:match.start()].count('\n') + 1
                })

        # Class detection
        class_pattern = r'class\s+(\w+)'
        classes = []
        for match in re.finditer(class_pattern, content):
            classes.append({
                'name': match.group(1),
                'line': content[:match.start()].count('\n') + 1
            })

        return {
            'imports': list(set(imports)),
            'functions': functions,
            'classes': classes,
            'has_main': 'main(' in content or 'Main' in [c['name'] for c in classes]
        }

    def _detect_entry_points(self) -> List[str]:
        """Detect likely entry points in the repository."""
        entry_points = []

        for file_path, metadata in self.file_metadata.items():
            filename = Path(file_path).name.lower()

            # Check common entry point filenames
            if filename in self.ENTRY_POINT_PATTERNS:
                entry_points.append(file_path)

            # Check for main function/block
            elif metadata.get('has_main', False):
                entry_points.append(file_path)

        return entry_points

    def _identify_key_files(self) -> List[str]:
        """Identify key/important files based on various heuristics."""
        key_files = []

        for file_path, metadata in self.file_metadata.items():
            filename = Path(file_path).name.lower()

            # Config files
            if filename in ['package.json', 'requirements.txt', 'pyproject.toml',
                          'cargo.toml', 'go.mod', 'pom.xml', 'build.gradle',
                          'dockerfile', 'docker-compose.yml', '.env.example',
                          'makefile', 'readme.md', 'license']:
                key_files.append(file_path)

            # Files with many imports (likely central to architecture)
            elif len(metadata.get('imports', [])) > 5:
                key_files.append(file_path)

            # Files with many classes/functions
            elif (len(metadata.get('classes', [])) + len(metadata.get('functions', []))) > 10:
                key_files.append(file_path)

        return key_files[:20]  # Limit to top 20 key files

    def _build_file_tree(self) -> Dict[str, Any]:
        """Build a hierarchical tree structure of files and folders."""
        tree = {}

        for file_path in self.file_metadata.keys():
            parts = Path(file_path).parts
            current = tree

            for i, part in enumerate(parts):
                if i == len(parts) - 1:  # It's a file
                    current[part] = {
                        'type': 'file',
                        'size': self.file_metadata[file_path].get('size', 0),
                        'language': self.file_metadata[file_path].get('language', 'Unknown'),
                        'lines': self.file_metadata[file_path].get('lines', 0)
                    }
                else:  # It's a directory
                    if part not in current:
                        current[part] = {'type': 'folder', 'children': {}}
                    elif current[part].get('type') != 'folder':
                        # Convert to folder if it wasn't already
                        current[part] = {'type': 'folder', 'children': {}}
                    current = current[part]['children']

        return tree

    def _extract_readme(self) -> Optional[Dict[str, str]]:
        """Extract README content if it exists."""
        readme_patterns = ['README.md', 'readme.md', 'README', 'readme.txt', 'README.rst']

        for pattern in readme_patterns:
            readme_path = self.repo_path / pattern
            if readme_path.exists():
                try:
                    with open(readme_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        return {
                            'file': pattern,
                            'content': content[:5000],  # Limit to first 5000 chars
                            'full_length': len(content)
                        }
                except:
                    continue

        return None

    def _parse_dependencies(self) -> Dict[str, Any]:
        """Parse dependency files to extract project dependencies."""
        dependencies = {
            'python': {},
            'javascript': {},
            'other': {}
        }

        # Parse requirements.txt
        req_file = self.repo_path / 'requirements.txt'
        if req_file.exists():
            try:
                with open(req_file, 'r', encoding='utf-8') as f:
                    deps = []
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            # Extract package name (before ==, >=, etc.)
                            pkg = re.split(r'[=<>!]', line)[0].strip()
                            deps.append(line)
                    dependencies['python']['requirements.txt'] = deps
            except:
                pass

        # Parse pyproject.toml
        pyproject_file = self.repo_path / 'pyproject.toml'
        if pyproject_file.exists():
            try:
                with open(pyproject_file, 'r', encoding='utf-8') as f:
                    data = toml.load(f)

                    # Poetry dependencies
                    if 'tool' in data and 'poetry' in data['tool']:
                        poetry_deps = data['tool']['poetry'].get('dependencies', {})
                        dependencies['python']['poetry'] = list(poetry_deps.keys())

                    # PEP 621 dependencies
                    if 'project' in data:
                        project_deps = data['project'].get('dependencies', [])
                        dependencies['python']['pyproject'] = project_deps
            except:
                pass

        # Parse package.json
        package_file = self.repo_path / 'package.json'
        if package_file.exists():
            try:
                with open(package_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    dependencies['javascript']['production'] = list(data.get('dependencies', {}).keys())
                    dependencies['javascript']['dev'] = list(data.get('devDependencies', {}).keys())
            except:
                pass

        # Parse Cargo.toml (Rust)
        cargo_file = self.repo_path / 'Cargo.toml'
        if cargo_file.exists():
            try:
                with open(cargo_file, 'r', encoding='utf-8') as f:
                    data = toml.load(f)
                    dependencies['other']['rust'] = list(data.get('dependencies', {}).keys())
            except:
                pass

        # Parse go.mod (Go)
        go_file = self.repo_path / 'go.mod'
        if go_file.exists():
            try:
                with open(go_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Extract require statements
                    requires = re.findall(r'require\s+([^\s]+)', content)
                    dependencies['other']['go'] = requires
            except:
                pass

        return dependencies

    def _detect_license(self) -> Optional[Dict[str, str]]:
        """Detect license file and try to identify the license type."""
        license_patterns = ['LICENSE', 'LICENSE.md', 'LICENSE.txt', 'LICENCE', 'license', 'license.md']

        for pattern in license_patterns:
            license_path = self.repo_path / pattern
            if license_path.exists():
                try:
                    with open(license_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()[:1000]  # Read first 1000 chars

                        # Simple license detection
                        license_type = 'Unknown'
                        if 'MIT License' in content or 'MIT' in content[:200]:
                            license_type = 'MIT'
                        elif 'Apache License' in content:
                            license_type = 'Apache 2.0'
                        elif 'GNU GENERAL PUBLIC LICENSE' in content:
                            if 'Version 3' in content:
                                license_type = 'GPL-3.0'
                            elif 'Version 2' in content:
                                license_type = 'GPL-2.0'
                        elif 'BSD' in content[:200]:
                            license_type = 'BSD'
                        elif 'ISC License' in content:
                            license_type = 'ISC'

                        return {
                            'file': pattern,
                            'type': license_type,
                            'preview': content[:500]
                        }
                except:
                    continue

        return None
