"""
Repository chat.

Context = compact repo overview + code relevant to the question.
  - With a live session and vector index: retrieval-augmented (RAG) — the most relevant
    functions/classes are selected via embeddings, symbol and file mentions.
  - Otherwise: falls back to whole files (entry points / key files / mentioned files),
    read from server memory when possible, else fetched from GitHub.
"""
import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

import requests
from fastapi import HTTPException
from groq import Groq

from app.core import config
from app.services.llm import completion_kwargs, groq_api_key
from app.services.rag_retriever import RepoRetriever

OVERVIEW_MAX_CHARS = 4500
README_MAX_CHARS = 1500
MAX_FALLBACK_FILES = 4
HISTORY_MESSAGE_MAX_CHARS = 2000

# Kept for backwards compatibility with older imports.
MAX_CONTEXT_CHARS = config.CHAT_CONTEXT_CHARS


def get_groq_client():
    api_key = groq_api_key()
    if not api_key:
        raise HTTPException(status_code=500, detail="Chat feature is not configured. GROQ_API_KEY is missing.")
    return Groq(api_key=api_key)


# ---------------------------------------------------------------------------
# Normalised repo info (from a live session or from client-supplied data)
# ---------------------------------------------------------------------------
def _readme_text(readme) -> str:
    if isinstance(readme, dict):
        return readme.get("content", "") or ""
    return readme or ""


def _split_frameworks(frameworks) -> Tuple[List[str], List[str]]:
    if isinstance(frameworks, dict):
        return frameworks.get("frontend", []) or [], frameworks.get("backend", []) or []
    return [], []


def info_from_pipeline(pipeline) -> dict:
    r = pipeline.results
    frontend, backend = _split_frameworks(r.get("frameworks"))
    return {
        "repo_url": pipeline.repo_url,
        "default_branch": pipeline.repo_meta.get("default_branch") or "main",
        "description": pipeline.repo_meta.get("description"),
        "readme": _readme_text((r.get("quickstart") or {}).get("readme")),
        "languages": r.get("languages") or {},
        "frontend": frontend,
        "backend": backend,
        "databases": r.get("databases") or [],
        "dependencies": r.get("dependencies") or {},
        "entry_points": r.get("entry_points") or [],
        "key_files": r.get("key_files") or [],
        "files": pipeline.analyzer.files,   # includes truncated `content`
    }


def normalize_analysis(analysis_data: dict) -> dict:
    if not analysis_data:
        return {}
    if "repoMeta" in analysis_data or "complexity" in analysis_data:
        meta = analysis_data.get("repoMeta") or {}
        frontend, backend = _split_frameworks(analysis_data.get("frameworks"))
        return {
            "repo_url": meta.get("url", "Unknown"),
            "default_branch": meta.get("default_branch") or "main",
            "description": meta.get("description"),
            "readme": _readme_text((analysis_data.get("quickstart") or {}).get("readme")),
            "languages": analysis_data.get("languages") or {},
            "frontend": frontend,
            "backend": backend,
            "databases": analysis_data.get("databases") or [],
            "dependencies": analysis_data.get("dependencies") or {},
            "entry_points": analysis_data.get("entryPoints") or [],
            "key_files": analysis_data.get("keyFiles") or [],
            "files": {
                f["file"]: {"functions": f.get("functions", []), "classes": f.get("classes", []),
                            "language": f.get("language", "")}
                for f in (analysis_data.get("complexity") or {}).get("fileList", []) if f.get("file")
            },
        }
    structure = analysis_data.get("structure_analysis", {})
    frontend, backend = _split_frameworks(structure.get("frameworks"))
    return {
        "repo_url": analysis_data.get("repository_url", "Unknown"),
        "default_branch": "main",
        "readme": _readme_text(structure.get("readme")),
        "languages": structure.get("languages", {}),
        "frontend": frontend,
        "backend": backend,
        "databases": structure.get("databases", []),
        "dependencies": structure.get("dependencies", {}),
        "entry_points": structure.get("entry_points", []),
        "key_files": structure.get("key_files", []),
        "files": structure.get("files", {}),
    }


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------
def _clean_readme(text: str) -> str:
    lines = [ln for ln in text.splitlines()
             if not ln.lstrip().startswith(("[![", "<img", "<p", "</p", "<a ", "</a", "<div", "</div", "<br"))]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _directory_summary(files: Dict[str, dict], max_lines: int = 25) -> List[str]:
    counts: Counter = Counter()
    for path in files:
        parts = path.split("/")
        counts["/".join(parts[:2]) + "/" if len(parts) > 2 else (parts[0] + "/" if len(parts) > 1 else "(root)")] += 1
    return [f"- {d} ({n} files)" for d, n in counts.most_common(max_lines)]


