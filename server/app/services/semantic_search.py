import re
from typing import List, Dict, Any, Set
from collections import defaultdict

# Comprehensive concept mappings - bidirectional relationships
CONCEPTS = {
    # Authentication & Security
    "auth": {"authentication", "authorize", "authorization", "login", "logout", "signin", "signout", "signup", "register", "session", "jwt", "token", "oauth", "password", "credential", "user", "permission", "role", "access", "security", "protect", "guard", "middleware"},
    "login": {"auth", "authentication", "signin", "session", "credential", "user", "password"},
    "security": {"auth", "authentication", "protect", "guard", "encrypt", "decrypt", "hash", "salt", "csrf", "xss", "sanitize"},

    # API & Network
    "api": {"endpoint", "route", "router", "controller", "handler", "request", "response", "rest", "graphql", "fetch", "http", "get", "post", "put", "delete", "patch", "crud", "service", "client"},
    "endpoint": {"api", "route", "router", "controller", "handler", "url", "path"},
    "request": {"fetch", "http", "api", "get", "post", "axios", "response", "body", "header", "param", "query"},
    "response": {"request", "http", "api", "status", "body", "header", "json", "data"},

    # Database & Storage
    "database": {"db", "sql", "nosql", "query", "model", "schema", "migration", "repository", "orm", "entity", "table", "collection", "mongo", "postgres", "mysql", "sqlite", "redis", "storage", "persist", "save", "find", "create", "update", "delete"},
    "db": {"database", "sql", "query", "model", "schema", "repository", "connection", "pool"},
    "model": {"schema", "entity", "database", "orm", "table", "type", "interface", "class", "data"},
    "query": {"database", "db", "sql", "find", "select", "where", "filter", "search"},

    # UI/Frontend
    "component": {"widget", "element", "view", "ui", "render", "page", "screen", "layout", "template", "jsx", "tsx", "html", "dom"},
    "ui": {"component", "view", "frontend", "interface", "layout", "style", "design", "ux", "render", "display", "screen"},
    "style": {"css", "scss", "sass", "less", "tailwind", "styled", "theme", "color", "font", "layout", "design", "class"},
    "page": {"component", "view", "screen", "route", "layout", "template"},

    # State Management
    "state": {"store", "redux", "context", "provider", "reducer", "action", "dispatch", "selector", "atom", "signal", "reactive", "observable", "subscribe"},
    "store": {"state", "redux", "context", "provider", "global", "persist"},

    # Testing
    "test": {"spec", "testing", "jest", "mocha", "pytest", "unittest", "assert", "expect", "describe", "it", "mock", "stub", "spy", "fixture", "coverage", "e2e", "integration", "unit"},
    "mock": {"test", "fake", "stub", "spy", "fixture"},

    # Error Handling
    "error": {"exception", "catch", "throw", "try", "handle", "failure", "fail", "bug", "issue", "problem", "crash", "panic", "recover"},
    "exception": {"error", "catch", "throw", "try", "handle", "raise"},
    "handle": {"error", "exception", "catch", "process", "manage", "handler"},

    # Configuration
    "config": {"configuration", "settings", "env", "environment", "options", "setup", "init", "initialize", "bootstrap", "constant", "variable"},
    "settings": {"config", "configuration", "options", "preferences", "env"},
    "env": {"environment", "config", "variable", "secret", "dotenv"},

    # Utilities & Helpers
    "util": {"utility", "helper", "utils", "common", "shared", "lib", "tool", "function"},
    "helper": {"util", "utility", "utils", "common", "shared", "support"},
    "common": {"shared", "util", "helper", "base", "core", "generic"},

    # Validation
    "validate": {"validation", "validator", "check", "verify", "sanitize", "clean", "parse", "schema", "rule", "constraint"},
    "validation": {"validate", "validator", "check", "verify", "schema", "form", "input"},

    # File & IO
    "file": {"read", "write", "stream", "buffer", "path", "directory", "folder", "upload", "download", "fs", "io"},
    "upload": {"file", "image", "media", "multipart", "form", "stream"},
    "download": {"file", "export", "save", "stream"},

    # Logging & Monitoring
    "log": {"logger", "logging", "debug", "info", "warn", "error", "trace", "print", "console", "monitor"},
    "logger": {"log", "logging", "winston", "pino", "bunyan"},

    # Cache & Performance
    "cache": {"redis", "memcache", "memory", "store", "ttl", "expire", "invalidate", "performance"},
    "performance": {"optimize", "fast", "speed", "cache", "lazy", "async", "parallel"},

    # Async & Concurrency
    "async": {"await", "promise", "future", "concurrent", "parallel", "thread", "worker", "queue", "job", "task"},
    "promise": {"async", "await", "then", "catch", "resolve", "reject"},

    # Types & Interfaces
    "type": {"interface", "class", "struct", "model", "schema", "definition", "declare", "generic"},
    "interface": {"type", "contract", "abstract", "protocol", "api"},

    # Hooks & Events
    "hook": {"use", "lifecycle", "effect", "callback", "event", "listener", "subscribe", "emit"},
    "event": {"hook", "listener", "emit", "dispatch", "subscribe", "handler", "callback", "on"},

    # Navigation & Routing
    "route": {"router", "navigation", "path", "url", "link", "redirect", "navigate", "page", "endpoint"},
    "navigation": {"route", "router", "menu", "breadcrumb", "link", "navigate"},

    # Forms
    "form": {"input", "field", "submit", "validate", "validation", "control", "formik", "react-hook-form"},
    "input": {"form", "field", "text", "value", "change", "control"},

    # Data Processing
    "data": {"model", "entity", "object", "json", "parse", "transform", "map", "filter", "reduce", "process"},
    "transform": {"data", "convert", "map", "parse", "format", "serialize", "deserialize"},

    # Service & Business Logic
    "service": {"business", "logic", "provider", "api", "client", "repository", "handler", "manager"},
    "business": {"service", "logic", "domain", "rule", "process"},
}

