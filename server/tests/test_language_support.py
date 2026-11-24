"""
End-to-end language support tests: one small, realistic project per language, run through
CodeAnalyzer.analyze() (symbols, imports -> file dependency graph, call graph, manifests,
frameworks, databases, entry points, build/run commands) and the chunker.

Run:  cd server && python -m pytest tests -q
"""
import textwrap
from pathlib import Path

import pytest

from app.services import source_parser
from app.services.code_analyzer import CodeAnalyzer
from app.services.code_chunker import CodeChunker

pytestmark = pytest.mark.skipif(not source_parser.available(), reason="tree-sitter not installed")


def make_project(root: Path, files: dict) -> Path:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")
    return root


def analyze(root: Path) -> dict:
    return CodeAnalyzer(str(root)).analyze()


def edges(result: dict, source: str) -> list:
    return result["call_graph"].get(source, {}).get("calls", [])


def system(result: dict, ecosystem: str) -> dict:
    return next(s for s in result["build_systems"] if s["ecosystem"] == ecosystem)


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------
@pytest.fixture
def python_project(tmp_path):
    return make_project(tmp_path, {
        "pyproject.toml": """
            [project]
            name = "demo"
            dependencies = ["fastapi>=0.110", "httpx", "SQLAlchemy[asyncio]~=2.0"]
            [project.optional-dependencies]
            dev = ["pytest>=8"]
            [project.scripts]
            demo = "demo.cli:main"
        """,
        "uv.lock": "",
        "src/demo/__init__.py": "from .core import Engine\n",
        "src/demo/core.py": """
            from .utils import helper

            class Engine:
                # Runs the thing
                def run(self):
                    return helper() + self.step()

                def step(self):
                    return 1
        """,
        "src/demo/utils.py": "def helper():\n    return 1\n",
        "src/demo/cli.py": """
            from demo.core import Engine

            def main():
                Engine().run()
        """,
        "src/demo/api.py": """
            from fastapi import FastAPI
            app = FastAPI()

            @app.get("/items")
            def list_items():
                return []
        """,
        "tests/test_core.py": "from demo.core import Engine\n\ndef test_run():\n    assert Engine().run() == 2\n",
    })


def test_python(python_project):
    r = analyze(python_project)
    core = r["files"]["src/demo/core.py"]
    assert core["classes"] == ["Engine"] and set(core["functions"]) == {"run", "step"}
    run = next(s for s in core["symbols"] if s["name"] == "run")
    assert run["parent"] == "Engine" and run["start_line"] == 4  # includes the comment above

    deps = r["file_dependencies"]
    assert deps["src/demo/core.py"]["resolved"] == ["src/demo/utils.py"]          # relative import
    assert deps["src/demo/__init__.py"]["resolved"] == ["src/demo/core.py"]
    assert deps["src/demo/cli.py"]["resolved"] == ["src/demo/core.py"]            # src-layout absolute
    assert "fastapi" in deps["src/demo/api.py"]["external"]

    assert "src/demo/utils.py::helper" in edges(r, "src/demo/core.py::Engine.run")
    assert "src/demo/core.py::Engine.step" in edges(r, "src/demo/core.py::Engine.run")  # self.step()
    assert "src/demo/core.py::Engine.run" in edges(r, "src/demo/cli.py::main")    # imported member call

    py = r["dependencies"]["python"]
    assert py["pyproject.toml"] == ["fastapi", "httpx", "SQLAlchemy"]
    assert "pytest" in py["pyproject.toml (dev/optional)"]
    assert "FastAPI" in r["frameworks"]["backend"]
    assert "src/demo/cli.py" in r["entry_points"]                                  # [project.scripts]

    s = system(r, "Python")
    assert s["tool"] == "uv" and s["install"] == ["uv sync"]
    assert s["run"] == ["uv run demo"] and s["test"] == ["uv run pytest"]


