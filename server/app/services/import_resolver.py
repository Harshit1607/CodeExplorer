"""
Resolve parsed import references to files inside the repository, per language.

  Python      dotted modules (src-layout aware, longest-suffix matching), relative imports
              with levels (`from ..core import X`), submodule imports (`from pkg import mod`)
  JS / TS     relative paths with extension probing (incl. TS ESM `./x.js` -> `x.ts`),
              index files, tsconfig/jsconfig `baseUrl` + `paths`, monorepo workspace packages
  Java        fully-qualified class names via each file's `package`, static & wildcard
              imports, plus same-package type references (no import needed in Java)
  Rust        `mod foo;` declarations and `use crate::/self::/super::` paths, including
              other crates of the same Cargo workspace
  C / C++     `#include "..."` relative to the including file, then by path suffix;
              `<...>` includes only when they match a project header (e.g. <fmt/core.h>)

Anything unresolved is reported as external.
"""
import json
import os
import posixpath
import re
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Dict, Iterable, List, Optional, Set, Tuple

from app.services.fs_utils import read_repo_text

try:
    import tomllib
except ImportError:  # pragma: no cover  (Python < 3.11)
    tomllib = None

PY_EXTS = (".py", ".pyi")
JS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")
JS_RESOLVE_EXTS = ("", ".ts", ".tsx", ".d.ts", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts", ".vue", ".svelte")
JS_INDEX = tuple(f"/index{e}" for e in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"))
CPP_EXTS = (".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx", ".ipp")
MAX_WILDCARD_FILES = 20


def _common_prefix_len(a: str, b: str) -> int:
    pa, pb = a.split("/"), b.split("/")
    n = 0
    for x, y in zip(pa, pb):
        if x != y:
            break
        n += 1
    return n


def _closest(candidates: Iterable[str], current: str) -> Optional[str]:
    cands = list(candidates)
    if not cands:
        return None
    return max(cands, key=lambda c: (_common_prefix_len(c, current), -len(c)))


def _load_jsonc(text: str):
    """Parse tsconfig-style JSON with comments and trailing commas."""
    text = re.sub(r'("(?:\\.|[^"\\])*")|//[^\n]*|/\*.*?\*/', lambda m: m.group(1) or "", text, flags=re.S)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return json.loads(text)


class ImportResolver:
    def __init__(self, files: Dict[str, dict], repo_path: str):
        self.files = files
        self.repo_path = repo_path
        self.paths: Set[str] = set(files)
        self._build_python_index()
        self._build_js_config()
        self._build_java_index()
        self._build_rust_index()
        self._build_cpp_index()

    # ------------------------------------------------------------------ API
    def resolve_file(self, path: str) -> Tuple[List[str], List[str]]:
        """(resolved repo files, external import strings) for one file."""
        meta = self.files.get(path, {})
        refs = meta.get("import_refs")
        if refs is None:
            return [], []
        ext = PurePosixPath(path).suffix.lower()
        resolved: List[str] = []
        external: List[str] = []

        for ref in refs:
            targets = self._resolve_ref(path, ext, ref)
            if targets:
                resolved.extend(t for t in targets if t != path)
            elif ref["kind"] != "mod":
                external.append(ref["module"])

        if ext == ".java":
            resolved.extend(self._java_same_package(path, meta))

        return list(dict.fromkeys(resolved)), list(dict.fromkeys(external))

    def _resolve_ref(self, path: str, ext: str, ref: dict) -> List[str]:
        if ext in PY_EXTS:
            return self._python(path, ref)
        if ext in JS_EXTS or ext in (".vue", ".svelte"):
            r = self._js(path, ref["module"])
            return [r] if r else []
        if ext == ".java":
            return self._java(ref)
        if ext == ".rs":
            return self._rust(path, ref)
        if ext in CPP_EXTS:
            r = self._cpp(path, ref)
            return [r] if r else []
        return []

    # --------------------------------------------------------------- Python
    def _build_python_index(self):
        self.py_modules: Dict[str, List[str]] = defaultdict(list)
        for p in self.paths:
            if not p.endswith(PY_EXTS):
                continue
            parts = p[: p.rfind(".")].split("/")
            if parts[-1] == "__init__":
                parts = parts[:-1]
            for i in range(len(parts)):
                self.py_modules[".".join(parts[i:])].append(p)

    def _py_lookup(self, dotted: str, current: str) -> Optional[str]:
        return _closest(self.py_modules.get(dotted, []), current)

    def _py_package_file(self, dir_parts: List[str]) -> Optional[str]:
        base = "/".join(dir_parts)
        for cand in (f"{base}.py", f"{base}/__init__.py", f"{base}.pyi", f"{base}/__init__.pyi"):
            cand = cand.lstrip("/")
            if cand in self.paths:
                return cand
        return None

    def _python(self, path: str, ref: dict) -> List[str]:
        module, names = ref["module"], [n for n in ref.get("names", []) if n != "*"]
        if module.startswith("."):
            level = len(module) - len(module.lstrip("."))
            rest = [p for p in module[level:].split(".") if p]
            base = path.split("/")[:-1]
            for _ in range(level - 1):
                base = base[:-1]
            out = [f for f in (self._py_package_file(base + rest + [n]) for n in names) if f]
            if out:
                return out
            f = self._py_package_file(base + rest) if (base + rest) else None
            return [f] if f else []
        # absolute: prefer `pkg.submodule` for `from pkg import submodule`
        out = [f for f in (self._py_lookup(f"{module}.{n}", path) for n in names) if f]
        if out:
            return out
        f = self._py_lookup(module, path)
        return [f] if f else []

    # ------------------------------------------------------------ JS / TS
    def _build_js_config(self):
        """tsconfig/jsconfig paths + monorepo package names."""
        # (config dir, dir that `paths` / bare imports resolve against, paths, has baseUrl)
        self.js_configs: List[Tuple[str, str, Dict[str, List[str]], bool]] = []
        self.js_packages: Dict[str, str] = {}  # package name -> dir
        for root, dirs, fnames in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in {"node_modules", ".git", "dist", "build", ".next", "out"}]
            rel = os.path.relpath(root, self.repo_path).replace("\\", "/")
            rel = "" if rel == "." else rel
            for name in fnames:
                full = os.path.join(root, name)
                if name in ("tsconfig.json", "jsconfig.json") or re.match(r"tsconfig\..+\.json$", name):
                    try:
                        cfg = _load_jsonc(read_repo_text(self.repo_path, full) or "{}")
                        opts = cfg.get("compilerOptions") or {}
                        base_url = opts.get("baseUrl")
                        paths = opts.get("paths") or {}
                        if base_url is not None or paths:
                            base = posixpath.normpath(posixpath.join(rel or ".", base_url or "."))
                            self.js_configs.append((rel, "" if base == "." else base, paths, base_url is not None))
                    except Exception:
                        pass
                elif name == "package.json":
                    try:
                        pkg_name = json.loads(read_repo_text(self.repo_path, full) or "{}").get("name")
                        if pkg_name:
                            self.js_packages[pkg_name] = rel
                    except Exception:
                        pass
        # Nearest config first
        self.js_configs.sort(key=lambda c: -len(c[0]))

    def _js_probe(self, base: str) -> Optional[str]:
        base = posixpath.normpath(base).lstrip("./") if base not in ("", ".") else ""
        if not base:
            return None
        candidates = [base + e for e in JS_RESOLVE_EXTS] + [base + i for i in JS_INDEX]
        stem, ext = posixpath.splitext(base)
        if ext in (".js", ".jsx", ".mjs", ".cjs"):  # TS ESM: import './x.js' refers to x.ts
            swap = {".js": (".ts", ".tsx"), ".jsx": (".tsx",), ".mjs": (".mts",), ".cjs": (".cts",)}[ext]
            candidates += [stem + e for e in swap]
        for c in candidates:
            if c in self.paths:
                return c
        return None

    def _js(self, path: str, module: str) -> Optional[str]:
        module = module.split("?")[0]
        current_dir = posixpath.dirname(path)
        if module.startswith("."):
            return self._js_probe(posixpath.join(current_dir, module))
        if module.startswith("/"):
            return self._js_probe(module[1:])

        # tsconfig / jsconfig paths & baseUrl (nearest applicable config)
        for cfg_dir, base_dir, paths, has_base_url in self.js_configs:
            if cfg_dir and not path.startswith(cfg_dir + "/"):
                continue
            for pattern, targets in paths.items():
                if "*" in pattern:
                    prefix, suffix = pattern.split("*", 1)
                    if module.startswith(prefix) and module.endswith(suffix) and len(module) >= len(prefix) + len(suffix):
                        star = module[len(prefix): len(module) - len(suffix)]
                        for t in targets:
                            r = self._js_probe(posixpath.join(base_dir, t.replace("*", star)))
                            if r:
                                return r
                elif module == pattern:
                    for t in targets:
                        r = self._js_probe(posixpath.join(base_dir, t))
                        if r:
                            return r
            if has_base_url:  # bare specifiers resolve against baseUrl only when it is set
                r = self._js_probe(posixpath.join(base_dir, module))
                if r:
                    return r

        # Monorepo workspace packages: "@scope/pkg" or "@scope/pkg/sub"
        for name, pkg_dir in self.js_packages.items():
            if module == name or module.startswith(name + "/"):
                sub = module[len(name):].lstrip("/")
                for base in ([posixpath.join(pkg_dir, sub), posixpath.join(pkg_dir, "src", sub)] if sub else
                             [posixpath.join(pkg_dir, "src/index"), posixpath.join(pkg_dir, "index"),
                              posixpath.join(pkg_dir, "lib/index")]):
                    r = self._js_probe(base)
                    if r:
                        return r

        # Common alias conventions: "@/x" and "~/x" -> src/x
        if module.startswith(("@/", "~/")):
            return self._js_probe("src/" + module[2:]) or self._js_probe(module[2:])
        return None

    # ----------------------------------------------------------------- Java
    def _build_java_index(self):
        self.java_classes: Dict[str, str] = {}               # fqcn -> file
        self.java_packages: Dict[str, List[str]] = defaultdict(list)
        self.java_declared: Dict[str, Set[str]] = {}         # file -> declared class names
        for p, meta in self.files.items():
            if not p.endswith(".java"):
                continue
            pkg = meta.get("package") or ""
            stem = PurePosixPath(p).stem
            self.java_packages[pkg].append(p)
            self.java_classes[f"{pkg}.{stem}" if pkg else stem] = p
            declared = set(meta.get("classes", [])) | {stem}
            self.java_declared[p] = declared
            for cls in declared:
                self.java_classes.setdefault(f"{pkg}.{cls}" if pkg else cls, p)

    def _java(self, ref: dict) -> List[str]:
        module = ref["module"]
        if module.endswith(".*"):
            pkg = module[:-2]
            files = self.java_packages.get(pkg)
            if files:
                return sorted(files)[:MAX_WILDCARD_FILES]
            module = pkg  # `import static a.b.Util.*`
        parts = module.split(".")
        while parts:  # drop member / nested-class segments until a class matches
            f = self.java_classes.get(".".join(parts))
            if f:
                return [f]
            parts = parts[:-1]
        return []

    def _java_same_package(self, path: str, meta: dict) -> List[str]:
        refs = set(meta.get("type_refs") or [])
        if not refs:
            return []
        out = []
        for other in self.java_packages.get(meta.get("package") or "", []):
            if other != path and refs & self.java_declared.get(other, set()):
                out.append(other)
        return out

    # ----------------------------------------------------------------- Rust
    def _build_rust_index(self):
        self.rust_crates: Dict[str, str] = {}   # crate dir -> crate name (as used in paths)
        self.rust_crate_by_name: Dict[str, str] = {}
        for root, dirs, fnames in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in {".git", "target", "node_modules"}]
            if "Cargo.toml" in fnames:
                rel = os.path.relpath(root, self.repo_path).replace("\\", "/")
                rel = "" if rel == "." else rel
                name = None
                if tomllib is not None:
                    try:
                        data = tomllib.loads(read_repo_text(self.repo_path, root, "Cargo.toml") or "")
                        name = ((data.get("lib") or {}).get("name") or (data.get("package") or {}).get("name"))
                    except Exception:
                        pass
                name = (name or PurePosixPath(rel or "crate").name).replace("-", "_")
                self.rust_crates[rel] = name
                self.rust_crate_by_name[name] = rel

        # module path for every .rs file: (crate_dir, ("a", "b"))
        self.rust_mod_of: Dict[str, Tuple[str, Tuple[str, ...]]] = {}
        self.rust_files: Dict[Tuple[str, Tuple[str, ...]], str] = {}
        for p in self.paths:
            if not p.endswith(".rs"):
                continue
            crate_dir = self._rust_crate_dir(p)
            rel = p[len(crate_dir) + 1:] if crate_dir else p
            parts = rel[:-3].split("/")
            is_crate_root = False
            if parts and parts[0] == "src":
                parts = parts[1:]
                if parts in ((["lib"], ["main"])):
                    is_crate_root = True
                if parts and parts[0] == "bin" and len(parts) == 2:
                    parts = []  # src/bin/x.rs is its own crate root
            elif len(parts) == 1:
                parts = []  # build.rs: its own crate root
            else:
                # tests/x.rs, examples/x.rs, benches/x.rs are crate roots; tests/common/mod.rs -> ["common"]
                parts = parts[1:] if len(parts) > 2 else []
            if parts and parts[-1] in ("mod", "lib", "main"):
                parts = parts[:-1]
            key = (crate_dir, tuple(parts))
            self.rust_mod_of[p] = key
            if is_crate_root or key not in self.rust_files:
                self.rust_files[key] = p  # src/lib.rs / src/main.rs win for the crate root

    def _rust_crate_dir(self, path: str) -> str:
        best = ""
        for d in self.rust_crates:
            if d == "" or path.startswith(d + "/"):
                if len(d) >= len(best):
                    best = d
        return best

    def _rust(self, path: str, ref: dict) -> List[str]:
        crate_dir, modpath = self.rust_mod_of.get(path, (self._rust_crate_dir(path), ()))
        stem = PurePosixPath(path).stem
        is_root_like = stem in ("mod", "lib", "main") or "/bin/" in path or not modpath

        if ref["kind"] == "mod":
            name = ref["module"]
            here = posixpath.dirname(path) if is_root_like else posixpath.join(posixpath.dirname(path), stem)
            for cand in (posixpath.join(here, f"{name}.rs"), posixpath.join(here, name, "mod.rs")):
                if cand in self.paths:
                    return [cand]
            return []

        segs = [s for s in ref["module"].split("::") if s]
        if not segs:
            return []
        head = segs[0]
        if head == "crate":
            base, segs = (crate_dir, ()), segs[1:]
        elif head == "self":
            base, segs = (crate_dir, modpath), segs[1:]
        elif head == "super":
            up = modpath
            while segs and segs[0] == "super":
                up = up[:-1]
                segs = segs[1:]
            base = (crate_dir, up)
        elif head in self.rust_crate_by_name:  # another crate in this workspace
            base, segs = (self.rust_crate_by_name[head], ()), segs[1:]
        elif (crate_dir, modpath + (head,)) in self.rust_files:  # 2018-style local module path
            base = (crate_dir, modpath)
        else:
            return []  # external crate (std, serde, ...)

        segs = [s for s in segs if s != "*"]
        for k in range(len(segs), -1, -1):  # longest module prefix that is a file
            f = self.rust_files.get((base[0], tuple(base[1]) + tuple(segs[:k])))
            if f:
                return [f]
        return []

    # ------------------------------------------------------------------ C++
    def _build_cpp_index(self):
        self.cpp_by_name: Dict[str, List[str]] = defaultdict(list)
        for p in self.paths:
            if p.endswith(CPP_EXTS):
                self.cpp_by_name[PurePosixPath(p).name].append(p)

    def _cpp(self, path: str, ref: dict) -> Optional[str]:
        inc = ref["module"].replace("\\", "/")
        if ref["kind"] == "include":
            local = posixpath.normpath(posixpath.join(posixpath.dirname(path), inc))
            if local in self.paths:
                return local
        cands = [c for c in self.cpp_by_name.get(PurePosixPath(inc).name, [])
                 if c == inc or c.endswith("/" + inc)]
        if not cands:
            return None
        if ref["kind"] == "include_system" and "/" not in inc and len(cands) > 1:
            return None  # <config.h>-style ambiguity: likely a system header
        return _closest(cands, path)