def split_identifier(name: str) -> List[str]:
    """Split camelCase, PascalCase, and snake_case identifiers into words."""
    # Handle snake_case and kebab-case
    name = name.replace('-', '_')
    parts = name.split('_')

    words = []
    for part in parts:
        # Split camelCase and PascalCase
        # Insert space before uppercase letters that follow lowercase letters
        split = re.sub(r'([a-z])([A-Z])', r'\1 \2', part)
        # Also split consecutive uppercase followed by lowercase (e.g., XMLParser -> XML Parser)
        split = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', split)
        words.extend(split.lower().split())

    return [w for w in words if len(w) > 1]  # Filter out single chars

def expand_query(query: str) -> Set[str]:
    """Expand query with related concepts."""
    # Split query into words
    words = set(re.findall(r'\w+', query.lower()))

    # Also split any camelCase/snake_case in query
    expanded_words = set()
    for word in words:
        expanded_words.add(word)
        expanded_words.update(split_identifier(word))

    # Add related concepts
    expanded = set(expanded_words)
    for word in expanded_words:
        if word in CONCEPTS:
            expanded.update(CONCEPTS[word])
        # Also check if word is part of any concept's related terms
        for concept, related in CONCEPTS.items():
            if word in related:
                expanded.add(concept)
                expanded.update(related)

    return expanded

def fuzzy_match(needle: str, haystack: str) -> float:
    """Calculate fuzzy match score between needle and haystack."""
    needle = needle.lower()
    haystack = haystack.lower()

    # Exact match
    if needle == haystack:
        return 1.0

    # Contains match
    if needle in haystack:
        # Score based on how much of haystack is the needle
        return 0.8 * (len(needle) / len(haystack))

    # Haystack contains needle as a word boundary match
    pattern = r'\b' + re.escape(needle)
    if re.search(pattern, haystack):
        return 0.7

    # Prefix match
    if haystack.startswith(needle):
        return 0.6

    # Suffix match
    if haystack.endswith(needle):
        return 0.5

    return 0.0

