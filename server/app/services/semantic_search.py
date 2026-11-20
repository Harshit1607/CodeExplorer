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

# ---------------------------------------------------------------------------
# Index construction
# ---------------------------------------------------------------------------
def files_from_analysis_data(analysis_data: Dict) -> Dict[str, Dict]:
    """Extract {path: {functions, classes, imports}} from client-supplied analysis data."""
    if not analysis_data:
        return {}
    if "repoMeta" in analysis_data or "complexity" in analysis_data:
        return {
            f["file"]: {
                "functions": f.get("functions", []),
                "classes": f.get("classes", []),
                "imports": f.get("imports", []),
            }
            for f in (analysis_data.get("complexity") or {}).get("fileList", [])
            if f.get("file")
        }
    return analysis_data.get("structure_analysis", {}).get("files", {})


def _build_keyword_index(files: Dict[str, Dict]) -> List[Dict[str, Any]]:
    index = []
    for file_path, info in files.items():
        path = file_path.replace("\\", "/")
        file_name = path.split("/")[-1]
        dir_path = "/".join(path.split("/")[:-1])
        index.append({"type": "file", "name": file_name, "file_path": path, "context": dir_path or "root"})
        for func in info.get("functions", []):
            index.append({"type": "function", "name": func, "file_path": path, "context": f"function in {file_name}"})
        for cls in info.get("classes", []):
            index.append({"type": "class", "name": cls, "file_path": path, "context": f"class in {file_name}"})
        for imp in info.get("imports", []):
            index.append({"type": "import", "name": imp, "file_path": path, "context": f"imported in {file_name}"})
    return index


def _parse_query(query: str):
    terms = set(re.findall(r'\w+', query.lower()))
    for term in list(terms):
        terms.update(split_identifier(term))
    return terms, expand_query(query)


# ---------------------------------------------------------------------------
# Keyword search (concept expansion + fuzzy name matching)
# ---------------------------------------------------------------------------
def keyword_search(query: str, files: Dict[str, Dict], limit: int = 30) -> List[Dict[str, Any]]:
    if not query.strip():
        return []
    query_terms, expanded_terms = _parse_query(query)
    scored = []
    for item in _build_keyword_index(files):
        score = calculate_relevance_score(item, query_terms, expanded_terms)
        if score > 0:
            scored.append({**item, "score": round(score, 1)})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


def semantic_search(query: str, analysis_data: Dict, limit: int = 30) -> List[Dict[str, Any]]:
    """Backward-compatible keyword search over client-supplied analysis data."""
    return keyword_search(query, files_from_analysis_data(analysis_data), limit)


# ---------------------------------------------------------------------------
# Hybrid search: keyword ranking + vector ranking, fused with RRF
# ---------------------------------------------------------------------------
RRF_K = 60                 # standard reciprocal-rank-fusion constant
MIN_VECTOR_SIMILARITY = 0.45
SNIPPET_LINES = 14
TYPE_ORDER = ["function", "class", "file", "import"]


def _chunk_to_item(chunk) -> Dict[str, Any]:
    """Map an embedded chunk onto the same identity scheme as the keyword index."""
    file_name = chunk.file.split("/")[-1]
    if chunk.symbol and chunk.kind in ("function", "method", "class"):
        short = chunk.symbol.split(".")[-1]
        item_type = "class" if chunk.kind == "class" else "function"
        context = f"{chunk.kind} {chunk.symbol} in {file_name}"
        return {"type": item_type, "name": short, "file_path": chunk.file, "context": context}
    return {"type": "file", "name": file_name, "file_path": chunk.file,
            "context": "/".join(chunk.file.split("/")[:-1]) or "root"}


def _key(item: Dict[str, Any]):
    return item["type"], item["name"], item["file_path"]


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_$][\w$.]*$")
_SECONDARY_PATH_RE = re.compile(r"(^|/)(tests?|__tests__|__mocks__|spec|specs|examples?|samples?|demos?|docs|fixtures?|benchmarks?)(/|$)|(^|/)test_|_test\.|\.test\.|\.spec\.")
_SECONDARY_QUERY_RE = re.compile(r"\b(tests?|spec|specs|mock|fixtures?|examples?|samples?|demo)\b", re.I)


