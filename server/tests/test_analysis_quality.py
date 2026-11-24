"""
Regression tests for analysis quality: what the tool says a repository is, and the call graph,
architecture and quick start it draws from it.

  Q1  database nodes only for real database clients / ORMs; no call edges across languages;
      generated API clients (`url: '/api/...'`) linked to backend routes
  Q2  tests, examples, docs and generated files never decide frameworks, databases, key files,
      entry points, AI report inputs or the default call-graph view
  Q3  architecture layers for full-stack repos, adaptive component depth, collapsed tests
  Q5  methods of different classes are separate call-graph nodes
  Q7  workspace-aware quick start commands
"""
import json
import textwrap
from pathlib import Path

import pytest

from app.services import path_classifier, source_parser
from app.services.ai_analyzer import AIAnalyzer
from app.services.code_analyzer import CodeAnalyzer
from app.services.code_chunker import CodeChunk
from app.services.rag_retriever import RepoRetriever

pytestmark = pytest.mark.skipif(not source_parser.available(), reason="tree-sitter not installed")


def make_project(root: Path, files: dict) -> Path:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")
    return root


def analyze(root: Path) -> dict:
    return CodeAnalyzer(str(root)).analyze()


def db_nodes(result: dict) -> dict:
    return {k: v for k, v in result["call_graph"].items() if v.get("type") == "db-query"}


# ---------------------------------------------------------------------------
# Shared path classifier
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("path, category", [
    ("src/flask/app.py", "primary"),
    ("backend/app/api/routes/items.py", "primary"),
    ("tests/test_basic.py", "test"),
    ("backend/tests/api/test_users.py", "test"),
    ("src/utils/format.test.ts", "test"),
    ("src/components/Button.spec.tsx", "test"),
    ("pkg/server/handler_test.go", "test"),
    ("src/main/java/com/acme/OwnerTest.java", "test"),
    ("conftest.py", "test"),
    ("examples/celery/src/task_app/__init__.py", "example"),
    ("examples/tutorial/tests/test_auth.py", "example"),     # the outermost directory decides
    ("docs/conf.py", "docs"),
    ("docs_src/tutorial/main.py", "docs"),
    ("frontend/src/client/sdk.gen.ts", "generated"),
    ("frontend/src/routeTree.gen.ts", "generated"),
    ("proto/user_pb2.py", "generated"),
    ("static/vendor/jquery.min.js", "generated"),
    ("package-lock.json", "generated"),
    ("uv.lock", "generated"),
    ("src/components/Button.stories.tsx", "example"),
])
def test_classify_path(path, category):
    assert path_classifier.classify_path(path) == category


def test_language_family():
    assert path_classifier.language_family("a/b.py") == "python"
    assert path_classifier.language_family("a/b.tsx") == path_classifier.language_family("a/b.mjs") == "javascript"
    assert path_classifier.language_family("a/B.java") == path_classifier.language_family("a/b.kt") == "jvm"
    assert path_classifier.language_family("a/b.hpp") == "cpp"
    assert path_classifier.language_family("README.md") is None


# ---------------------------------------------------------------------------
# Q1: database nodes and cross-language edges
# ---------------------------------------------------------------------------
def test_generic_method_calls_are_not_database_queries(tmp_path):
    r = analyze(make_project(tmp_path, {
        "pyproject.toml": '[project]\nname = "signer"\ndependencies = []\n',
        "src/signer/core.py": """
            import hashlib, hmac

            def derive_key(secret, salt):
                mac = hmac.new(secret, digestmod=hashlib.sha1)
                mac.update(salt)
                return mac.digest()

            def merge(config, extra):
                config.update(extra)
                found = [x for x in filter(None, extra)]
                return config.get("debug"), found

            def label():
                return "Select a file from the list"
        """,
        "src/signer/web.js": """
            export function pick(items) {
              const first = items.find(i => i.ok);
              const copy = Object.create(null);
              return items.filter(Boolean).concat([first, copy]);
            }
        """,
    }))
    assert db_nodes(r) == {}
    assert all(v["type"] != "service" for v in r["call_graph"].values())


def test_orm_calls_are_database_queries(tmp_path):
    r = analyze(make_project(tmp_path, {
        "pyproject.toml": '[project]\nname = "api"\ndependencies = ["fastapi", "sqlmodel"]\n',
        "app/crud.py": """
            from sqlmodel import Session, select

            def get_user(session: Session, email: str):
                return session.exec(select(User).where(User.email == email)).first()

            def create_user(session: Session, user):
                session.add(user)
                session.commit()
                return user
        """,
        "app/raw.py": """
            def count_users(cursor):
                cursor.execute("SELECT count(*) FROM users")
                return cursor.fetchone()
        """,
    }))
    db = db_nodes(r)
    assert "app/crud.py::get_user" in db["db-query::QUERY"]["called_by"]
    assert "app/crud.py::create_user" in db["db-query::INSERT"]["called_by"]
    assert "app/raw.py::count_users" in db["db-query::SELECT"]["called_by"]
    assert r["call_graph"]["app/crud.py::create_user"]["type"] == "service"