def calculate_relevance_score(item: Dict, query_terms: Set[str], expanded_terms: Set[str]) -> float:
    """Calculate relevance score for a search item."""
    score = 0.0

    name = item.get("name", "")
    name_lower = name.lower()
    file_path = item.get("file_path", "").lower()
    item_type = item.get("type", "")

    # Split the name into component words
    name_words = set(split_identifier(name))
    name_words.add(name_lower)

    # Extract directory/path components
    path_parts = set()
    for part in file_path.replace("\\", "/").split("/"):
        path_parts.add(part.lower())
        path_parts.update(split_identifier(part))

    # Score direct query term matches
    for term in query_terms:
        # Exact name match (highest score)
        if term == name_lower:
            score += 25.0
        # Name contains term
        elif term in name_lower:
            score += 15.0
        # Term matches a word in the name
        elif term in name_words:
            score += 12.0
        # Fuzzy match on name
        else:
            fuzzy = fuzzy_match(term, name_lower)
            if fuzzy > 0:
                score += fuzzy * 10.0

        # File path matches
        if term in file_path:
            score += 5.0
        elif term in path_parts:
            score += 3.0

    # Score expanded term matches (lower weight)
    for term in expanded_terms - query_terms:
        if term in name_lower or term in name_words:
            score += 4.0
        elif term in file_path or term in path_parts:
            score += 2.0
        else:
            fuzzy = fuzzy_match(term, name_lower)
            if fuzzy > 0.5:
                score += fuzzy * 3.0

    # Boost by type relevance
    type_boost = {
        "function": 1.5,
        "class": 1.4,
        "file": 1.2,
        "import": 0.6,
    }
    score *= type_boost.get(item_type, 1.0)

    # Bonus for matching multiple query terms
    matching_terms = sum(1 for t in query_terms if t in name_lower or t in name_words or t in file_path)
    if matching_terms > 1:
        score *= (1 + 0.2 * matching_terms)

    return score

def semantic_search(query: str, analysis_data: Dict, limit: int = 30) -> List[Dict[str, Any]]:
    """
    Perform semantic search on the analyzed repository data.

    Uses keyword expansion, fuzzy matching, and concept mapping to find relevant code elements.
    """
    if not query.strip():
        return []

    structure = analysis_data.get("structure_analysis", {})
    files = structure.get("files", {})

    # Parse query
    query_terms = set(re.findall(r'\w+', query.lower()))
    # Also split any camelCase in query
    for term in list(query_terms):
        query_terms.update(split_identifier(term))

    expanded_terms = expand_query(query)

    # Build search index
    search_index = []

    for file_path, info in files.items():
        # Normalize path
        normalized_path = file_path.replace("\\", "/")
        file_name = normalized_path.split("/")[-1]
        dir_path = "/".join(normalized_path.split("/")[:-1])

        # Add file
        search_index.append({
            "type": "file",
            "name": file_name,
            "file_path": normalized_path,
            "context": dir_path or "root",
        })

        # Add functions
        for func in info.get("functions", []):
            search_index.append({
                "type": "function",
                "name": func,
                "file_path": normalized_path,
                "context": f"function in {file_name}",
            })

        # Add classes
        for cls in info.get("classes", []):
            search_index.append({
                "type": "class",
                "name": cls,
                "file_path": normalized_path,
                "context": f"class in {file_name}",
            })

        # Add imports (but with lower priority - they'll get scored lower)
        for imp in info.get("imports", []):
            search_index.append({
                "type": "import",
                "name": imp,
                "file_path": normalized_path,
                "context": f"imported in {file_name}",
            })

    # Score all items
    scored_results = []
    for item in search_index:
        score = calculate_relevance_score(item, query_terms, expanded_terms)
        if score > 0:
            scored_results.append({
                **item,
                "score": round(score, 1),
            })

    # Sort by score and limit
    scored_results.sort(key=lambda x: x["score"], reverse=True)

    return scored_results[:limit]

def search_with_ai_ranking(query: str, analysis_data: Dict, groq_client=None) -> Dict[str, Any]:
    """
    Perform semantic search and return organized results.
    """
    results = semantic_search(query, analysis_data, limit=30)

    # Group results by type
    grouped = defaultdict(list)
    for result in results:
        grouped[result["type"]].append(result)

    # Sort groups to show most relevant types first
    type_order = ["function", "class", "file", "import"]
    sorted_grouped = {}
    for t in type_order:
        if t in grouped:
            sorted_grouped[t] = grouped[t]

    return {
        "query": query,
        "total_results": len(results),
        "results": results,
        "grouped": sorted_grouped,
    }
