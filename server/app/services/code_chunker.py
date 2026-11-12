"""
Split source files into symbol-level chunks for embedding.

Python files are chunked with the `ast` module (exact function / class / method
boundaries). Every other language uses line-anchored definition regexes as split
points, which works well enough for JS/TS, Java, Go, Rust, C#, Kotlin, Ruby, PHP, etc.
Oversized segments are split into overlapping line windows.
"""
import ast
import re
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple

MAX_CHUNK_LINES = 80        # split segments larger than this
WINDOW_OVERLAP = 10         # overlap between windows of an oversized segment
MIN_CHUNK_LINES = 4         # merge tiny segments (non-blank lines) into the next one
MAX_EMBED_CHARS = 1000      # ~250 code tokens: faster and (measured) no worse than 1800
MAX_FILE_BYTES = 400_000    # skip giant / generated files
MAX_AVG_LINE_LEN = 250      # skip minified files


@dataclass
class CodeChunk:
    id: str
    file: str
    language: str
    symbol: Optional[str]     # e.g. "login", "AuthService", "AuthService.login"
    kind: str                 # function | method | class | module
    start_line: int           # 1-based, inclusive
    end_line: int             # 1-based, inclusive
    code: str

    def embedding_text(self) -> str:
        """Code plus a short header; the path and symbol carry a lot of meaning."""
        header = f"File: {self.file}\n"
        if self.symbol:
            header += f"{self.kind.capitalize()}: {self.symbol}\n"
        return (header + self.code)[:MAX_EMBED_CHARS]

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------
# Generic (regex) definition detection
# --------------------------------------------------------------------------
_CONTROL_WORDS = {
    "if", "for", "while", "switch", "catch", "return", "else", "do", "try",
    "new", "throw", "sizeof", "typeof", "await", "yield", "elif", "with",
}