def test_django_orm_and_prisma_are_database_queries(tmp_path):
    r = analyze(make_project(tmp_path, {
        "shop/views.py": """
            from .models import Order

            def open_orders(request):
                return Order.objects.filter(open=True)
        """,
        "web/package.json": '{"name": "web", "dependencies": {"@prisma/client": "5"}}',
        "web/src/users.ts": """
            import { PrismaClient } from '@prisma/client';
            const prisma = new PrismaClient();
            export async function removeUser(id: string) {
              return prisma.user.delete({ where: { id } });
            }
        """,
    }))
    db = db_nodes(r)
    assert "shop/views.py::open_orders" in db["db-query::SELECT"]["called_by"]
    assert "web/src/users.ts::removeUser" in db["db-query::DELETE"]["called_by"]


def test_calls_never_resolve_across_languages(tmp_path):
    r = analyze(make_project(tmp_path, {
        "backend/app/routes.py": """
            from app.models import User

            def create_user(data):
                return User(**data)
        """,
        "backend/app/models.py": "class User:\n    pass\n",
        "frontend/src/User.tsx": "export function User() {\n  return <div />;\n}\n",
        "frontend/src/Page.tsx": "import { User } from './User';\nexport function Page() {\n  return <User />;\n}\n",
    }))
    cg = r["call_graph"]
    assert cg["backend/app/routes.py::create_user"]["calls"] == []
    assert cg["frontend/src/Page.tsx::Page"]["calls"] == ["frontend/src/User.tsx::User"]


def test_generated_api_client_links_to_backend_routes(tmp_path):
    r = analyze(make_project(tmp_path, {
        "backend/pyproject.toml": '[project]\nname = "app"\ndependencies = ["fastapi"]\n',
        "backend/app/main.py": """
            from fastapi import FastAPI
            from app.api.main import api_router

            app = FastAPI()
            app.include_router(api_router, prefix=settings.API_V1_STR)
        """,
        "backend/app/api/routes/users.py": """
            from fastapi import APIRouter

            router = APIRouter(prefix="/users", tags=["users"])

            @router.get("/me")
            def read_user_me():
                return {}

            @router.get("/{user_id}")
            def read_user_by_id(user_id: int):
                return {}

            @router.post("/")
            def create_user(user: dict):
                return user
        """,
        "frontend/package.json": '{"name": "web", "dependencies": {"react": "18"}}',
        "frontend/src/client/sdk.gen.ts": """
            import { client } from './client.gen';
            export class UsersService {
                public static readUserById(options: Options) {
                    return (options.client ?? client).get<Res, Err>({
                        responseType: 'json',
                        url: '/api/v1/users/{user_id}',
                        ...options
                    });
                }
                public static createUser(options: Options) {
                    return __request(OpenAPI, {
                        method: 'POST',
                        url: '/api/v1/users/',
                        body: options.body
                    });
                }
            }
        """,
    }))
    cg = r["call_graph"]
    by_id = cg["api-call::GET::/api/v1/users/{user_id}"]
    assert by_id["called_by"] == ["frontend/src/client/sdk.gen.ts::UsersService.readUserById"]
    assert by_id["calls"] == ["backend/app/api/routes/users.py::read_user_by_id"]   # not users/me
    assert cg["api-call::POST::/api/v1/users/"]["calls"] == ["backend/app/api/routes/users.py::create_user"]
    assert cg["backend/app/api/routes/users.py::read_user_by_id"]["type"] == "route"