def build_overview(info: dict) -> str:
    parts = [f"# Repository: {info.get('repo_url', 'Unknown')}"]
    if info.get("description"):
        parts.append(info["description"])

    readme = _clean_readme(info.get("readme") or "")
    if readme:
        parts.append(f"## README (excerpt)\n{readme[:README_MAX_CHARS]}")

    langs = info.get("languages") or {}
    if langs:
        top = sorted(langs.items(), key=lambda kv: (kv[1] or {}).get("count", 0), reverse=True)[:6]
        parts.append("**Languages:** " + ", ".join(f"{k} ({(v or {}).get('count', 0)} files)" for k, v in top))
    if info.get("frontend"):
        parts.append(f"**Frontend:** {', '.join(info['frontend'])}")
    if info.get("backend"):
        parts.append(f"**Backend:** {', '.join(info['backend'])}")
    if info.get("databases"):
        parts.append(f"**Databases:** {', '.join(info['databases'])}")

    deps = info.get("dependencies") or {}
    dep_lines = []
    for _, sources in deps.items():
        if isinstance(sources, dict):
            for source, dep_list in sources.items():
                if dep_list:
                    dep_lines.append(f"- {source}: {', '.join(dep_list[:15])}")
    if dep_lines:
        parts.append("## Dependencies\n" + "\n".join(dep_lines[:8]))

    if info.get("entry_points"):
        parts.append("**Entry points:** " + ", ".join(info["entry_points"][:8]))
    if info.get("key_files"):
        parts.append("**Key files:** " + ", ".join(info["key_files"][:10]))

    files = info.get("files") or {}
    if files:
        parts.append(f"## Layout ({len(files)} source files)\n" + "\n".join(_directory_summary(files)))

    return "\n".join(parts)[:OVERVIEW_MAX_CHARS]


# ---------------------------------------------------------------------------
# Fallback code context (no vector index)
# ---------------------------------------------------------------------------
def extract_mentioned_files(question: str, available_files: List[str]) -> List[str]:
    q = question.lower()
    out = []
    for path in available_files:
        name = path.split("/")[-1].lower()
        stem = name.rsplit(".", 1)[0]
        if name in q or (len(stem) >= 4 and re.search(rf"\b{re.escape(stem)}\b", q)):
            out.append(path)
    return out


def prioritize_files(files: dict, key_files: List[str], entry_points: List[str], mentioned: List[str]) -> List[str]:
    order, seen = [], set()
    for group in (mentioned, entry_points, key_files):
        for f in group:
            if f in files and f not in seen:
                order.append(f)
                seen.add(f)
    rest = sorted((p for p in files if p not in seen),
                  key=lambda p: len(files[p].get("functions", [])) + 2 * len(files[p].get("classes", [])),
                  reverse=True)
    return order + rest


def fetch_file_content(repo_url: str, default_branch: str, file_path: str) -> str:
    if not repo_url or not repo_url.startswith("https://github.com/"):
        return ""
    parts = repo_url.rstrip("/").split("/")
    owner, repo = parts[-2], parts[-1].removesuffix(".git")
    try:
        resp = requests.get(f"https://raw.githubusercontent.com/{owner}/{repo}/{default_branch or 'main'}/{file_path}", timeout=5.0)
        if resp.status_code == 200:
            return resp.text
    except Exception as e:
        print(f"Failed to fetch {file_path}: {e}")
    return ""


def build_fallback_code(info: dict, question: str, budget: int) -> Tuple[str, List[dict]]:
    files = info.get("files") or {}
    mentioned = extract_mentioned_files(question, list(files))
    out, sources, used = [], [], 0
    for path in prioritize_files(files, info.get("key_files", []), info.get("entry_points", []), mentioned):
        if len(sources) >= MAX_FALLBACK_FILES or budget - used < 600:
            break
        content = files[path].get("content") or fetch_file_content(info.get("repo_url"), info.get("default_branch"), path)
        if not content:
            continue
        room = budget - used - 100
        if len(content) > room:
            content = content[:room] + "\n... [truncated]"
        block = f"### {path}\n```\n{content}\n```\n"
        out.append(block)
        used += len(block)
        sources.append({"file": path, "start_line": 1, "end_line": content.count("\n") + 1,
                        "symbol": None, "reason": "file"})
    return "\n".join(out), sources


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------
def build_chat_context(question: str, history: Optional[List[dict]], analysis_data: Optional[dict],
                       pipeline=None) -> Tuple[str, List[dict], str]:
    """Returns (context, sources, retrieval_mode)."""
    info = info_from_pipeline(pipeline) if pipeline else normalize_analysis(analysis_data or {})
    if not info or not info.get("files"):
        # Without real repository data the model would answer from memory and invent code.
        raise HTTPException(status_code=400, detail="No analyzed source files are available for this repository yet. "
                                                    "Wait for the analysis to finish (or re-run it) and try again.")

    overview = build_overview(info)
    code_budget = max(2000, config.CHAT_CONTEXT_CHARS - len(overview))

    retriever = RepoRetriever(pipeline.vector_index, pipeline.results.get("call_graph"), pipeline.analyzer.files) if pipeline else None
    if retriever and retriever.available:
        code, sources = retriever.retrieve(question, history, code_budget)
        mode = "semantic"
    else:
        code, sources = build_fallback_code(info, question, code_budget)
        mode = "files"

    context = overview
    if code:
        heading = ("## Relevant code (retrieved for this question; excerpts, not whole files)"
                   if mode == "semantic" else "## Source code (selected files)")
        context += f"\n\n{heading}\n\n{code}"
    return context, sources, mode