# (regex, kind). The first capturing group that matched is the symbol name.
_DEF_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # class-like: class/interface/struct/enum/trait/impl/object/record/module/type
    (re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:(?:public|private|protected|internal|abstract|final|sealed|static|data|open|pub(?:\([^)]*\))?)\s+)*"
                r"(?:class|interface|struct|enum|trait|impl|object|record|module)\s+([A-Za-z_]\w*)"), "class"),
    (re.compile(r"^\s*(?:export\s+)?type\s+([A-Za-z_]\w*)\s*(?:<[^>]*>)?\s*="), "class"),
    # JS/TS/PHP: function foo(
    (re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:(?:public|private|protected|static|final|abstract)\s+)*(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*[<(]"), "function"),
    # JS/TS: const foo = (...) => / const foo = async x => / const foo = function
    (re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(?:async\s+)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*(?::[^=]+)?=>"), "function"),
    (re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?function\b"), "function"),
    # React: const handleX = useCallback(...) / useMemo(...)
    (re.compile(r"^\s*(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:React\.)?(?:useCallback|useMemo)\s*\("), "function"),
    # Python / Ruby / Scala: def foo
    (re.compile(r"^\s*(?:async\s+)?def\s+(?:self\.)?([A-Za-z_]\w*[?!]?)"), "function"),
    # Go / Swift: func (r *T) Foo(   |   func foo(
    (re.compile(r"^\s*(?:(?:public|private|internal|fileprivate|open|static|override|mutating)\s+)*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)"), "function"),
    # Kotlin: fun foo(
    (re.compile(r"^\s*(?:(?:public|private|protected|internal|override|suspend|inline|open|abstract)\s+)*fun\s+(?:<[^>]*>\s*)?(?:[\w.]+\.)?([A-Za-z_]\w*)\s*\("), "function"),
    # Rust: fn foo
    (re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:const\s+)?(?:async\s+)?(?:unsafe\s+)?(?:extern\s+\"[^\"]*\"\s+)?fn\s+([A-Za-z_]\w*)"), "function"),
    # Java / C# / C++ methods with modifiers: public static Foo<Bar> name(
    (re.compile(r"^\s*(?:@\w+\s+)*(?:(?:public|private|protected|internal|static|final|abstract|override|virtual|async|synchronized|inline|extern|unsafe|sealed)\s+)+"
                r"[\w<>\[\]?,.*&:\s]+?\s+[*&]?([A-Za-z_]\w*)\s*\([^;]*$"), "function"),
    # TS/JS class methods: `  async foo(a, b) {`   (indented, ends with "{")
    (re.compile(r"^\s+(?:(?:public|private|protected|static|readonly|override|async|get|set)\s+)*([A-Za-z_$][\w$]*)\s*\([^;]*\)\s*(?::\s*[^{;]+)?\{\s*$"), "method"),
    # C / C++ top-level functions: `int foo(...)` at column 0, not a declaration
    (re.compile(r"^[A-Za-z_][\w\s*&:<>,]*?\s+[*&]?([A-Za-z_]\w*)\s*\([^;]*$"), "function"),
]


def _match_definition(line: str) -> Optional[Tuple[str, str]]:
    stripped = line.strip()
    if not stripped or stripped.startswith(("//", "#", "*", "/*", "--")):
        return None
    for pattern, kind in _DEF_PATTERNS:
        m = pattern.match(line)
        if m:
            name = next((g for g in m.groups() if g), None)
            if name and name not in _CONTROL_WORDS:
                return name, kind
    return None


def _nonblank(lines: List[str]) -> int:
    return sum(1 for ln in lines if ln.strip())


# --------------------------------------------------------------------------
# Chunker
# --------------------------------------------------------------------------
class CodeChunker:
    def chunk_file(self, rel_path: str, content: str, language: str) -> List[CodeChunk]:
        if not content or len(content) > MAX_FILE_BYTES:
            return []
        lines = content.splitlines()
        if not lines:
            return []
        if len(content) / max(len(lines), 1) > MAX_AVG_LINE_LEN:
            return []  # minified / generated

        segments: Optional[List[Tuple[int, int, Optional[str], str]]] = None
        if rel_path.endswith(".py"):
            segments = self._python_segments(content, len(lines))
        if segments is None:
            segments = self._regex_segments(lines)

        segments = self._merge_small(segments, lines)

        chunks: List[CodeChunk] = []
        for start, end, symbol, kind in segments:
            for w_start, w_end in self._windows(start, end):
                code = "\n".join(lines[w_start - 1:w_end])
                if not code.strip():
                    continue
                chunks.append(CodeChunk(
                    id=f"{rel_path}:{w_start}-{w_end}",
                    file=rel_path,
                    language=language,
                    symbol=symbol,
                    kind=kind,
                    start_line=w_start,
                    end_line=w_end,
                    code=code,
                ))
        return chunks

    # ---- Python: exact boundaries via AST ----------------------------------
    def _python_segments(self, content: str, n_lines: int):
        try:
            tree = ast.parse(content)
        except (SyntaxError, ValueError):
            return None

        defs: List[Tuple[int, int, str, str]] = []

        def visit(body, parent: Optional[str]):
            for node in body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    start = min([d.lineno for d in node.decorator_list] + [node.lineno])
                    end = getattr(node, "end_lineno", None) or start
                    name = f"{parent}.{node.name}" if parent else node.name
                    if isinstance(node, ast.ClassDef):
                        methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                        if end - start + 1 > MAX_CHUNK_LINES and methods:
                            # Large class: header chunk + one chunk per method
                            first_method = min(min([d.lineno for d in m.decorator_list] + [m.lineno]) for m in methods)
                            defs.append((start, first_method - 1, name, "class"))
                            visit(node.body, name)
                        else:
                            defs.append((start, end, name, "class"))
                    else:
                        defs.append((start, end, name, "method" if parent else "function"))

        visit(tree.body, None)
        defs.sort()
        return self._fill_gaps(defs, n_lines)

    # ---- Other languages: regex split points -------------------------------
    def _regex_segments(self, lines: List[str]):
        starts: List[Tuple[int, str, str]] = []
        for i, line in enumerate(lines, start=1):
            found = _match_definition(line)
            if found:
                starts.append((i, found[0], found[1]))

        if not starts:
            return [(1, len(lines), None, "module")]

        segments = []
        if starts[0][0] > 1:
            segments.append((1, starts[0][0] - 1, None, "module"))
        for idx, (line_no, name, kind) in enumerate(starts):
            end = starts[idx + 1][0] - 1 if idx + 1 < len(starts) else len(lines)
            segments.append((line_no, end, name, kind))
        return segments

    # ---- helpers -----------------------------------------------------------
    @staticmethod
    def _fill_gaps(defs, n_lines):
        """Turn a sorted list of (possibly nested-free) definitions into full coverage."""
        segments = []
        cursor = 1
        for start, end, name, kind in defs:
            if end < cursor:
                continue
            start = max(start, cursor)
            if start > cursor:
                segments.append((cursor, start - 1, None, "module"))
            segments.append((start, end, name, kind))
            cursor = end + 1
        if cursor <= n_lines:
            segments.append((cursor, n_lines, None, "module"))
        return segments

    @staticmethod
    def _merge_small(segments, lines):
        """Merge segments with too little code into their neighbour."""
        merged = []
        pending = None
        for seg in segments:
            if pending:
                start, _, p_sym, p_kind = pending
                _, end, sym, kind = seg
                # Prefer the named / larger segment's identity
                seg = (start, end, sym or p_sym, kind if sym else p_kind)
                pending = None
            start, end, sym, kind = seg
            if _nonblank(lines[start - 1:end]) < MIN_CHUNK_LINES:
                pending = seg
                continue
            merged.append(seg)
        if pending:
            if merged:
                s, _, sym, kind = merged[-1]
                merged[-1] = (s, pending[1], sym, kind)
            else:
                merged.append(pending)
        return merged

    @staticmethod
    def _windows(start: int, end: int):
        if end - start + 1 <= MAX_CHUNK_LINES:
            yield start, end
            return
        step = MAX_CHUNK_LINES - WINDOW_OVERLAP
        s = start
        while s <= end:
            e = min(s + MAX_CHUNK_LINES - 1, end)
            yield s, e
            if e == end:
                break
            s += step