# ---------------------------------------------------------------------------
# Q2: examples, tests and generated files do not decide what the repo is
# ---------------------------------------------------------------------------
@pytest.fixture
def library_with_examples(tmp_path):
    files = {
        "pyproject.toml": '[project]\nname = "webfw"\ndependencies = ["werkzeug", "jinja2"]\n',
        "src/webfw/__init__.py": "from .app import App\n",
        "src/webfw/app.py": """
            from .routing import Map
            from .config import Config

            class App:
                def __init__(self):
                    self.config = Config()
                    self.url_map = Map()

                def run(self):
                    return self.url_map.bind()
        """,
        "src/webfw/routing.py": "class Map:\n    def bind(self):\n        return 1\n",
        "src/webfw/config.py": "class Config(dict):\n    def from_file(self, path):\n        return path\n",
        "examples/celery/pyproject.toml": '[project]\nname = "task-app"\ndependencies = ["webfw", "celery[redis]", "redis"]\n',
        "examples/celery/src/task_app/__init__.py": """
            from celery import Celery
            from webfw import App

            def create_app():
                app = App()
                return Celery(app)
        """,
        "examples/celery/src/task_app/tasks.py": """
            from celery import shared_task

            class AddTask:
                def run(self, a, b):
                    return a + b

            class MulTask:
                def run(self, a, b):
                    return a * b
        """,
        "docs/conf.py": "project = 'webfw'\n",
        "web/src/client/sdk.gen.ts": """
            import { client } from './client.gen';
            export class Api {
              static get() { return client.get(); }
            }
            export class ItemsService {
              static list() { return client.get(); }
            }
            export class UsersService {
              static me() { return client.get(); }
            }
        """,
    }
    for i in range(6):
        files[f"tests/test_feature_{i}.py"] = "\n".join(
            ["from webfw import App", ""] + [f"def test_{i}_{j}():\n    assert App().run()\n" for j in range(30)])
    return make_project(tmp_path, files)


def test_examples_do_not_decide_frameworks_or_databases(library_with_examples):
    r = analyze(library_with_examples)
    assert "Celery" not in r["frameworks"]["backend"]
    assert "Redis" not in r["databases"]
    # ...but the dependency view still lists every manifest
    assert "examples/celery/pyproject.toml" in r["dependencies"]["python"]


def test_key_files_and_entry_points_skip_secondary_code(library_with_examples):
    r = analyze(library_with_examples)
    assert r["key_files"] and all(path_classifier.is_primary(p) for p in r["key_files"])
    assert "web/src/client/sdk.gen.ts" not in r["key_files"]                     # generated
    assert "examples/celery/src/task_app/tasks.py" not in r["key_files"]           # example
    assert not any(p.startswith(("examples/", "tests/", "docs/")) for p in r["entry_points"])


def test_ai_report_inputs_come_from_primary_code(library_with_examples):
    r = analyze(library_with_examples)
    context = json.loads(AIAnalyzer({
        "frameworks": r["frameworks"],
        "databases": r["databases"],
        "entryPoints": r["entry_points"] + ["tests/test_feature_0.py"],
        "complexity": {"fileList": [{"file": p, "lines": m["lines"], "functions": m["functions"],
                                     "classes": m["classes"]} for p, m in r["files"].items()]},
        "file_dependencies": r["file_dependencies"],
    })._build_condensed_context())
    assert context["core_files"] and all(path_classifier.is_primary(f["path"]) for f in context["core_files"])
    assert context["architecture_hints"] and all(h.startswith("src/") for h in context["architecture_hints"])
    assert context["entry_points"] and all(path_classifier.is_primary(p) for p in context["entry_points"])


def test_call_graph_nodes_carry_their_category(library_with_examples):
    cg = analyze(library_with_examples)["call_graph"]
    assert cg["src/webfw/app.py::App.run"]["category"] == "primary"
    assert cg["tests/test_feature_0.py::test_0_0"]["category"] == "test"
    assert cg["examples/celery/src/task_app/tasks.py::AddTask.run"]["category"] == "example"
    assert cg["web/src/client/sdk.gen.ts::Api.get"]["category"] == "generated"


