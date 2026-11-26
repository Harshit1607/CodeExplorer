"""
Docs and config files for the chunk index (chat, search and the AI report).

Source files answer "how does X work?"; these answer "how do I install / configure / run the
tests / deploy?". They are chunked alongside the code, each chunk tagged `docs` or `config`:

  docs    README*, CONTRIBUTING*, root guides (SETUP.md, DEPLOYMENT.md, ...), docs/**/*.md|rst|txt
  config  Dockerfile*, compose*.yml, CI workflows (.github/workflows, GitLab, CircleCI, ...),
          .env.example-style templates, Makefile

Never `.env` itself: only templates, which are meant to be committed.
The total is bounded (config.DOC_INDEX_MAX_FILES / DOC_INDEX_MAX_CHUNKS), most useful files first,
so a large docs/ tree cannot crowd code out of the index.
"""
import os
import re
from typing import Callable, List, Optional, Tuple

from app.core import config
from app.services.code_chunker import CodeChunk
from app.services.fs_utils import inside_repo, read_repo_text

MAX_DOC_FILE_BYTES = 200_000
MAX_CHUNKS_PER_DOC_FILE = 40
MAX_DOC_CHUNK_LINES = 60
MAX_DOC_CHUNK_CHARS = 1500       # prose lines are long; keep chunks close to what gets embedded

_DOC_EXT = r"(?:md|mdx|markdown|rst|txt)"
_README_RE = re.compile(rf"^readme(?:\.{_DOC_EXT})?$", re.I)
_CONTRIBUTING_RE = re.compile(rf"^contributing(?:\.{_DOC_EXT})?$", re.I)
_ROOT_GUIDE_RE = re.compile(
    rf"^(?:setup|install|installation|deploy|deployment|development|developing|hacking|building|"
    rf"running|testing|getting[-_]started|quickstart)\.{_DOC_EXT}$", re.I)
_DOCS_DIR_RE = re.compile(r"(^|/)docs?/", re.I)
_DOCS_PAGE_RE = re.compile(rf"\.{_DOC_EXT}$", re.I)
_NOT_A_DOC_RE = re.compile(r"^(requirements.*|constraints.*|robots|license|licence|copying|notice)\.txt$", re.I)

_DOCKERFILE_RE = re.compile(r"^(?:dockerfile|containerfile)(?:[.-][\w.-]+)?$|\.dockerfile$", re.I)
_COMPOSE_RE = re.compile(r"^(?:docker-)?compose(?:[.-][\w.-]+)?\.ya?ml$", re.I)
_ENV_TEMPLATE_RE = re.compile(r"^(?:\.env(?:\.[\w-]+)*\.(?:example|sample|template|dist)|env\.(?:example|sample)|example\.env)$", re.I)
_MAKEFILE_RE = re.compile(r"^(?:gnu)?makefile$", re.I)
_CI_PATH_RE = re.compile(
    r"(^|/)\.github/workflows/[^/]+\.ya?ml$|^\.gitlab-ci\.ya?ml$|^\.circleci/config\.ya?ml$|"
    r"^azure-pipelines\.ya?ml$|^\.travis\.ya?ml$|^bitbucket-pipelines\.ya?ml$|^jenkinsfile$", re.I)

_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
_UNDERLINE_RE = re.compile(r"^\s*([=\-~^*+#`:'\"])\1{2,}\s*$")
_FENCE_RE = re.compile(r"^\s{0,3}(```|~~~)")


def classify_doc_path(rel_path: str) -> Optional[Tuple[str, int]]:
    """(tag, rank) for a docs/config file worth indexing, else None. Lower rank = more useful."""
    path = rel_path.replace("\\", "/")
    name = path.rsplit("/", 1)[-1]
    root = "/" not in path
    if _CI_PATH_RE.search(path):
        return "config", 2
    if _README_RE.match(name):
        return "docs", 0 if root else 3
    if _CONTRIBUTING_RE.match(name):
        return "docs", 1 if root else 3
    if root and _ROOT_GUIDE_RE.match(name):
        return "docs", 1
    if _DOCKERFILE_RE.search(name) or _COMPOSE_RE.match(name) or _ENV_TEMPLATE_RE.match(name) \
            or _MAKEFILE_RE.match(name):
        return "config", 2 if root else 3
    if _DOCS_DIR_RE.search(path) and _DOCS_PAGE_RE.search(name) and not _NOT_A_DOC_RE.match(name):
        return "docs", 4
    return None


def _language(rel_path: str, tag: str) -> str:
    name = rel_path.rsplit("/", 1)[-1].lower()
    if name.endswith((".yml", ".yaml")):
        return "YAML"
    if _DOCKERFILE_RE.search(name):
        return "Dockerfile"
    if _MAKEFILE_RE.match(name):
        return "Makefile"
    if name == "jenkinsfile":
        return "Groovy"
    if _ENV_TEMPLATE_RE.match(name):
        return "Env"
    if name.endswith(".rst"):
        return "reStructuredText"
    if name.endswith(".txt"):
        return "Text"
    return "Markdown" if tag == "docs" else "Text"


