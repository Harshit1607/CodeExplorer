"""
Project manifests: dependencies and build/run commands for every supported ecosystem.

  Python      requirements*.txt, pyproject.toml (PEP 621, PEP 735 groups, Poetry, PDM, uv),
              Pipfile, setup.cfg, setup.py
  JS / TS     package.json
  Java        pom.xml (Maven), build.gradle(.kts) + gradle/libs.versions.toml (Gradle)
  Rust        every Cargo.toml (workspace, dev/build/target-specific dependencies)
  C / C++     CMakeLists.txt (find_package, FetchContent, CPM, pkg-config), conanfile.txt/.py,
              vcpkg.json, meson.build
  Go          go.mod

`build_systems()` turns the detected project roots into ready-to-run commands
(install / build / run / test), using wrappers and lockfiles when present
(./mvnw, ./gradlew, uv.lock, poetry.lock, pnpm-lock.yaml, ...).
"""
import configparser
import json
import os
import posixpath
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Set, Tuple

from app.services.fs_utils import inside_repo, read_repo_text

try:
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None

MAX_MANIFESTS_PER_TYPE = 60
MAX_ROOTS_PER_ECOSYSTEM = 4
_SECONDARY_DIR_RE = re.compile(r"(^|/)(tests?|examples?|samples?|demos?|docs?|fixtures?|benchmarks?|benches|testdata|e2e)(/|$)", re.I)

MANIFEST_NAMES = {
    "package.json": "npm", "pyproject.toml": "pyproject", "Pipfile": "pipfile", "setup.cfg": "setupcfg",
    "setup.py": "setuppy", "pom.xml": "maven", "build.gradle": "gradle", "build.gradle.kts": "gradle",
    "settings.gradle": "gradle-settings", "settings.gradle.kts": "gradle-settings", "libs.versions.toml": "gradle-catalog",
    "Cargo.toml": "cargo", "CMakeLists.txt": "cmake", "conanfile.txt": "conan", "conanfile.py": "conan",
    "vcpkg.json": "vcpkg", "meson.build": "meson", "go.mod": "gomod",
    "Makefile": "make", "makefile": "make", "GNUmakefile": "make", "manage.py": "django",
}
_REQUIREMENTS_RE = re.compile(r"^requirements([-_.][\w.-]+)?\.(txt|in)$", re.I)


def _read(repo_path: str, *parts: str) -> str:
    """Text of a repository file; "" when missing or a symlink leading outside the repo."""
    return read_repo_text(repo_path, *parts) or ""


def _toml(repo_path: str, *parts: str) -> dict:
    if tomllib is None:
        return {}
    try:
        return tomllib.loads(_read(repo_path, *parts))
    except Exception:
        return {}


def _pep508_name(req: str) -> Optional[str]:
    m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", req or "")
    return m.group(1) if m else None