# ---------------------------------------------------------------------------
# Q3: architecture view
# ---------------------------------------------------------------------------
@pytest.fixture
def fullstack_project(tmp_path):
    files = {
        "backend/pyproject.toml": '[project]\nname = "app"\ndependencies = ["fastapi", "sqlmodel", "psycopg"]\n',
        "backend/app/main.py": "from fastapi import FastAPI\nfrom app.api.main import api_router\napp = FastAPI()\n",
        "backend/app/models.py": "class User:\n    pass\n",
        "backend/app/crud.py": "from app.models import User\n\ndef create_user():\n    return User()\n",
        "backend/app/api/main.py": "from app.api.routes import items, users\napi_router = None\n",
        "backend/app/api/deps.py": "def get_db():\n    return None\n",
        "backend/app/api/routes/__init__.py": "",
        "backend/app/api/routes/items.py": "from app import crud\n\ndef read_items():\n    return crud.create_user()\n",
        "backend/app/api/routes/users.py": "from app import crud\n\ndef read_users():\n    return crud.create_user()\n",
        "backend/app/core/config.py": "class Settings:\n    pass\n",
        "backend/app/core/security.py": "def hash_password(p):\n    return p\n",
        "backend/app/core/db.py": "from app.core.config import Settings\n\ndef init_db():\n    return Settings()\n",
        "backend/app/alembic/env.py": "def run():\n    pass\n",
        "backend/app/alembic/versions/0001_init.py": "def upgrade():\n    pass\n",
        "backend/tests/conftest.py": "import pytest\n",
        "backend/tests/api/test_items.py": "from app.api.routes.items import read_items\n\ndef test_items():\n    read_items()\n",
        "backend/tests/crud/test_user.py": "from app.crud import create_user\n\ndef test_user():\n    create_user()\n",
        "frontend/package.json": json.dumps({"name": "web", "scripts": {"dev": "vite"},
                                             "dependencies": {"react": "18", "react-dom": "18"},
                                             "devDependencies": {"vite": "5", "tailwindcss": "3"}}),
        "frontend/src/main.tsx": "import { App } from './app/App';\ncreateRoot(document.body).render(<App />);\n",
        "frontend/src/app/App.tsx": "export function App() {\n  return <div />;\n}\n",
        "frontend/src/app/routes.tsx": "export function Routes() {\n  return <div />;\n}\n",
        "frontend/tests/login.spec.ts": "test('login', () => {});\n",
    }
    for name in ("Button", "Card", "Dialog", "Input", "Menu", "Table", "Tabs", "Toast"):
        files[f"frontend/src/components/ui/{name}.tsx"] = f"export function {name}() {{\n  return <div />;\n}}\n"
    for name in ("AddItem", "EditItem", "DeleteItem"):
        files[f"frontend/src/components/Items/{name}.tsx"] = f"export function {name}() {{\n  return <div />;\n}}\n"
    return make_project(tmp_path, files)


def test_fullstack_architecture_layers(fullstack_project):
    r = analyze(fullstack_project)
    nodes = {n["id"]: n for n in r["architecture"]["nodes"]}

    backend = {i: n for i, n in nodes.items() if i.startswith("backend/") and n["category"] == "primary"}
    assert backend and all(n["layer"] != "frontend" for n in backend.values())   # `/app` is not `src/app`
    assert all("React" not in n["frameworks"] for n in backend.values())
    assert nodes["backend/app/api"]["layer"] == "api" and "FastAPI" in nodes["backend/app/api"]["frameworks"]
    assert nodes["backend/app/core"]["layer"] == "config"
    assert nodes["backend/app/alembic"]["layer"] == "data"
    assert nodes["backend/app"]["layer"] == "services"

    frontend = [n for i, n in nodes.items() if i.startswith("frontend/") and n["category"] == "primary"]
    assert frontend and all(n["layer"] == "frontend" for n in frontend)
    assert all("FastAPI" not in n["frameworks"] for n in frontend)
    assert any("React" in n["frameworks"] for n in frontend)

    # Tests collapse into one component per sub-project
    assert nodes["backend/tests"]["layer"] == "tests" and nodes["backend/tests"]["file_count"] == 3
    assert nodes["frontend/tests"]["layer"] == "tests"
    assert not any(i.startswith("backend/tests/") for i in nodes)


def test_architecture_stays_readable_on_large_repos(tmp_path):
    files = {"pyproject.toml": '[project]\nname = "big"\n'}
    for pkg in range(30):
        for sub in range(4):
            for mod in range(3):
                files[f"big/pkg{pkg}/sub{sub}/mod{mod}.py"] = f"def f{mod}():\n    return {mod}\n"
        files[f"tests/pkg{pkg}/test_pkg.py"] = "def test_x():\n    pass\n"
    r = analyze(make_project(tmp_path, files))
    components = [n for n in r["architecture"]["nodes"] if n["type"] == "component"]
    assert len(components) <= 20
    assert sum(n["file_count"] for n in components) == len(r["files"])
    tests = [n for n in components if n["layer"] == "tests"]
    assert len(tests) == 1 and tests[0]["file_count"] == 30


# ---------------------------------------------------------------------------
# Q5: methods of different classes stay apart
# ---------------------------------------------------------------------------
def test_same_named_methods_are_separate_nodes(tmp_path):
    r = analyze(make_project(tmp_path, {
        "sessions.py": """
            class SessionInterface:
                def open_session(self, app):
                    return None

                def make_null_session(self, app):
                    return self.open_session(app)


            class SecureCookieSessionInterface(SessionInterface):
                def open_session(self, app):
                    return self.load(app)

                def load(self, app):
                    return app


            def __getattr__(name):
                return name


            def open_session(app):
                return SecureCookieSessionInterface().open_session(app)
        """,
    }))
    cg = r["call_graph"]
    base, secure = "sessions.py::SessionInterface.open_session", "sessions.py::SecureCookieSessionInterface.open_session"
    assert base in cg and secure in cg and "sessions.py::open_session" in cg
    assert cg["sessions.py::SessionInterface.make_null_session"]["calls"] == [base]      # self -> own class
    assert cg[secure]["calls"] == ["sessions.py::SecureCookieSessionInterface.load"]
    assert cg[base]["calls"] == []                                                       # nothing merged in
    assert cg["sessions.py::SessionInterface.make_null_session"]["name"] == "SessionInterface.make_null_session"