# ---------------------------------------------------------------------------
# JavaScript / TypeScript
# ---------------------------------------------------------------------------
@pytest.fixture
def ts_project(tmp_path):
    return make_project(tmp_path, {
        "package.json": """
            {"name": "web", "scripts": {"dev": "vite", "build": "tsc && vite build", "test": "vitest"},
             "dependencies": {"react": "^18", "react-dom": "^18"},
             "devDependencies": {"vite": "^5", "vitest": "^1", "typescript": "^5"}}
        """,
        "pnpm-lock.yaml": "",
        "tsconfig.json": """
            {
              // JSONC: comments and trailing commas are allowed
              "compilerOptions": { "baseUrl": ".", "paths": { "@lib/*": ["src/lib/*"] }, },
            }
        """,
        "src/main.tsx": """
            import { createRoot } from 'react-dom/client';
            import App from './App.js';
            createRoot(document.getElementById('root')!).render(<App />);
        """,
        "src/App.tsx": """
            import { format } from '@lib/format';
            /** The root component */
            export default function App() {
              return <Header title={format('x')} />;
            }
            function Header({ title }: { title: string }) { return <h1>{title}</h1>; }
        """,
        "src/lib/format.ts": """
            export const format = (s: string) => s.toUpperCase();
            export interface Fmt { x: number }
            export class Formatter { fmt(s: string) { return format(s); } }
        """,
        "src/legacy.js": "const { format } = require('./lib/format');\nmodule.exports = () => format('y');\n",
    })


def test_typescript(ts_project):
    r = analyze(ts_project)
    fmt = r["files"]["src/lib/format.ts"]
    assert set(fmt["functions"]) == {"format", "fmt"} and set(fmt["classes"]) == {"Fmt", "Formatter"}
    app_sym = next(s for s in r["files"]["src/App.tsx"]["symbols"] if s["name"] == "App")
    assert app_sym["start_line"] == 2                                              # JSDoc included

    deps = r["file_dependencies"]
    assert deps["src/main.tsx"]["resolved"] == ["src/App.tsx"]                     # './App.js' -> App.tsx
    assert deps["src/App.tsx"]["resolved"] == ["src/lib/format.ts"]                # tsconfig paths
    assert deps["src/legacy.js"]["resolved"] == ["src/lib/format.ts"]              # require()
    assert "react-dom/client" in deps["src/main.tsx"]["external"]

    assert "src/App.tsx::Header" in edges(r, "src/App.tsx::App")                   # JSX <Header />
    assert "src/lib/format.ts::format" in edges(r, "src/App.tsx::App")
    assert "src/lib/format.ts::format" in edges(r, "src/lib/format.ts::Formatter.fmt")

    assert {"React", "Vite"} <= set(r["frameworks"]["frontend"])
    assert r["entry_points"][0] == "src/main.tsx"                                  # createRoot()
    s = system(r, "JavaScript/TypeScript")
    assert s["tool"] == "pnpm" and s["run"] == ["pnpm run dev"] and s["test"] == ["pnpm run test"]


# ---------------------------------------------------------------------------
# Java (Maven + Spring Boot)
# ---------------------------------------------------------------------------
@pytest.fixture
def java_project(tmp_path):
    return make_project(tmp_path, {
        "pom.xml": """
            <project xmlns="http://maven.apache.org/POM/4.0.0">
              <parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId></parent>
              <dependencies>
                <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-web</artifactId></dependency>
                <dependency><groupId>org.postgresql</groupId><artifactId>postgresql</artifactId></dependency>
              </dependencies>
            </project>
        """,
        "mvnw": "",
        "src/main/java/com/acme/App.java": """
            package com.acme;
            import org.springframework.boot.SpringApplication;
            @SpringBootApplication
            public class App {
                public static void main(String[] args) { SpringApplication.run(App.class, args); }
            }
        """,
        "src/main/java/com/acme/web/OwnerController.java": """
            package com.acme.web;
            import com.acme.repo.OwnerRepository;
            import java.util.List;
            @RestController
            public class OwnerController {
                private final OwnerRepository repo;
                @GetMapping("/owners")
                public List<Owner> list() { return repo.findAll(); }
                public Owner make() { return new Owner(); }
            }
        """,
        "src/main/java/com/acme/web/Owner.java": "package com.acme.web;\npublic class Owner {\n    public Owner() {}\n}\n",
        "src/main/java/com/acme/repo/OwnerRepository.java": """
            package com.acme.repo;
            public interface OwnerRepository { java.util.List findAll(); }
        """,
    })