def _heading_sections(lines: List[str]) -> List[Tuple[int, int, Optional[str], str]]:
    """Split prose at headings: `# Title` (Markdown) or a title underlined with ===/--- (setext, reST)."""
    starts: List[Tuple[int, str]] = []
    in_fence = False
    for i, line in enumerate(lines, start=1):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _HEADING_RE.match(line)
        if m:
            starts.append((i, m.group(1)))
        elif i > 1 and _UNDERLINE_RE.match(line) and lines[i - 2].strip() and not _UNDERLINE_RE.match(lines[i - 2]) \
                and not (starts and starts[-1][0] == i - 1):
            starts.append((i - 1, lines[i - 2].strip()))

    if not starts:
        return [(1, len(lines), None, "section")]
    segments = []
    if starts[0][0] > 1:
        segments.append((1, starts[0][0] - 1, None, "section"))
    for idx, (line_no, title) in enumerate(starts):
        end = starts[idx + 1][0] - 1 if idx + 1 < len(starts) else len(lines)
        segments.append((line_no, end, title.strip("*_` ")[:80] or None, "section"))
    return segments


def _merge_heading_only(segments, lines: List[str]):
    """A section that is only a heading (`# Project` straight before `## Install`) joins the next one."""
    merged, pending = [], None
    for start, end, title, kind in segments:
        if pending is not None:
            start, pending = pending, None
        if sum(1 for ln in lines[start - 1:end] if ln.strip()) <= 1:
            pending = start
            continue
        merged.append((start, end, title, kind))
    if pending is not None:
        if merged:
            merged[-1] = (merged[-1][0], len(lines), merged[-1][2], merged[-1][3])
        else:
            merged.append((pending, len(lines), None, "section"))
    return merged


def _windows(lines: List[str], start: int, end: int):
    """Split [start, end] into windows of at most MAX_DOC_CHUNK_LINES lines / MAX_DOC_CHUNK_CHARS chars."""
    w_start, chars = start, 0
    for i in range(start, end + 1):
        size = len(lines[i - 1]) + 1
        if i > w_start and (i - w_start >= MAX_DOC_CHUNK_LINES or chars + size > MAX_DOC_CHUNK_CHARS):
            yield w_start, i - 1
            w_start, chars = i, 0
        chars += size
    yield w_start, end


def chunk_doc(rel_path: str, content: str, tag: str) -> List[CodeChunk]:
    """Chunk one docs/config file. Docs split at headings (the heading is the chunk's symbol)."""
    if not content or len(content) > MAX_DOC_FILE_BYTES:
        return []
    lines = content.splitlines()
    if not lines:
        return []
    language = _language(rel_path, tag)
    if tag == "docs":
        segments = _merge_heading_only(_heading_sections(lines), lines)
    else:
        segments = [(1, len(lines), None, "config")]

    chunks: List[CodeChunk] = []
    for start, end, symbol, kind in segments:
        for w_start, w_end in _windows(lines, start, end):
            text = "\n".join(lines[w_start - 1:w_end])
            if not text.strip():
                continue
            chunks.append(CodeChunk(id=f"{rel_path}:{w_start}-{w_end}", file=rel_path, language=language,
                                    symbol=symbol, kind=kind, start_line=w_start, end_line=w_end,
                                    code=text, tag=tag))
            if len(chunks) >= MAX_CHUNKS_PER_DOC_FILE:
                return chunks
    return chunks


def find_doc_files(repo_path: str, keep_dir: Optional[Callable[[str], bool]] = None) -> List[Tuple[str, str]]:
    """[(relative path, tag)] most useful first. Skips symlinks that lead outside the repository."""
    found = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = sorted(d for d in dirs if keep_dir is None or keep_dir(d))
        rel_root = os.path.relpath(root, repo_path).replace("\\", "/")
        for name in files:
            rel = name if rel_root == "." else f"{rel_root}/{name}"
            hit = classify_doc_path(rel)
            if hit and inside_repo(repo_path, rel):
                found.append((hit[1], rel.count("/"), rel, hit[0]))
    found.sort()
    return [(rel, tag) for _, _, rel, tag in found]


def collect_doc_chunks(repo_path: str, keep_dir: Optional[Callable[[str], bool]] = None,
                       max_files: Optional[int] = None, max_chunks: Optional[int] = None) -> List[CodeChunk]:
    """Chunks for the repository's docs/config files, within the configured budget."""
    max_files = config.DOC_INDEX_MAX_FILES if max_files is None else max_files
    max_chunks = config.DOC_INDEX_MAX_CHUNKS if max_chunks is None else max_chunks
    chunks: List[CodeChunk] = []
    used_files = 0
    for rel, tag in find_doc_files(repo_path, keep_dir):
        if used_files >= max_files or len(chunks) >= max_chunks:
            break
        content = read_repo_text(repo_path, rel)
        file_chunks = chunk_doc(rel, content or "", tag)
        if not file_chunks:
            continue
        chunks.extend(file_chunks[:max_chunks - len(chunks)])
        used_files += 1
    return chunks

