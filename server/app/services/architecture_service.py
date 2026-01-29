"""
Architecture Analyzer Service

Generates a high-level architecture diagram model from analysis data.
Aggregates file-level data into directory/module-level components,
classifies them into architectural layers, and detects relationships.
"""

from typing import Dict, List, Any, Optional, Set
from pathlib import Path
import re


class ArchitectureAnalyzer:
    """
    Generates a high-level architecture diagram model from analysis data.
    """

    # Layer classification rules (directory name patterns -> layer)
    LAYER_RULES = {
        'frontend': {
            'dirs': {'src/components', 'src/pages', 'src/views', 'src/app',
                     'client', 'frontend', 'web', 'ui', 'public', 'static',
                     'src/screens', 'src/layouts', 'components', 'pages', 'views'},
            'frameworks': {'React', 'Vue.js', 'Angular', 'Svelte', 'Next.js', 'Nuxt.js'},
            'extensions': {'.tsx', '.jsx', '.vue', '.svelte'},
        },
        'api': {
            'dirs': {'api', 'routes', 'controllers', 'endpoints', 'handlers',
                     'src/api', 'app/api', 'src/routes', 'app/routes',
                     'server/api', 'server/routes'},
            'patterns': [r'router', r'controller', r'handler', r'endpoint'],
        },
        'services': {
            'dirs': {'services', 'service', 'src/services', 'app/services',
                     'lib', 'src/lib', 'core', 'src/core', 'domain',
                     'business', 'logic', 'usecases', 'server/services'},
        },
        'data': {
            'dirs': {'models', 'schemas', 'entities', 'database', 'db',
                     'migrations', 'prisma', 'src/models', 'app/models',
                     'repositories', 'dal', 'server/models'},
            'frameworks': {'SQLAlchemy', 'Prisma', 'TypeORM', 'Sequelize'},
        },
        'config': {
            'dirs': {'config', 'configuration', 'settings', 'src/config',
                     'app/config', 'app/core'},
            'files': {'config.py', 'settings.py', 'config.ts', 'config.js'},
        },
        'tests': {
            'dirs': {'tests', 'test', '__tests__', 'spec', 'specs',
                     'src/__tests__', 'src/test', 'e2e', 'integration'},
        },
        'middleware': {
            'dirs': {'middleware', 'middlewares', 'src/middleware',
                     'app/middleware', 'interceptors'},
        },
        'utils': {
            'dirs': {'utils', 'helpers', 'shared', 'common', 'src/utils',
                     'src/helpers', 'tools', 'lib/utils'},
        },
    }

    def __init__(self, analysis_data: Dict[str, Any]):
        self.files = analysis_data.get('files', {})
        self.frameworks = analysis_data.get('frameworks', {'frontend': [], 'backend': []})
        self.databases = analysis_data.get('databases', [])
        self.file_dependencies = analysis_data.get('file_dependencies', {})
        self.entry_points = analysis_data.get('entry_points', [])

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
        self._label_nodes(nodes, layers)

        # Step 6: Build layer summary
        layer_summary = self._build_layer_summary(nodes)

        return {
            "nodes": nodes,
            "edges": edges,
            "layers": layer_summary,
        }

    def _identify_components(self) -> Dict[str, Dict]:
        """Group files into logical components based on directory structure."""
        components: Dict[str, Dict] = {}

        for file_path, meta in self.files.items():
            normalized = file_path.replace('\\', '/')
            parts = normalized.split('/')

            # Use first 1-2 directory levels as component ID
            if len(parts) >= 3:
                component_id = '/'.join(parts[:2])
            elif len(parts) >= 2:
                component_id = parts[0]
            else:
                component_id = '(root)'

            if component_id not in components:
                components[component_id] = {
                    'files': [],
                    'languages': set(),
                    'extensions': set(),
                    'functions_count': 0,
                    'classes_count': 0,
                    'lines': 0,
                }

            components[component_id]['files'].append(file_path)
            components[component_id]['languages'].add(meta.get('language', 'Unknown'))
            components[component_id]['extensions'].add(meta.get('extension', ''))
            components[component_id]['functions_count'] += len(meta.get('functions', []))
            components[component_id]['classes_count'] += len(meta.get('classes', []))
            components[component_id]['lines'] += meta.get('lines', 0)

        # Convert sets to lists for JSON serialization
        for comp in components.values():
            comp['languages'] = list(comp['languages'])
            comp['extensions'] = list(comp['extensions'])

        return components

    def _classify_layers(self, components: Dict) -> Dict[str, str]:
        """Classify each component into an architectural layer."""
        classification = {}

        all_fw = self.frameworks.get('frontend', []) + self.frameworks.get('backend', [])

        for comp_id, comp_data in components.items():
            comp_lower = comp_id.lower().replace('\\', '/')
            layer = 'other'
            best_match_score = 0

            for layer_name, rules in self.LAYER_RULES.items():
                score = 0

                # Check directory name match
                for d in rules.get('dirs', set()):
                    d_lower = d.lower()
                    if comp_lower == d_lower or comp_lower.startswith(d_lower + '/'):
                        score += 10
                        break
                    if '/' + d_lower in comp_lower or comp_lower.endswith('/' + d_lower.split('/')[-1]):
                        score += 5
                        break

                # Check framework association
                if any(fw in rules.get('frameworks', set()) for fw in all_fw):
                    # Check if component contains files with relevant extensions
                    if 'extensions' in rules:
                        if any(ext in rules['extensions'] for ext in comp_data.get('extensions', [])):
                            score += 8

                # Check if component has frontend-like extensions
                if layer_name == 'frontend':
                    frontend_exts = {'.tsx', '.jsx', '.vue', '.svelte'}
                    if any(ext in frontend_exts for ext in comp_data.get('extensions', [])):
                        score += 3

                if score > best_match_score:
                    best_match_score = score
                    layer = layer_name

            classification[comp_id] = layer

        return classification

    def _detect_edges(self, components: Dict) -> List[Dict]:
        """Detect inter-component dependency edges."""
        edges = []
        edge_counts: Dict[str, int] = {}  # Track edge weights

        for file_path, deps in self.file_dependencies.items():
            source_comp = self._file_to_component(file_path, components)

            for resolved_dep in deps.get('resolved', []):
                target_comp = self._file_to_component(resolved_dep, components)

                if source_comp and target_comp and source_comp != target_comp:
                    edge_key = f"{source_comp}->{target_comp}"
                    edge_counts[edge_key] = edge_counts.get(edge_key, 0) + 1

        # Convert to edge list with weights
        for edge_key, count in edge_counts.items():
            source, target = edge_key.split('->')
            edges.append({
                "source": source,
                "target": target,
                "label": "imports",
                "weight": count,
            })

        return edges

    def _file_to_component(self, file_path: str, components: Dict) -> Optional[str]:
        """Map a file path to its component ID."""
        for comp_id, comp_data in components.items():
            if file_path in comp_data['files']:
                return comp_id
        return None

    def _build_nodes(self, components: Dict, layers: Dict) -> List[Dict]:
        """Build the node list for the architecture diagram."""
        nodes = []

        for comp_id, comp_data in components.items():
            # Create a readable label from the component ID
            label = comp_id.split('/')[-1].replace('_', ' ').replace('-', ' ').title()
            if comp_id == '(root)':
                label = 'Root'

            nodes.append({
                "id": comp_id,
                "label": label,
                "type": "component",
                "layer": layers.get(comp_id, 'other'),
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

    def _label_nodes(self, nodes: List[Dict], layers: Dict):
        """Add framework labels to nodes based on detected frameworks."""
        frontend_fws = self.frameworks.get('frontend', [])
        backend_fws = self.frameworks.get('backend', [])

        for node in nodes:
            if node['type'] == 'database':
                continue

            layer = node.get('layer', 'other')

            if layer == 'frontend' and frontend_fws:
                node['frameworks'] = frontend_fws
            elif layer in ('api', 'services') and backend_fws:
                node['frameworks'] = backend_fws
            elif layer == 'data' and backend_fws:
                # Data layer might use ORMs
                orm_frameworks = [fw for fw in backend_fws if any(
                    orm in fw.lower() for orm in ['sqlalchemy', 'prisma', 'typeorm', 'sequelize', 'django']
                )]
                if orm_frameworks:
                    node['frameworks'] = orm_frameworks

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