def test_java(java_project):
    r = analyze(java_project)
    ctl = "src/main/java/com/acme/web/OwnerController.java"
    deps = r["file_dependencies"][ctl]
    assert "src/main/java/com/acme/repo/OwnerRepository.java" in deps["resolved"]  # import
    assert "src/main/java/com/acme/web/Owner.java" in deps["resolved"]             # same package, no import
    assert "java.util.List" in deps["external"]

    assert "src/main/java/com/acme/repo/OwnerRepository.java::OwnerRepository.findAll" \
        in edges(r, f"{ctl}::OwnerController.list")
    assert "src/main/java/com/acme/web/Owner.java::Owner.Owner" \
        in edges(r, f"{ctl}::OwnerController.make")                                # new Owner()

    assert "org.springframework.boot:spring-boot-starter-web" in r["dependencies"]["java"]["pom.xml"]
    assert "Spring Boot" in r["frameworks"]["backend"] and "PostgreSQL" in r["databases"]
    assert r["entry_points"] == ["src/main/java/com/acme/App.java"]
    s = system(r, "Java")
    assert s["tool"] == "maven" and s["run"] == ["./mvnw spring-boot:run"] and s["test"] == ["./mvnw test"]


# ---------------------------------------------------------------------------
# Rust (Cargo workspace)
# ---------------------------------------------------------------------------
@pytest.fixture
def rust_project(tmp_path):
    return make_project(tmp_path, {
        "Cargo.toml": '[workspace]\nmembers = ["crates/core", "crates/cli"]\n',
        "crates/core/Cargo.toml": """
            [package]
            name = "demo-core"
            [dependencies]
            serde = { version = "1", features = ["derive"] }
            sqlx = { version = "0.7", features = ["postgres", "runtime-tokio"] }
        """,
        "crates/core/src/lib.rs": "pub mod config;\npub use config::Config;\n",
        "crates/core/src/config.rs": """
            /// Application configuration.
            #[derive(Debug)]
            pub struct Config<'a> { pub name: &'a str }

            impl<'a> Config<'a> {
                pub fn new() -> Self { Config { name: load() } }
            }

            fn load() -> &'static str { "}" }
        """,
        "crates/cli/Cargo.toml": """
            [package]
            name = "demo-cli"
            [dependencies]
            demo-core = { path = "../core" }
            axum = "0.7"
            tokio = { version = "1", features = ["full"] }
        """,
        "crates/cli/src/main.rs": """
            use demo_core::config::Config;
            mod routes;

            fn main() {
                let c = Config::new();
                routes::serve(c);
            }
        """,
        "crates/cli/src/routes.rs": """
            use axum::{routing::get, Router};

            pub fn serve(_c: demo_core::Config) {
                let _app: Router = Router::new().route("/health", get(health));
            }

            async fn health() -> &'static str { "ok" }
        """,
    })


def test_rust(rust_project):
    r = analyze(rust_project)
    cfg = r["files"]["crates/core/src/config.rs"]
    assert cfg["classes"] == ["Config"] and set(cfg["functions"]) == {"new", "load"}
    new = next(s for s in cfg["symbols"] if s["name"] == "new")
    assert new["parent"] == "Config"
    struct = next(s for s in cfg["symbols"] if s["name"] == "Config")
    assert struct["start_line"] == 1                                               # /// + #[derive] included

    deps = r["file_dependencies"]
    assert deps["crates/core/src/lib.rs"]["resolved"] == ["crates/core/src/config.rs"]    # mod config;
    assert set(deps["crates/cli/src/main.rs"]["resolved"]) == {
        "crates/core/src/config.rs",                                               # workspace crate path
        "crates/cli/src/routes.rs",                                                # mod routes;
    }
    assert any(e.startswith("axum") for e in deps["crates/cli/src/routes.rs"]["external"])

    assert "crates/core/src/config.rs::Config.new" in edges(r, "crates/cli/src/main.rs::main")  # Config::new()
    assert "crates/cli/src/routes.rs::serve" in edges(r, "crates/cli/src/main.rs::main")  # routes::serve()
    assert "crates/core/src/config.rs::load" in edges(r, "crates/core/src/config.rs::Config.new")

    rust = r["dependencies"]["rust"]
    assert rust["crates/core/Cargo.toml"] == ["serde", "sqlx"]
    assert {"Axum", "Tokio"} <= set(r["frameworks"]["backend"]) and "PostgreSQL" in r["databases"]
    assert {"crates/cli/src/main.rs", "crates/core/src/lib.rs"} <= set(r["entry_points"])
    assert "crates/core/src/config.rs" not in r["entry_points"]
    s = system(r, "Rust")
    assert s["build"] == ["cargo build --workspace"] and s["run"] == ["cargo run -p demo-cli"]


