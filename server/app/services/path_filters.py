"""
Path predicates for code that is not the product itself: tests, generated files, vendored copies.

Used to keep the search index on primary code and to hide tests in the call graph by default.
Paths are repository-relative with forward slashes.
"""
import re
from typing import Optional

# Test files by name: test_x.py, x_test.py, x_test.go, x.test.ts, x.spec.js, XTest.java, conftest.py ...
_TEST_FILE_RE = re.compile(
    r"(^|/)(test_[^/]+\.py|[^/]+_tests?\.(py|go|rs|rb|exs?|dart|cc|cpp|c)|tests\.py|conftest\.py"
    r"|[^/]+\.(test|spec)\.[cm]?[jt]sx?|[^/]+_spec\.rb"
    r"|[^/]+(Tests?|IT|Spec)\.(java|kt|scala|cs|swift))$")
# Test directories anywhere in the path. A bare `test/` dir is only counted at the repo root or
# under `src/` (Maven/Gradle layout): elsewhere it is often a real package such as `django/test/`.
_TEST_DIR_RE = re.compile(
    r"(^|/)(tests|__tests__|__mocks__|testdata|test_data|e2e|spec|specs)/"
    r"|^test/|(^|/)src/test/")

_GENERATED_FILE_RE = re.compile(
    r"(\.gen\.[^/]+|\.generated\.[^/]+|_generated\.[^/]+|_pb2(_grpc)?\.pyi?|\.pb\.(go|cc|h)|\.g\.dart"
    r"|\.min\.[cm]?js|-min\.js|\.bundle\.js|\.chunk\.js)$")
_GENERATED_DIR_RE = re.compile(r"(^|/)(generated|__generated__|migrations)/")

_VENDORED_DIR_RE = re.compile(
    r"(^|/)(vendor|vendors|vendored|third_party|third-party|thirdparty|3rdparty|node_modules"
    r"|bower_components|site-packages)/")


def is_test_path(path: str) -> bool:
    return bool(_TEST_FILE_RE.search(path) or _TEST_DIR_RE.search(path))


def is_generated_path(path: str) -> bool:
    return bool(_GENERATED_FILE_RE.search(path) or _GENERATED_DIR_RE.search(path))


def is_vendored_path(path: str) -> bool:
    return bool(_VENDORED_DIR_RE.search(path))


def non_primary_reason(path: str) -> Optional[str]:
    """'test' | 'generated' | 'vendored' when the path is not primary product code, else None."""
    if is_vendored_path(path):
        return "vendored"
    if is_generated_path(path):
        return "generated"
    if is_test_path(path):
        return "test"
    return None
