"""
Architecture Analyzer Service

Generates a high-level architecture diagram model from analysis data.
Aggregates file-level data into directory/module-level components,
classifies them into architectural layers, and detects relationships.

Components follow the repository's shape instead of a fixed depth: each sub-project (a
directory with its own manifest, e.g. `backend/` and `frontend/` of a full-stack repo) starts
as one component, and the largest components are split along their directories until the
diagram holds about MAX_COMPONENTS boxes. Tests, examples and docs are collapsed into one
component per sub-project, and each component is labelled only with frameworks written in
its own language.
"""

import math
import posixpath
from typing import Dict, List, Any, Optional, Set, Tuple

from app.services import path_classifier
from app.services.path_classifier import DOCS, EXAMPLE, TEST


class ArchitectureAnalyzer:
    """
    Generates a high-level architecture diagram model from analysis data.
    """

    MAX_COMPONENTS = 20        # boxes in the diagram (secondary collapsed components included)
    MIN_SPLIT_FILES = 6        # a component with fewer files is never split further
    MIN_PART_FILES = 2         # a sub-directory with fewer files stays in its parent's component

    # Layer rules: directory names (one path segment), matched against a component's segments.
    # The component's own (last) segment counts most; ancestors count less. Two-segment rules
    # (`app/core`) only match those consecutive segments.
    LAYER_RULES = {
        'frontend': {'components', 'pages', 'views', 'screens', 'layouts', 'public', 'static', 'ui',
                     'hooks', 'widgets', 'styles', 'theme', 'src/app', 'app/routes'},
        'api': {'api', 'apis', 'routes', 'routers', 'router', 'controllers', 'controller', 'endpoints',
                'handlers', 'resolvers', 'graphql', 'rest', 'views', 'urls'},
        'middleware': {'middleware', 'middlewares', 'interceptors', 'guards'},
        'services': {'services', 'service', 'core', 'domain', 'business', 'logic', 'usecases', 'use_cases',
                     'workers', 'tasks', 'jobs', 'lib'},
        'data': {'models', 'model', 'schemas', 'schema', 'entities', 'entity', 'database', 'db', 'migrations',
                 'alembic', 'prisma', 'repositories', 'repository', 'dal', 'dao', 'orm', 'crud'},
        'config': {'config', 'configs', 'configuration', 'settings', 'conf', 'app/core'},
        'utils': {'utils', 'util', 'helpers', 'helper', 'shared', 'common', 'tools', 'lib/utils'},
    }
    # Top-level directories that say which side of a full-stack repo a component is on
    FRONTEND_ROOTS = {'frontend', 'client', 'web', 'webapp', 'www', 'ui', 'mobile'}
    BACKEND_ROOTS = {'backend', 'server', 'srv'}
    UI_EXTENSIONS = {'.tsx', '.jsx', '.vue', '.svelte'}
    # Collapsed component name and layer for each secondary category
    _SECONDARY_NAMES = {TEST: 'tests', EXAMPLE: 'examples', DOCS: 'docs'}
    _SECONDARY_LAYERS = {TEST: 'tests', EXAMPLE: 'other', DOCS: 'other'}
    _ORM_NAMES = ('sqlalchemy', 'prisma', 'typeorm', 'sequelize', 'django', 'mongoose')

    def __init__(self, analysis_data: Dict[str, Any]):
        self.files = analysis_data.get('files', {})
        self.frameworks = analysis_data.get('frameworks', {'frontend': [], 'backend': []})
        self.databases = analysis_data.get('databases', [])
        self.file_dependencies = analysis_data.get('file_dependencies', {})
        self.entry_points = analysis_data.get('entry_points', [])
        # Directories holding a project manifest (package.json, pyproject.toml, Cargo.toml, ...)
        self.project_roots = sorted({r.strip('/') for r in analysis_data.get('project_roots', []) if r
                                     and not path_classifier.is_secondary_dir(r)},
                                    key=lambda r: -r.count('/'))
        # Framework name -> language families it is written in (React -> {javascript})
        self.framework_families: Dict[str, Set[str]] = {
            k: set(v) for k, v in (analysis_data.get('framework_families') or {}).items()}

    def generate(self) -> Dict[str, Any]:
        """Generate the architecture model."""
        # Step 1: Group files into directory-level components
        components = self._identify_components()

        # Step 2: Classify components into layers
        layers = self._classify_layers(components)

        # Step 3: Detect edges (component-to-component dependencies)
        edges = self._detect_edges(components)

        # Step 4: Build node list
        nodes = self._build_nodes(components, layers)

        # Step 5: Add framework/database labels
        self._label_nodes(nodes, components)

        # Step 6: Build layer summary
        layer_summary = self._build_layer_summary(nodes)

        return {
            "nodes": nodes,
            "edges": edges,
            "layers": layer_summary,
        }

    # ------------------------------------------------------------------ components
    def _project_root(self, path: str) -> str:
        """Deepest sub-project directory containing `path` ('' for the repository root)."""
        for root in self.project_roots:  # deepest first
            if path.startswith(root + '/'):
                return root
        return ''

    def _identify_components(self) -> Dict[str, Dict]:
        """Group files into components: one per sub-project, split along directories while the
        diagram stays readable; tests / examples / docs collapse into one per sub-project."""
        self._assignment: Dict[str, str] = {}
        secondary: Dict[str, List[str]] = {}
        secondary_category: Dict[str, str] = {}
        groups: Dict[str, List[str]] = {}

        for file_path in self.files:
            path = file_path.replace('\\', '/')
            category = path_classifier.classify_path(path)
            if category in self._SECONDARY_NAMES:
                comp_id = posixpath.join(self._project_root(path), self._SECONDARY_NAMES[category])
                secondary.setdefault(comp_id, []).append(file_path)
                secondary_category.setdefault(comp_id, category)
            else:  # primary and generated code stay where they live
                groups.setdefault(self._project_root(path), []).append(file_path)

        # Share the diagram between sub-projects (sqrt of their size, so a small backend next to a
        # large frontend still gets its api / models / core boxes), then split each one.
        budget = max(self.MAX_COMPONENTS - len(secondary), len(groups), 4)
        weights = {root: math.sqrt(len(files)) for root, files in groups.items()}
        total = sum(weights.values()) or 1.0
        split: Dict[str, List[str]] = {}
        for root, files in groups.items():
            share = max(1, int(round(budget * weights[root] / total)))
            split.update(self._split_groups({root: files}, budget=share))
        groups = split

        components: Dict[str, Dict] = {}
        for comp_dir, files in groups.items():
            components[comp_dir or '(root)'] = self._component(files, 'primary', comp_dir)
        for comp_id, files in secondary.items():
            if comp_id in components:  # a real `tests/` dir merged into its collapsed twin
                components[comp_id]['files'].extend(files)
                continue
            components[comp_id] = self._component(files, secondary_category[comp_id],
                                                  comp_id.rsplit('/', 1)[0] if '/' in comp_id else '')
        for comp_id, comp in components.items():
            for f in comp['files']:
                self._assignment[f] = comp_id
            self._summarise(comp)
        return components

    def _split_groups(self, groups: Dict[str, List[str]], budget: int) -> Dict[str, List[str]]:
        """Split the largest component into its sub-directories while the result fits `budget`."""
        frozen: Set[str] = set()
        while True:
            splittable = [d for d, fs in groups.items() if d not in frozen and self._subdirs(d, fs)]
            if not splittable:
                return groups
            # Chains (no files of their own, one sub-directory) descend for free
            chain = next((d for d in splittable if self._is_chain(d, groups[d])), None)
            target = chain or max(splittable, key=lambda d: (len(groups[d]), d))
            files = groups[target]
            if chain is None and len(files) < self.MIN_SPLIT_FILES:
                frozen.add(target)
                continue
            parts = self._split(target, files)
            if set(parts) == {target}:
                frozen.add(target)
                continue
            if chain is None and len(groups) - 1 + len(parts) > budget:
                # Out of room for the biggest box: detailing smaller ones would only unbalance
                return groups
            del groups[target]
            for d, fs in parts.items():
                groups.setdefault(d, []).extend(fs)

    @staticmethod
    def _rel(comp_dir: str, path: str) -> str:
        return path[len(comp_dir) + 1:] if comp_dir else path

    def _subdirs(self, comp_dir: str, files: List[str]) -> Set[str]:
        return {self._rel(comp_dir, f).split('/', 1)[0] for f in files if '/' in self._rel(comp_dir, f)}

    def _is_chain(self, comp_dir: str, files: List[str]) -> bool:
        return len(self._subdirs(comp_dir, files)) == 1 and all('/' in self._rel(comp_dir, f) for f in files)

    def _split(self, comp_dir: str, files: List[str]) -> Dict[str, List[str]]:
        parts: Dict[str, List[str]] = {}
        for f in files:
            rel = self._rel(comp_dir, f)
            key = posixpath.join(comp_dir, rel.split('/', 1)[0]) if '/' in rel else comp_dir
            parts.setdefault(key, []).append(f)
        if len(parts) > 1:  # tiny sub-directories stay with their parent
            for key in [k for k, fs in parts.items() if k != comp_dir and len(fs) < self.MIN_PART_FILES]:
                parts.setdefault(comp_dir, []).extend(parts.pop(key))
        return parts

    @staticmethod
    def _component(files: List[str], category: str, root: str) -> Dict[str, Any]:
        return {'files': list(files), 'category': category, 'root': root}

    def _summarise(self, comp: Dict[str, Any]) -> None:
        languages, extensions, families = set(), set(), set()
        family_lines: Dict[str, int] = {}
        functions = classes = lines = 0
        for f in comp['files']:
            meta = self.files.get(f, {})
            languages.add(meta.get('language', 'Unknown'))
            extensions.add(meta.get('extension', ''))
            family = path_classifier.language_family(f)
            if family:
                families.add(family)
                family_lines[family] = family_lines.get(family, 0) + max(meta.get('lines', 0), 1)
            functions += len(meta.get('functions', []))
            classes += len(meta.get('classes', []))
            lines += meta.get('lines', 0)
        main_family = max(family_lines, key=lambda k: (family_lines[k], k)) if family_lines else None
        comp.update(languages=sorted(languages), extensions=sorted(extensions), families=families,
                     main_family=main_family, functions_count=functions, classes_count=classes, lines=lines)

    # ------------------------------------------------------------------ layers
    def _ui_families(self) -> Set[str]:
        """Language families that can make up a frontend: JS/TS, plus any language with a detected
        UI framework (Streamlit -> python, JavaFX -> jvm). A Python backend never can otherwise."""
        fams = {'javascript'}
        for fw in self.frameworks.get('frontend', []):
            fams |= self.framework_families.get(fw, set())
        return fams

    def _classify_layers(self, components: Dict) -> Dict[str, str]:
        """Classify each component into an architectural layer."""
        classification = {}
        ui_families = self._ui_families()
        has_ui_framework = bool(self.frameworks.get('frontend'))

        for comp_id, comp in components.items():
            if comp['category'] in self._SECONDARY_LAYERS:
                classification[comp_id] = self._SECONDARY_LAYERS[comp['category']]
                continue
            segs = [] if comp_id == '(root)' else comp_id.lower().split('/')
            # Which side of a full-stack repo: decided by the outermost frontend / backend directory name
            side = next(('frontend' if s in self.FRONTEND_ROOTS else 'backend' for s in segs
                         if s in self.FRONTEND_ROOTS or s in self.BACKEND_ROOTS), None)
            # A component is frontend only when most of its code is in a UI language
            can_be_frontend = side != 'backend' and comp.get('main_family') in ui_families
            if side == 'frontend' and can_be_frontend:
                classification[comp_id] = 'frontend'
                continue

            layer, best = 'other', 0
            for layer_name, names in self.LAYER_RULES.items():
                if layer_name == 'frontend' and not can_be_frontend:
                    continue
                score = self._rule_score(segs, names)
                if score > best:
                    layer, best = layer_name, score

            if best == 0:
                if can_be_frontend and has_ui_framework and set(comp.get('extensions', [])) & self.UI_EXTENSIONS:
                    layer = 'frontend'
                elif side == 'backend':
                    layer = 'services'  # backend/app, server/src: the backend's own logic
            classification[comp_id] = layer

        return classification

    @staticmethod
    def _rule_score(segs: List[str], names: Set[str]) -> int:
        """12 for a two-segment rule ending at the component, 10 for the component's own name,
        4 for an ancestor directory name."""
        if not segs:
            return 0
        score = 0
        for name in names:
            parts = name.split('/')
            if len(parts) > 1:
                if len(segs) >= len(parts) and segs[-len(parts):] == parts:
                    score = max(score, 12)
            elif segs[-1] == name:
                score = max(score, 10)
            elif name in segs[:-1]:
                score = max(score, 4)
        return score

    # ------------------------------------------------------------------ edges / nodes
    def _detect_edges(self, components: Dict) -> List[Dict]:
        """Detect inter-component dependency edges."""
        edges = []
        edge_counts: Dict[Tuple[str, str], int] = {}  # Track edge weights

        for file_path, deps in self.file_dependencies.items():
            source_comp = self._file_to_component(file_path, components)

            for resolved_dep in deps.get('resolved', []):
                target_comp = self._file_to_component(resolved_dep, components)

                if source_comp and target_comp and source_comp != target_comp:
                    key = (source_comp, target_comp)
                    edge_counts[key] = edge_counts.get(key, 0) + 1

        # Convert to edge list with weights
        for (source, target), count in edge_counts.items():
            edges.append({
                "source": source,
                "target": target,
                "label": "imports",
                "weight": count,
            })

        return edges

    def _file_to_component(self, file_path: str, components: Dict) -> Optional[str]:
        """Map a file path to its component ID."""
        assignment = getattr(self, '_assignment', None)
        if assignment is not None:
            return assignment.get(file_path)
        for comp_id, comp_data in components.items():
            if file_path in comp_data['files']:
                return comp_id
        return None

    def _build_nodes(self, components: Dict, layers: Dict) -> List[Dict]:
        """Build the node list for the architecture diagram."""
        nodes = []

        for comp_id, comp_data in components.items():
            nodes.append({
                "id": comp_id,
                "label": 'Root' if comp_id == '(root)' else comp_id,
                "type": "component",
                "layer": layers.get(comp_id, 'other'),
                "category": comp_data['category'],
                "root": comp_data['root'] or '.',
                "file_count": len(comp_data['files']),
                "languages": comp_data['languages'],
                "functions_count": comp_data['functions_count'],
                "classes_count": comp_data['classes_count'],
                "lines": comp_data['lines'],
                "frameworks": [],  # Populated in _label_nodes
            })

        # Add database nodes if databases detected
        for db in self.databases:
            nodes.append({
                "id": f"db::{db}",
                "label": db,
                "type": "database",
                "layer": "data",
                "file_count": 0,
                "languages": [],
                "functions_count": 0,
                "classes_count": 0,
                "lines": 0,
                "frameworks": [],
            })

        return nodes

    def _label_nodes(self, nodes: List[Dict], components: Dict):
        """Label each component with the detected frameworks of its own language(s), for its layer."""
        def own(frameworks: List[str], families: Set[str]) -> List[str]:
            # Frameworks of unknown language are shown nowhere rather than everywhere
            return [fw for fw in frameworks if self.framework_families.get(fw, set()) & families]

        frontend_fws = self.frameworks.get('frontend', [])
        backend_fws = self.frameworks.get('backend', [])

        for node in nodes:
            if node['type'] == 'database':
                continue
            comp = components.get(node['id'], {})
            if comp.get('category') != 'primary':
                continue
            families = comp.get('families', set())
            layer = node.get('layer', 'other')

            if layer == 'frontend':
                node['frameworks'] = own(frontend_fws, families)
            elif layer in ('api', 'services', 'middleware'):
                node['frameworks'] = own(backend_fws, families)
            elif layer == 'data':
                # Data layer might use ORMs
                node['frameworks'] = [fw for fw in own(backend_fws, families)
                                      if any(orm in fw.lower() for orm in self._ORM_NAMES)]

    def _build_layer_summary(self, nodes: List[Dict]) -> List[Dict]:
        """Build a summary of layers with their component counts."""
        layer_order = ['frontend', 'api', 'middleware', 'services', 'data', 'config', 'utils', 'tests', 'other']
        layers = []

        for layer_name in layer_order:
            layer_nodes = [n['id'] for n in nodes if n.get('layer') == layer_name]
            if layer_nodes:
                layers.append({
                    "name": layer_name,
                    "nodes": layer_nodes,
                })

        return layers