# ---------------------------------------------------------------------------
# C++ (CMake + Conan)
# ---------------------------------------------------------------------------
@pytest.fixture
def cpp_project(tmp_path):
    return make_project(tmp_path, {
        "CMakeLists.txt": """
            cmake_minimum_required(VERSION 3.20)
            project(demo CXX)
            find_package(fmt REQUIRED)
            find_package(SQLite3)
            add_subdirectory(app)
            enable_testing()
        """,
        "conanfile.txt": "[requires]\nfmt/10.2.1\nspdlog/1.12.0\n[generators]\nCMakeDeps\n",
        "include/demo/math.hpp": """
            #pragma once
            namespace demo {
            /** Adds numbers. */
            template <typename T> class Calc { public: T twice(T v) { return add(v, v); } T add(T a, T b); };
            int square(int x);
            }
        """,
        "src/math.cpp": """
            #include "demo/math.hpp"
            namespace demo {
            int square(int x) { Calc<int> c; return c.add(x, 0) * x; }
            template <typename T> T Calc<T>::add(T a, T b) { return a + b; }
            }
        """,
        "app/CMakeLists.txt": "add_executable(demo_app main.cpp)\nadd_executable(demo_tests tests.cpp)\n",
        "app/main.cpp": """
            #include <demo/math.hpp>
            #include <vector>
            int main() { return demo::square(3); }
        """,
    })


def test_cpp(cpp_project):
    r = analyze(cpp_project)
    math_cpp = r["files"]["src/math.cpp"]
    add = next(s for s in math_cpp["symbols"] if s["name"] == "add")
    assert add["parent"] == "Calc" and add["kind"] == "method"                     # out-of-class template method
    assert r["files"]["include/demo/math.hpp"]["classes"] == ["Calc"]

    deps = r["file_dependencies"]
    assert deps["src/math.cpp"]["resolved"] == ["include/demo/math.hpp"]           # "demo/math.hpp" by suffix
    assert deps["app/main.cpp"]["resolved"] == ["include/demo/math.hpp"]           # <demo/math.hpp>
    assert deps["app/main.cpp"]["external"] == ["vector"]

    assert "src/math.cpp::square" in edges(r, "app/main.cpp::main")                # demo::square()
    assert "src/math.cpp::Calc.add" in edges(r, "src/math.cpp::square")            # c.add()
    assert r["entry_points"] == ["app/main.cpp"]

    cpp = r["dependencies"]["cpp"]
    assert cpp["CMakeLists.txt"] == ["fmt", "SQLite3"] and cpp["conanfile.txt"] == ["fmt", "spdlog"]
    assert "SQLite" in r["databases"]
    s = system(r, "C/C++")
    assert s["install"] == ["conan install . --output-folder=build --build=missing"]
    assert s["build"][0].endswith("-DCMAKE_TOOLCHAIN_FILE=build/conan_toolchain.cmake")
    assert s["run"] == ["./build/app/demo_app"] and s["test"] == ["ctest --test-dir build --output-on-failure"]


# ---------------------------------------------------------------------------
# Chunker uses parsed symbols
# ---------------------------------------------------------------------------
def test_chunks_follow_parsed_symbols():
    lines = ["/** Big service. */", "export class Service {"]
    for i in range(12):
        lines += [f"  /** Does step {i}. */", f"  step{i}(x: number) {{"] + ["    x += 1;"] * 6 + ["    return x;", "  }"]
    lines += ["}"]
    content = "\n".join(lines)
    parsed = source_parser.parse_source(content, ".ts")
    chunks = CodeChunker().chunk_file("svc.ts", content, "TypeScript", [s.to_dict() for s in parsed.symbols])

    methods = [c for c in chunks if c.kind == "method"]
    assert len(methods) == 12 and [m.symbol for m in methods[:2]] == ["Service.step0", "Service.step1"]
    assert methods[1].code.lstrip().startswith("/** Does step 1. */")              # doc comment kept
    assert chunks[0].start_line == 1 and "export class Service" in chunks[0].code  # tiny header merged in
    assert chunks[-1].end_line == len(lines)                                       # whole file covered