def _norm_py(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


# ----------------------------------------------------------------------------
# Discovery
# ----------------------------------------------------------------------------
def find_manifests(repo_path: str, skip_dirs: Set[str]) -> Dict[str, List[str]]:
    """{manifest type: [relative paths]} (requirements files are type 'requirements')."""
    found: Dict[str, List[str]] = defaultdict(list)
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = sorted(d for d in dirs if d not in skip_dirs and not d.endswith(".egg-info"))
        rel = os.path.relpath(root, repo_path).replace("\\", "/")
        rel = "" if rel == "." else rel
        for name in files:
            kind = MANIFEST_NAMES.get(name)
            if kind is None and _REQUIREMENTS_RE.match(name):
                kind = "requirements"
            if kind and len(found[kind]) < MAX_MANIFESTS_PER_TYPE \
                    and inside_repo(repo_path, os.path.join(root, name)):
                found[kind].append(f"{rel}/{name}" if rel else name)
    return found


def _key(rel_path: str, suffix: str = "") -> str:
    return rel_path + (f" ({suffix})" if suffix else "")


# ----------------------------------------------------------------------------
# Dependency extraction
# ----------------------------------------------------------------------------
def extract_dependencies(repo_path: str, manifests: Dict[str, List[str]]) -> Dict[str, Dict[str, List[str]]]:
    deps: Dict[str, Dict[str, List[str]]] = {
        "python": {}, "javascript": {}, "java": {}, "rust": {}, "cpp": {}, "other": {},
    }

    def put(eco: str, key: str, names: Iterable[str]):
        names = list(dict.fromkeys(n for n in names if n))
        if names:
            deps[eco][key] = names

    # ---- JavaScript
    for rel in manifests.get("npm", []):
        try:
            pkg = json.loads(_read(repo_path, rel))
        except Exception:
            continue
        prefix = posixpath.dirname(rel)
        if pkg.get("dependencies"):
            put("javascript", f"{prefix}/dependencies" if prefix else "dependencies", pkg["dependencies"].keys())
        if pkg.get("devDependencies"):
            put("javascript", f"{prefix}/devDependencies" if prefix else "devDependencies", pkg["devDependencies"].keys())

    # ---- Python
    for rel in manifests.get("requirements", []):
        names = []
        for line in _read(repo_path, rel).splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith(("-r", "-c", "--")):
                continue
            egg = re.search(r"#egg=([\w.-]+)", line)
            if line.startswith("-e") or "://" in line:
                names.append(egg.group(1) if egg else None)
            else:
                names.append(_pep508_name(line))
        put("python", rel, names)

    for rel in manifests.get("pyproject", []):
        data = _toml(repo_path, rel)
        project = data.get("project") or {}
        put("python", rel, (_pep508_name(r) for r in project.get("dependencies") or []))
        extra = [_pep508_name(r) for group in (project.get("optional-dependencies") or {}).values() for r in group]
        extra += [_pep508_name(r) for group in (data.get("dependency-groups") or {}).values()
                  for r in group if isinstance(r, str)]
        tool = data.get("tool") or {}
        poetry = tool.get("poetry") or {}
        put("python", rel + " (poetry)", (k for k in (poetry.get("dependencies") or {}) if k.lower() != "python"))
        extra += list((poetry.get("dev-dependencies") or {}).keys())
        for group in (poetry.get("group") or {}).values():
            extra += list((group.get("dependencies") or {}).keys())
        for group in ((tool.get("pdm") or {}).get("dev-dependencies") or {}).values():
            extra += [_pep508_name(r) for r in group]
        extra += [_pep508_name(r) for r in ((tool.get("uv") or {}).get("dev-dependencies") or [])]
        put("python", _key(rel, "dev/optional"), extra)

    for rel in manifests.get("pipfile", []):
        data = _toml(repo_path, rel)
        put("python", rel, (data.get("packages") or {}).keys())
        put("python", _key(rel, "dev"), (data.get("dev-packages") or {}).keys())

    for rel in manifests.get("setupcfg", []):
        cfg = configparser.ConfigParser()
        try:
            cfg.read_string(_read(repo_path, rel))
            raw = cfg.get("options", "install_requires", fallback="")
            put("python", rel, (_pep508_name(l) for l in raw.splitlines() if l.strip()))
        except Exception:
            pass

    for rel in manifests.get("setuppy", []):
        m = re.search(r"install_requires\s*=\s*\[(.*?)\]", _read(repo_path, rel), re.S)
        if m:
            put("python", rel, (_pep508_name(s) for s in re.findall(r"['\"]([^'\"]+)['\"]", m.group(1))))

    # ---- Java
    for rel in manifests.get("maven", []):
        put("java", rel, _maven_deps(_read(repo_path, rel)))
    for rel in manifests.get("gradle", []):
        text = _read(repo_path, rel)
        coords = re.findall(
            r"\b(?:implementation|api|compileOnly|runtimeOnly|testImplementation|testRuntimeOnly|"
            r"annotationProcessor|kapt|ksp|developmentOnly|classpath|compile|testCompile)\s*\(?\s*"
            r"(?:platform\s*\(\s*|enforcedPlatform\s*\(\s*)?[\"']([\w.\-]+):([\w.\-]+)", text)
        put("java", rel, (f"{g}:{a}" for g, a in coords))
        plugins = re.findall(r"\bid\s*\(?\s*[\"']([\w.\-]+)[\"']", text)
        plugins += re.findall(r"apply\s+plugin\s*:\s*[\"']([\w.\-]+)[\"']", text)
        plugins += [p for p in re.findall(r"^\s*(application|java-library|java)\s*$", text, re.M)]
        put("java", _key(rel, "plugins"), plugins)
    for rel in manifests.get("gradle-catalog", []):
        data = _toml(repo_path, rel)
        libs = []
        for v in (data.get("libraries") or {}).values():
            if isinstance(v, str):
                libs.append(":".join(v.split(":")[:2]))
            elif isinstance(v, dict):
                libs.append(v.get("module") or (f"{v.get('group')}:{v.get('name')}" if v.get("group") else None))
        put("java", rel, libs)
        put("java", _key(rel, "plugins"), ((p.get("id") if isinstance(p, dict) else str(p).split(":")[0])
                                           for p in (data.get("plugins") or {}).values()))

    # ---- Rust
    for rel in manifests.get("cargo", []):
        data = _toml(repo_path, rel)
        tables = {"": [data.get("dependencies")], "dev": [data.get("dev-dependencies")],
                  "build": [data.get("build-dependencies")]}
        tables[""].append((data.get("workspace") or {}).get("dependencies"))
        for target in (data.get("target") or {}).values():
            tables[""].append(target.get("dependencies"))
            tables["dev"].append(target.get("dev-dependencies"))
        for suffix, groups in tables.items():
            names = []
            for t in groups:
                for name, spec in (t or {}).items():
                    names.append(spec.get("package", name) if isinstance(spec, dict) else name)
            put("rust", _key(rel, suffix), names)

    # ---- C / C++
    for rel in manifests.get("cmake", []):
        text = _read(repo_path, rel)
        names = re.findall(r"find_package\s*\(\s*([A-Za-z0-9_]+)", text, re.I)
        names += re.findall(r"FetchContent_Declare\s*\(\s*([A-Za-z0-9_\-]+)", text, re.I)
        names += re.findall(r"CPMAddPackage\s*\(\s*NAME\s+([A-Za-z0-9_\-]+)", text, re.I)
        names += [m.split("/")[-1] for m in re.findall(r"CPMAddPackage\s*\(\s*\"(?:gh|gl|bb):([^\"#@]+)", text, re.I)]
        names += re.findall(r"pkg_check_modules\s*\(\s*\w+\s+(?:(?:REQUIRED|QUIET|IMPORTED_TARGET|GLOBAL)\s+)*([\w\-+.]+)", text, re.I)
        put("cpp", rel, names)
    for rel in manifests.get("conan", []):
        text = _read(repo_path, rel)
        if rel.endswith(".txt"):
            section, names = None, []
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("["):
                    section = line.strip("[]").lower()
                elif line and section in ("requires", "tool_requires", "build_requires"):
                    names.append(line.split("/")[0])
            put("cpp", rel, names)
        else:
            put("cpp", rel, re.findall(r"[\"']([\w.\-+]+)/[\w.\-+@\[\]~, ]+[\"']", text))
    for rel in manifests.get("vcpkg", []):
        try:
            data = json.loads(_read(repo_path, rel))
            put("cpp", rel, ((d if isinstance(d, str) else d.get("name")) for d in data.get("dependencies", [])))
        except Exception:
            pass
    for rel in manifests.get("meson", []):
        put("cpp", rel, re.findall(r"dependency\s*\(\s*'([^']+)'", _read(repo_path, rel)))

    # ---- Go
    for rel in manifests.get("gomod", []):
        put("other", rel, re.findall(r"^\s*([\w./-]+)\s+v\d", _read(repo_path, rel), re.M))

    return deps


def _maven_deps(text: str) -> List[str]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    for el in root.iter():  # strip XML namespaces
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    out = []
    parent = root.find("parent")
    if parent is not None:
        out.append(f"{parent.findtext('groupId', '')}:{parent.findtext('artifactId', '')}")
    for dep in root.findall("./dependencies/dependency"):
        out.append(f"{dep.findtext('groupId', '')}:{dep.findtext('artifactId', '')}")
    for plugin in root.findall("./build/plugins/plugin"):
        out.append(f"{plugin.findtext('groupId', 'org.apache.maven.plugins')}:{plugin.findtext('artifactId', '')}")
    return [c for c in out if not c.startswith(":") and not c.endswith(":")]


_DEV_KEY_RE = re.compile(r"devDependencies|\((?:dev|build|dev/optional)\)|(^|/)requirements[-_.]?(dev|test|docs|lint)", re.I)


def dependency_sets(deps: Dict[str, Dict[str, List[str]]], runtime_only: bool = False) -> Dict[str, Set[str]]:
    """Lower-cased dependency names per ecosystem (Python names PEP 503-normalised).
    `runtime_only` drops dev/test/build groups (devDependencies, Cargo dev-dependencies, ...)."""
    sets: Dict[str, Set[str]] = {}
    for eco, groups in deps.items():
        values = {d.lower() for key, names in groups.items()
                  if not (runtime_only and _DEV_KEY_RE.search(key)) for d in names}
        sets[eco] = {_norm_py(v) for v in values} | values if eco == "python" else values
    return sets


# ----------------------------------------------------------------------------
# Build systems / quick start
# ----------------------------------------------------------------------------
def _roots(paths: Iterable[str]) -> List[str]:
    """Top-most directories (no nested roots of the same ecosystem), primary dirs first."""
    dirs = sorted({posixpath.dirname(p) for p in paths}, key=lambda d: (d.count("/") if d else -1, d))
    chosen: List[str] = []
    for d in dirs:
        if any(c == "" or d == c or d.startswith(c + "/") for c in chosen):
            continue
        if d and _SECONDARY_DIR_RE.search(d):
            continue
        chosen.append(d)
    return chosen[:MAX_ROOTS_PER_ECOSYSTEM]


def _js_package_manager(repo_path: str, root: str) -> str:
    for d in (root, ""):
        base = os.path.join(repo_path, d)
        for lock, pm in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lockb", "bun"),
                         ("bun.lock", "bun"), ("package-lock.json", "npm")):
            if os.path.exists(os.path.join(base, lock)):
                return pm
    try:
        pm = json.loads(_read(repo_path, root, "package.json")).get("packageManager", "")
        for name in ("pnpm", "yarn", "bun"):
            if pm.startswith(name):
                return name
    except Exception:
        pass
    return "npm"


