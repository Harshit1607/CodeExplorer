import re
from typing import List, Dict, Any
from collections import defaultdict

# Common programming terms and their related concepts
CONCEPT_SYNONYMS = {
    # Authentication
    "auth": ["authentication", "login", "logout", "signin", "signout", "session", "jwt", "token", "oauth", "password", "credential"],
    "authentication": ["auth", "login", "logout", "signin", "signout", "session", "jwt", "token", "oauth", "password", "credential"],
    "login": ["auth", "authentication", "signin", "session", "credential"],

    # API & Network
    "api": ["endpoint", "route", "controller", "handler", "request", "response", "rest", "graphql"],
    "fetch": ["request", "http", "api", "get", "post", "axios", "ajax"],
    "request": ["fetch", "http", "api", "get", "post", "axios"],

    # Database
    "database": ["db", "sql", "query", "model", "schema", "migration", "repository", "orm"],
    "db": ["database", "sql", "query", "model", "schema", "migration", "repository"],
    "model": ["schema", "entity", "database", "orm", "table"],

    # UI/Frontend
    "component": ["widget", "element", "view", "ui", "render"],
    "ui": ["component", "view", "frontend", "interface", "layout", "style"],
    "style": ["css", "scss", "sass", "tailwind", "styled", "theme"],

    # State Management
    "state": ["store", "redux", "context", "provider", "reducer", "action"],
    "store": ["state", "redux", "context", "provider"],

    # Testing
    "test": ["spec", "testing", "jest", "mocha", "pytest", "unittest", "assert"],
    "spec": ["test", "testing", "describe", "it", "expect"],

    # Error Handling
    "error": ["exception", "catch", "throw", "try", "handle", "failure"],
    "exception": ["error", "catch", "throw", "try", "handle"],

    # Configuration
    "config": ["configuration", "settings", "env", "environment", "options"],
    "settings": ["config", "configuration", "options", "preferences"],

    # Utilities
    "util": ["utility", "helper", "utils", "common", "shared"],
    "helper": ["util", "utility", "utils", "common"],

    # Validation
    "validate": ["validation", "validator", "check", "verify", "sanitize"],
    "validation": ["validate", "validator", "check", "verify", "schema"],
}

def expand_query(query: str) -> List[str]:
    """Expand query with synonyms and related terms."""
    words = re.findall(r'\w+', query.lower())
    expanded = set(words)

    for word in words:
        if word in CONCEPT_SYNONYMS:
            expanded.update(CONCEPT_SYNONYMS[word])

    return list(expanded)

def calculate_relevance_score(item: Dict, query_terms: List[str], expanded_terms: List[str]) -> float:
    """Calculate relevance score for a search item."""
    score = 0.0

    name = item.get("name", "").lower()
    file_path = item.get("file_path", "").lower()
    item_type = item.get("type", "")
    context = item.get("context", "").lower()

    # Combine all searchable text
    searchable = f"{name} {file_path} {context}"

    # Exact match in name (highest weight)
    for term in query_terms:
        if term in name:
            score += 10.0
            if name == term or name.startswith(term) or name.endswith(term):
                score += 5.0

    # Match in file path
    for term in query_terms:
        if term in file_path:
            score += 3.0

    # Expanded term matches (lower weight)
    for term in expanded_terms:
        if term not in query_terms and term in searchable:
            score += 1.5

    # Boost by type relevance
    type_boost = {
        "file": 1.2,
        "function": 1.5,
        "class": 1.4,
        "import": 0.8,
    }
    score *= type_boost.get(item_type, 1.0)

    return score

def semantic_search(query: str, analysis_data: Dict, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Perform semantic search on the analyzed repository data.

    Uses keyword expansion and fuzzy matching to find relevant code elements.
    """
    if not query.strip():
        return []

    structure = analysis_data.get("structure_analysis", {})
    files = structure.get("files", {})

    # Build search index
    search_index = []

    for file_path, info in files.items():
        # Normalize path
        normalized_path = file_path.replace("\\", "/")
        file_name = normalized_path.split("/")[-1]

        # Add file
        search_index.append({
            "type": "file",
            "name": file_name,
            "file_path": normalized_path,
            "context": normalized_path,
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

        # Add imports (lower priority)
        for imp in info.get("imports", []):
            search_index.append({
                "type": "import",
                "name": imp,
                "file_path": normalized_path,
                "context": f"imported in {file_name}",
            })

    # Parse and expand query
    query_terms = re.findall(r'\w+', query.lower())
    expanded_terms = expand_query(query)

    # Score all items
    scored_results = []
    for item in search_index:
        score = calculate_relevance_score(item, query_terms, expanded_terms)
        if score > 0:
            scored_results.append({
                **item,
                "score": score,
            })

    # Sort by score and limit
    scored_results.sort(key=lambda x: x["score"], reverse=True)

    return scored_results[:limit]

def search_with_ai_ranking(query: str, analysis_data: Dict, groq_client=None) -> Dict[str, Any]:
    """
    Perform semantic search and optionally use AI to explain results.

    Returns search results with optional AI-generated summary.
    """
    results = semantic_search(query, analysis_data, limit=20)

    # Group results by type
    grouped = defaultdict(list)
    for result in results:
        grouped[result["type"]].append(result)

    return {
        "query": query,
        "total_results": len(results),
        "results": results,
        "grouped": dict(grouped),
    }
