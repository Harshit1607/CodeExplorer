"""
What a repository path *is*: the product's own code, or tests, examples, docs or generated
output. One classifier shared by every place that decides what the repository is about
(framework and database detection, key files, entry points, architecture, the AI report
inputs, the call graph, search ranking and quick start roots), so that an `examples/celery`
sub-project, a test suite or a generated API client never speaks for the whole repository.

Also maps a path to its language family, used to keep call edges inside one language.
"""
import posixpath
import re
from functools import lru_cache
from typing import Iterable, List, Optional

PRIMARY = "primary"
TEST = "test"
EXAMPLE = "example"
DOCS = "docs"
GENERATED = "generated"

CATEGORIES = (PRIMARY, TEST, EXAMPLE, DOCS, GENERATED)

# Directory names (any segment, case-insensitive) and the category they put their contents in.
_DIR_CATEGORIES = {
    TEST: {"test", "tests", "__tests__", "__mocks__", "spec", "specs", "e2e", "testdata", "test-data",
           "testing-data", "fixture", "fixtures", "benchmark", "benchmarks", "benches", "bench",
           "playwright", "cypress"},
    EXAMPLE: {"example", "examples", "sample", "samples", "demo", "demos", "playground", "playgrounds",
              "cookbook", "tutorial", "tutorials"},
    DOCS: {"doc", "docs", "documentation", "docs_src", "docs-src", "website"},
    GENERATED: {"__generated__", "generated", "gen-src"},
}
_DIR_LOOKUP = {name: cat for cat, names in _DIR_CATEGORIES.items() for name in names}

# File names that are generated or machine-maintained, whatever directory they sit in.
_LOCKFILES = {
    "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb", "bun.lock",
    "poetry.lock", "uv.lock", "pdm.lock", "pipfile.lock", "cargo.lock", "gemfile.lock", "composer.lock",
    "go.sum", "flake.lock", "packages.lock.json", "gradle.lockfile",
}
_GENERATED_FILE_RE = re.compile(
    r"(\.gen\.[cm]?[jt]sx?|\.generated\.\w+|_pb2(_grpc)?\.pyi?|\.pb\.(go|cc|h)|_grpc\.pb\.(go|cc|h)"
    r"|\.pb\.gw\.go|_pb\.[jt]s|_grpc_pb\.[jt]s|\.min\.(js|css|mjs)|[-.]bundle\.js|\.g\.dart|\.freezed\.dart"
    r"|_generated\.\w+|\.designer\.cs)$", re.I)

# File names that mark a test, whatever directory they sit in.
_TEST_FILE_RE = re.compile(
    r"(^test_.+\.py$|.+_test\.py$|^conftest\.py$|.+_test\.go$|.+\.(test|spec)\.[cm]?[jt]sx?$"
    r"|.+(Test|Tests|IT|Spec)\.(java|kt|scala)$|.+_spec\.rb$|.+_test\.rb$|.+Test\.php$"
    r"|.+_tests?\.(rs|cc|cpp|c)$|^test_.+\.(cc|cpp|c)$)")
_EXAMPLE_FILE_RE = re.compile(r".+\.stories\.[cm]?[jt]sx?$")  # Storybook stories


@lru_cache(maxsize=65536)
def classify_path(path: str) -> str:
    """primary | test | example | docs | generated for a repository-relative path.

    Generated file names win; otherwise the first (outermost) categorised directory decides,
    so `examples/app/tests/test_x.py` is an example and `tests/fixtures/demo/a.py` a test.
    Test file names (`test_x.py`, `x.spec.ts`, `FooTest.java`) next to sources are tests."""
    norm = path.replace("\\", "/").strip("/")
    if not norm:
        return PRIMARY
    parts = norm.split("/")
    name = parts[-1]
    lower_name = name.lower()
    if lower_name in _LOCKFILES or _GENERATED_FILE_RE.search(name):
        return GENERATED
    for seg in parts[:-1]:
        cat = _DIR_LOOKUP.get(seg.lower())
        if cat:
            return cat
    if _TEST_FILE_RE.match(name):
        return TEST
    if _EXAMPLE_FILE_RE.match(name):
        return EXAMPLE
    return PRIMARY


def classify_dir(path: str) -> str:
    """Category of a directory (the contents it would give its files)."""
    norm = path.replace("\\", "/").strip("/")
    if not norm:
        return PRIMARY
    for seg in norm.split("/"):
        cat = _DIR_LOOKUP.get(seg.lower())
        if cat:
            return cat
    return PRIMARY


def is_primary(path: str) -> bool:
    return classify_path(path) == PRIMARY


def is_secondary(path: str) -> bool:
    """Tests, examples, docs or generated output."""
    return classify_path(path) != PRIMARY


def is_secondary_dir(path: str) -> bool:
    return classify_dir(path) != PRIMARY


def secondary_root(path: str) -> Optional[str]:
    """The directory that makes `path` secondary (`backend/tests` for `backend/tests/api/x.py`),
    or None when only the file name does (a `foo.test.ts` next to its source, a generated file)."""
    parts = path.replace("\\", "/").strip("/").split("/")
    for i, seg in enumerate(parts[:-1]):
        if seg.lower() in _DIR_LOOKUP:
            return "/".join(parts[:i + 1])
    return None


def primary_paths(paths: Iterable[str]) -> List[str]:
    """The primary paths, or all of them when the repository has no primary code at all
    (a collection of examples is still worth describing)."""
    paths = list(paths)
    primary = [p for p in paths if is_primary(p)]
    return primary or paths


# ----------------------------------------------------------------------------
# Language families: a call written in one family never resolves to a function in another.
# ----------------------------------------------------------------------------
_FAMILY_BY_EXT = {}
for _family, _exts in {
    "python": (".py", ".pyi"),
    "javascript": (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts", ".vue", ".svelte"),
    "jvm": (".java", ".kt", ".kts", ".scala"),
    "rust": (".rs",),
    "cpp": (".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx", ".ipp"),
    "go": (".go",),
    "ruby": (".rb",),
    "php": (".php",),
    "csharp": (".cs",),
    "swift": (".swift",),
}.items():
    for _ext in _exts:
        _FAMILY_BY_EXT[_ext] = _family


def language_family(path: str) -> Optional[str]:
    return _FAMILY_BY_EXT.get(posixpath.splitext(path)[1].lower())