def _entry(eco: str, tool: str, root: str, **phases) -> dict:
    out = {"ecosystem": eco, "tool": tool, "root": root or "."}
    for phase in ("setup", "install", "build", "run", "test"):
        cmds = phases.get(phase)
        out[phase] = [c for c in ([cmds] if isinstance(cmds, str) else (cmds or [])) if c] or None
    out["notes"] = phases.get("notes") or []
    return out


def _module_under(root: str, file_path: str) -> Optional[str]:
    rel = file_path[len(root) + 1:] if root else file_path
    if not rel.endswith(".py"):
        return None
    parts = rel[:-3].split("/")
    if parts[0] == "src" and len(parts) > 1:
        parts = parts[1:]
    return ".".join(parts)


def build_systems(repo_path: str, manifests: Dict[str, List[str]], files: Dict[str, dict],
                  dep_sets: Dict[str, Set[str]]) -> List[dict]:
    has = lambda root, name: os.path.exists(os.path.join(repo_path, root, name))
    under = lambda root: [p for p in files if not root or p.startswith(root + "/")]
    systems: List[dict] = []

    # ---- JavaScript / TypeScript
    for root in _roots(manifests.get("npm", [])):
        try:
            pkg = json.loads(_read(repo_path, root, "package.json"))
        except Exception:
            continue
        scripts = pkg.get("scripts") or {}
        pm = _js_package_manager(repo_path, root)
        script = lambda s: (f"{pm} run {s}" if pm != "npm" or s not in ("start", "test") else f"npm {s}")
        run = next((script(s) for s in ("dev", "start", "serve", "preview") if s in scripts), None)
        test = scripts.get("test")
        systems.append(_entry(
            "JavaScript/TypeScript", pm, root,
            install=f"{pm} install",
            build=script("build") if "build" in scripts else None,
            run=run or ("node " + pkg["main"] if pkg.get("main") else None),
            test=script("test") if test and "no test specified" not in test else None,
        ))

    # ---- Python
    py_manifests = (manifests.get("pyproject", []) + manifests.get("setuppy", []) + manifests.get("pipfile", [])
                    + manifests.get("requirements", []) + manifests.get("django", []) + manifests.get("setupcfg", []))
    for root in _roots(py_manifests):
        pyproject = _toml(repo_path, root, "pyproject.toml") if has(root, "pyproject.toml") else {}
        tool_cfg = pyproject.get("tool") or {}
        if has(root, "uv.lock") or "uv" in tool_cfg:
            tool = "uv"
        elif has(root, "poetry.lock") or "poetry" in tool_cfg:
            tool = "poetry"
        elif has(root, "pdm.lock") or "pdm" in tool_cfg:
            tool = "pdm"
        elif has(root, "Pipfile"):
            tool = "pipenv"
        else:
            tool = "pip"
        runner = {"uv": "uv run ", "poetry": "poetry run ", "pdm": "pdm run ", "pipenv": "pipenv run "}.get(tool, "")
        setup, install = None, {"uv": "uv sync", "poetry": "poetry install", "pdm": "pdm install",
                                "pipenv": "pipenv install --dev"}.get(tool)
        if tool == "pip":
            setup = ["python -m venv .venv", "source .venv/bin/activate   # Windows: .venv\\Scripts\\activate"]
            if has(root, "requirements.txt"):
                install = "pip install -r requirements.txt"
            elif pyproject or has(root, "setup.py"):
                install = "pip install -e ."

        run = None
        py_files = [p for p in under(root) if p.endswith(".py")]
        scripts = (pyproject.get("project") or {}).get("scripts") or (tool_cfg.get("poetry") or {}).get("scripts") or {}
        if has(root, "manage.py"):
            run = f"{runner}python manage.py runserver"
        elif scripts:
            run = f"{runner}{next(iter(scripts))}"
        else:
            for p in py_files:
                content = files[p].get("content", "")
                m = re.search(r"^(\w+)\s*=\s*FastAPI\(", content, re.M)
                if m and _module_under(root, p):
                    run = f"{runner}uvicorn {_module_under(root, p)}:{m.group(1)} --reload"
                    break
                m = re.search(r"^(\w+)\s*=\s*Flask\(", content, re.M)
                if m and _module_under(root, p):
                    run = f"{runner}flask --app {_module_under(root, p)} run"
                    break
                if "streamlit" in dep_sets.get("python", set()) and re.search(r"^import streamlit", content, re.M):
                    run = f"{runner}streamlit run {p[len(root) + 1:] if root else p}"
                    break
            if run is None:
                mains = [p for p in py_files if p.endswith("/__main__.py")]
                if mains and _module_under(root, mains[0]):
                    run = f"{runner}python -m {_module_under(root, mains[0]).rsplit('.', 1)[0]}"
                else:
                    entry = next((p for p in py_files if files[p].get("has_main")
                                  and not _SECONDARY_DIR_RE.search(p)), None)
                    if entry:
                        run = f"{runner}python {entry[len(root) + 1:] if root else entry}"
        has_tests = any(re.search(r"(^|/)(tests?/|test_[^/]*\.py$)", p) for p in py_files)
        test = f"{runner}pytest" if ("pytest" in dep_sets.get("python", set()) or has_tests) else None
        systems.append(_entry("Python", tool, root, setup=setup, install=install, run=run, test=test))

    # ---- Rust
    rs_files = [p for p in files if p.endswith(".rs")]
    for root in _roots(manifests.get("cargo", [])):
        data = _toml(repo_path, root, "Cargo.toml")
        is_workspace = "workspace" in data
        flag = " --workspace" if is_workspace else ""
        prefix = f"{root}/" if root else ""
        run = None
        if "package" in data and (f"{prefix}src/main.rs" in files or data.get("bin")):
            run = "cargo run"
        elif is_workspace:
            bins = sorted(p for p in rs_files if p.startswith(prefix) and p.endswith("/src/main.rs"))
            for b in bins[:1]:
                member = _toml(repo_path, posixpath.dirname(posixpath.dirname(b)), "Cargo.toml")
                name = (member.get("package") or {}).get("name")
                if name:
                    run = f"cargo run -p {name}"
        notes = [] if run else ["Library crate: no binary target to run."]
        systems.append(_entry("Rust", "cargo", root, build=f"cargo build{flag}", run=run,
                              test=f"cargo test{flag}", notes=notes))

    # ---- Java (Maven / Gradle)
    java = dep_sets.get("java", set())
    spring = any(d.startswith("org.springframework.boot") for d in java)
    quarkus = any(d.startswith("io.quarkus") for d in java)
    for root in _roots(manifests.get("maven", [])):
        mvn = "./mvnw" if has(root, "mvnw") else "mvn"
        run = f"{mvn} spring-boot:run" if spring else (f"{mvn} quarkus:dev" if quarkus else None)
        systems.append(_entry("Java", "maven", root, build=f"{mvn} -B package -DskipTests", run=run,
                              test=f"{mvn} test"))
    gradle_files = manifests.get("gradle-settings", []) + manifests.get("gradle", [])
    for root in _roots(gradle_files):
        gw = "./gradlew" if has(root, "gradlew") else "gradle"
        android = any("com.android" in d for d in java)
        if spring:
            run = f"{gw} bootRun"
        elif "application" in java:
            run = f"{gw} run"
        else:
            run = None
        systems.append(_entry("Java/Kotlin", "gradle", root,
                              build=f"{gw} assembleDebug" if android else f"{gw} build",
                              run=run, test=f"{gw} test",
                              notes=["Android app: install with `./gradlew installDebug` on a device/emulator."] if android else []))

    # ---- C / C++
    cmake_roots = _roots(manifests.get("cmake", []))
    for root in cmake_roots:
        install, toolchain, notes = [], "", []
        if has(root, "conanfile.txt") or has(root, "conanfile.py"):
            install.append("conan install . --output-folder=build --build=missing")
            toolchain = " -DCMAKE_TOOLCHAIN_FILE=build/conan_toolchain.cmake"
        if has(root, "vcpkg.json"):
            toolchain = " -DCMAKE_TOOLCHAIN_FILE=$VCPKG_ROOT/scripts/buildsystems/vcpkg.cmake"
            notes.append("Dependencies come from vcpkg (manifest mode): set VCPKG_ROOT first.")
        cmakelists = [m for m in manifests.get("cmake", []) if not root or m.startswith(root + "/")]
        executables, testing = [], False
        for m in cmakelists:
            text = _read(repo_path, m)
            testing = testing or bool(re.search(r"enable_testing|add_test\s*\(|gtest_discover_tests|catch_discover_tests", text, re.I))
            sub = posixpath.dirname(m)[len(root):].strip("/") if root else posixpath.dirname(m)
            if _SECONDARY_DIR_RE.search(sub):
                continue  # executables under test/, examples/, ... are not the app
            for exe in re.findall(r"add_executable\s*\(\s*([A-Za-z0-9_\-${}]+)", text, re.I):
                if "$" not in exe and not re.search(r"test|bench|example", exe, re.I):
                    executables.append(posixpath.join("build", sub, exe) if sub else f"build/{exe}")
        systems.append(_entry(
            "C/C++", "cmake", root, install=install,
            build=[f"cmake -S . -B build -DCMAKE_BUILD_TYPE=Release{toolchain}", "cmake --build build -j"],
            run=f"./{executables[0]}" if executables else None,
            test="ctest --test-dir build --output-on-failure" if testing else None,
            notes=notes + ([] if executables else ["No executable target found (library project)."]),
        ))
    for root in _roots(manifests.get("meson", [])):
        if root in cmake_roots:
            continue
        systems.append(_entry("C/C++", "meson", root, build=["meson setup build", "meson compile -C build"],
                              test="meson test -C build"))
    has_c = any(p.endswith((".c", ".cc", ".cpp", ".cxx")) for p in files)
    for root in _roots(manifests.get("make", [])):
        if not has_c or root in cmake_roots or has(root, "meson.build"):
            continue
        text = _read(repo_path, root, "Makefile") or _read(repo_path, root, "makefile")
        systems.append(_entry("C/C++", "make", root, build="make",
                              test="make test" if re.search(r"^test\s*:", text, re.M) else None))

    # ---- Go
    for root in _roots(manifests.get("gomod", [])):
        prefix = f"{root}/" if root else ""
        go_files = [p for p in files if p.startswith(prefix) and p.endswith(".go")]
        if any(posixpath.dirname(p) == root and files[p].get("has_main") for p in go_files):
            run = "go run ."
        else:
            cmd = sorted({posixpath.dirname(p) for p in go_files if files[p].get("has_main") and "/cmd/" in "/" + p})
            run = f"go run ./{cmd[0][len(prefix):]}" if cmd else None
        systems.append(_entry("Go", "go", root, install="go mod download", build="go build ./...",
                              run=run, test="go test ./..."))

    return _rank_systems(systems, files)


_ECOSYSTEM_EXTS = {
    "JavaScript/TypeScript": (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts", ".vue", ".svelte"),
    "Python": (".py", ".pyi"),
    "Rust": (".rs",),
    "Java": (".java", ".kt"),
    "Java/Kotlin": (".java", ".kt"),
    "C/C++": (".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx", ".ipp"),
    "Go": (".go",),
}


def _rank_systems(systems: List[dict], files: Dict[str, dict]) -> List[dict]:
    """Order by how much of the code each build covers; drop builds for code that isn't there
    (e.g. a Gradle file used only for packaging in a C++ repo)."""
    def weight(s: dict) -> int:
        exts = _ECOSYSTEM_EXTS.get(s["ecosystem"], ())
        root = "" if s["root"] == "." else s["root"] + "/"
        return sum(1 for p in files if p.startswith(root) and p.endswith(exts))

    weighted = [(weight(s), i, s) for i, s in enumerate(systems)]
    kept = [w for w in weighted if w[0] > 0] or weighted
    kept.sort(key=lambda w: (-w[0], w[1]))
    return [s for _, _, s in kept]