def test_retriever_call_info_uses_class_qualified_ids(tmp_path):
    r = analyze(make_project(tmp_path, {
        "svc.py": """
            class A:
                def run(self):
                    return self.step()

                def step(self):
                    return 1


            class B:
                def run(self):
                    return 2
        """,
    }))
    retriever = RepoRetriever(None, r["call_graph"], r["files"])
    chunk = lambda symbol: CodeChunk(id="x", file="svc.py", language="Python", symbol=symbol, kind="method",
                                     start_line=1, end_line=2, code="")
    assert retriever._call_info(chunk("A.run")) == "calls: A.step"
    assert retriever._call_info(chunk("A.step")) == "called by: A.run"
    assert retriever._call_info(chunk("B.run")) == ""


# ---------------------------------------------------------------------------
# Q7: workspaces / monorepos in the quick start
# ---------------------------------------------------------------------------
def test_uv_and_bun_workspaces_run_from_member_roots(tmp_path):
    r = analyze(make_project(tmp_path, {
        "pyproject.toml": '[tool.uv.workspace]\nmembers = ["backend"]\n',
        "uv.lock": "",
        "package.json": json.dumps({"name": "root", "private": True, "workspaces": ["frontend", "packages/*"],
                                    "scripts": {"dev": "bun run --filter frontend dev"}}),
        "bun.lock": "",
        "backend/pyproject.toml": '[project]\nname = "app"\ndependencies = ["fastapi[standard]"]\n',
        "backend/app/__init__.py": "",
        "backend/app/main.py": "from fastapi import FastAPI\nfrom app.api import router\napp = FastAPI()\n",
        "backend/app/api.py": "router = None\n",
        "frontend/package.json": json.dumps({"name": "web", "scripts": {"dev": "vite", "build": "vite build"},
                                             "dependencies": {"react": "18"}}),
        "frontend/src/main.tsx": "createRoot(document.body).render(<div />);\n",
        "packages/emails/package.json": json.dumps({"name": "emails", "scripts": {"build": "email export"}}),
        "packages/emails/src/Welcome.tsx": "export function Welcome() {\n  return <div />;\n}\n",
    }))
    systems = {(s["ecosystem"], s["root"]): s for s in r["build_systems"]}

    py = systems[("Python", "backend")]
    assert py["tool"] == "uv" and py["install"] == ["uv sync"] and py["workspace"] == "."
    assert py["run"] == ["uv run uvicorn app.main:app --reload"]          # not backend.app.main:app from "."
    assert ("Python", ".") not in systems                                # the root is only a workspace

    root = systems[("JavaScript/TypeScript", ".")]
    assert root["install"] == ["bun install"] and root["workspace"] is None
    member = systems[("JavaScript/TypeScript", "frontend")]
    assert member["workspace"] == "." and member["install"] is None
    assert member["run"] == ["bun run dev"] and member["build"] == ["bun run build"]
    assert systems[("JavaScript/TypeScript", "packages/emails")]["build"] == ["bun run build"]


def test_pnpm_workspace_members(tmp_path):
    r = analyze(make_project(tmp_path, {
        "package.json": json.dumps({"name": "mono", "private": True}),
        "pnpm-workspace.yaml": "packages:\n  - 'apps/*'\n  - \"!apps/legacy\"\n",
        "pnpm-lock.yaml": "",
        "apps/web/package.json": json.dumps({"name": "web", "scripts": {"dev": "next dev"}}),
        "apps/web/src/page.tsx": "export default function Page() {\n  return <div />;\n}\n",
        "apps/legacy/package.json": json.dumps({"name": "legacy", "scripts": {"dev": "node ."}}),
        "apps/legacy/index.js": "console.log(1);\n",
    }))
    roots = {s["root"]: s for s in r["build_systems"] if s["ecosystem"] == "JavaScript/TypeScript"}
    assert roots["apps/web"]["run"] == ["pnpm run dev"] and roots["apps/web"]["workspace"] == "."
    assert "apps/legacy" not in roots
