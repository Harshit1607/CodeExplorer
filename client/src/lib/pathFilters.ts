// Test-file detection, mirroring `is_test_path` in server/app/services/path_filters.py.
// A bare `test/` directory only counts at the repo root or under `src/` (Maven/Gradle);
// elsewhere it is often a real package, such as `django/test/`.
const TEST_FILE_RE = new RegExp(
  '(^|/)(test_[^/]+\\.py|[^/]+_tests?\\.(py|go|rs|rb|exs?|dart|cc|cpp|c)|tests\\.py|conftest\\.py' +
  '|[^/]+\\.(test|spec)\\.[cm]?[jt]sx?|[^/]+_spec\\.rb' +
  '|[^/]+(Tests?|IT|Spec)\\.(java|kt|scala|cs|swift))$',
);
const TEST_DIR_RE = /(^|\/)(tests|__tests__|__mocks__|testdata|test_data|e2e|spec|specs)\/|^test\/|(^|\/)src\/test\//;

export function isTestPath(path: string): boolean {
  return TEST_FILE_RE.test(path) || TEST_DIR_RE.test(path);
}