def build_context(analysis_data: dict, question: str = "", max_code_files: int = MAX_FALLBACK_FILES) -> str:
    """Backward-compatible helper (no session)."""
    return build_chat_context(question, None, analysis_data)[0]


SYSTEM_PROMPT = """You are an expert code analyst helping a developer understand a GitHub repository.

{context}

## How to answer
- Ground every claim in the overview and code above. Cite locations as `path:line` (line numbers are given in each excerpt header).
- Only quote code that appears above, verbatim. Never invent, reconstruct or "simplify" code and present it as the repository's code. If you must sketch something, label it clearly as illustrative.
- Quote short code snippets when they make the explanation clearer.
- Explain how pieces connect (callers/callees are listed under excerpt headers when known).
- The code shown was selected for this question and may be partial. If something you need is not shown, say which file or symbol is missing instead of guessing; the user can ask about it by name.
- Be concise and use Markdown."""


def chat_about_repo(question: str, analysis_data: Optional[dict], chat_history: Optional[list] = None,
                    pipeline=None) -> dict:
    client = get_groq_client()
    history = (chat_history or [])[-config.CHAT_HISTORY_MESSAGES:]
    context, sources, mode = build_chat_context(question, history, analysis_data, pipeline)

    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(context=context)}]
    for msg in history:
        messages.append({"role": msg.get("role", "user"), "content": (msg.get("content") or "")[:HISTORY_MESSAGE_MAX_CHARS]})
    messages.append({"role": "user", "content": question})

    try:
        response = client.chat.completions.create(messages=messages, **completion_kwargs(config.CHAT_MAX_TOKENS, 0.3))
        answer = (response.choices[0].message.content or "").strip()
        if not answer:
            raise HTTPException(status_code=503, detail="The AI returned an empty answer. Please try again.")
        return {"response": answer, "sources": sources, "retrieval": mode}
    except HTTPException:
        raise
    except Exception as e:
        raise _map_llm_error(e)


def _map_llm_error(e: Exception) -> HTTPException:
    error_msg = str(e)
    low = error_msg.lower()
    print(f"Chat API Error: {error_msg}")
    status = getattr(e, "status_code", None)

    if status == 413 or "request too large" in low or "reduce your message size" in low:
        return HTTPException(400, "The question context is too large for the AI's rate limit. Try a more specific question.")
    if status == 429 or "rate_limit" in low:
        # Upstream (Groq) quota is shared by every user of this server; pass its back-off through.
        retry_after = None
        try:
            retry_after = int(float(e.response.headers.get("retry-after")))  # type: ignore[attr-defined]
        except Exception:
            pass
        headers = {"Retry-After": str(max(1, retry_after))} if retry_after else None
        wait = f" Please try again in {retry_after}s." if retry_after else " Please wait a moment and try again."
        return HTTPException(429, "The AI service's rate limit was reached." + wait, headers=headers)
    if status == 401 or "invalid_api_key" in low or "invalid api key" in low:
        return HTTPException(401, "AI service authentication failed. Please check the API key.")
    if "model_not_found" in low or "does not exist" in low:
        return HTTPException(503, f"AI model '{config.GROQ_MODEL}' is unavailable. Set GROQ_MODEL to a model your key can access.")
    if "context_length_exceeded" in low or "maximum context length" in low:
        return HTTPException(400, "The question context is too long. Try asking about specific files.")
    if status == 503 or "service unavailable" in low:
        return HTTPException(503, "AI service is temporarily unavailable. Please try again later.")
    return HTTPException(500, f"Chat failed: {error_msg[:200]}")