def _fusion_weights(query: str):
    """(keyword_weight, vector_weight). Identifier lookups trust keywords, phrases trust vectors."""
    words = query.split()
    if len(words) == 1 and _IDENTIFIER_RE.match(words[0]):
        return 1.0, 0.6
    if len(words) <= 2:
        return 0.8, 1.0
    return 0.4, 1.0


def hybrid_search(query: str, files: Dict[str, Dict], vector_index=None,
                  limit: int = 30, mode: str = "hybrid") -> Dict[str, Any]:
    use_vectors = mode in ("hybrid", "semantic") and vector_index is not None and vector_index.searchable
    use_keywords = mode in ("hybrid", "keyword") or not use_vectors

    kw_results = keyword_search(query, files, limit=100) if use_keywords else []

    vec_items: Dict[tuple, Dict[str, Any]] = {}
    if use_vectors:
        for chunk, sim in vector_index.search(query, k=80, min_score=MIN_VECTOR_SIMILARITY):
            item = _chunk_to_item(chunk)
            k = _key(item)
            if k in vec_items and vec_items[k]["similarity"] >= sim:
                continue  # keep the best-matching chunk per symbol
            lines = chunk.code.splitlines()
            snippet = "\n".join(lines[:SNIPPET_LINES]) + ("\n..." if len(lines) > SNIPPET_LINES else "")
            vec_items[k] = {**item, "similarity": round(sim, 3), "start_line": chunk.start_line,
                            "end_line": chunk.end_line, "snippet": snippet}

    vec_ranked = sorted(vec_items.values(), key=lambda x: x["similarity"], reverse=True)
    w_kw, w_vec = _fusion_weights(query)
    if not kw_results:
        w_kw = 0.0
    if not vec_ranked:
        w_vec = 0.0
    max_fused = (w_kw + w_vec or 1.0) / (RRF_K + 1)
    penalize_secondary = not _SECONDARY_QUERY_RE.search(query)

    fused: Dict[tuple, Dict[str, Any]] = {}
    for rank, item in enumerate(kw_results, start=1):
        fused[_key(item)] = {**item, "keyword_score": item["score"], "_rrf": w_kw / (RRF_K + rank), "match": "keyword"}
    for rank, item in enumerate(vec_ranked, start=1):
        k = _key(item)
        if k in fused:
            entry = fused[k]
            entry.update({kk: item[kk] for kk in ("similarity", "start_line", "end_line", "snippet")})
            entry["context"] = item["context"]
            entry["_rrf"] += w_vec / (RRF_K + rank)
            entry["match"] = "hybrid"
        else:
            fused[k] = {**item, "_rrf": w_vec / (RRF_K + rank), "match": "semantic"}

    if penalize_secondary:
        # Tests / examples / docs are useful, but rarely what an explorer is looking for first.
        for entry in fused.values():
            if _SECONDARY_PATH_RE.search(entry["file_path"].lower()):
                entry["_rrf"] *= 0.75

    results = sorted(fused.values(), key=lambda x: (x["_rrf"], x.get("similarity") or 0), reverse=True)[:limit]
    for r in results:
        # 100 = ranked first by every active retriever
        r["score"] = round(100 * r.pop("_rrf") / max_fused, 1)

    grouped = defaultdict(list)
    for r in results:
        grouped[r["type"]].append(r)

    return {
        "query": query,
        "total_results": len(results),
        "results": results,
        "grouped": {t: grouped[t] for t in TYPE_ORDER if t in grouped},
        "mode": "hybrid" if (use_vectors and use_keywords) else ("semantic" if use_vectors else "keyword"),
        "index": vector_index.info() if vector_index is not None else None,
    }


def search_with_ai_ranking(query: str, analysis_data: Dict, groq_client=None) -> Dict[str, Any]:
    """Backward-compatible entry point (keyword only)."""
    return hybrid_search(query, files_from_analysis_data(analysis_data), None, mode="keyword")
