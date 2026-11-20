"""
Tree-sitter based source parsing for Python, JavaScript/JSX, TypeScript/TSX, Java,
Rust and C/C++.

For each file it extracts:
  - symbols: functions, methods, classes/structs/interfaces/traits/enums/... with exact
    line ranges (extended upwards to include decorators, attributes and doc comments),
    their parent class-like container, and the calls made inside each function
  - imports: structured references (module text + imported names + kind)
  - has_main: whether the file is a program entry point
  - type_refs / package (Java): used to link files in the same package

`parse_source()` returns None when tree-sitter (or a grammar) is unavailable, so
callers can fall back to the older regex analysis.
"""
import re
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set, Tuple

try:
    import tree_sitter as _ts
except ImportError:  # pragma: no cover
    _ts = None

MAX_PARSE_BYTES = 1_500_000  # skip generated / amalgamated giants

# extension -> grammar id
EXTENSION_GRAMMAR: Dict[str, str] = {
    ".py": "python", ".pyi": "python",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".mts": "typescript", ".cts": "typescript",
    ".tsx": "tsx",
    ".java": "java",
    ".rs": "rust",
    ".c": "cpp", ".h": "cpp", ".cc": "cpp", ".cpp": "cpp", ".cxx": "cpp",
    ".hpp": "cpp", ".hh": "cpp", ".hxx": "cpp", ".ipp": "cpp",
}

_GRAMMAR_LOADERS: Dict[str, Callable] = {
    "python": lambda: __import__("tree_sitter_python").language(),
    "javascript": lambda: __import__("tree_sitter_javascript").language(),
    "typescript": lambda: __import__("tree_sitter_typescript").language_typescript(),
    "tsx": lambda: __import__("tree_sitter_typescript").language_tsx(),
    "java": lambda: __import__("tree_sitter_java").language(),
    "rust": lambda: __import__("tree_sitter_rust").language(),
    "cpp": lambda: __import__("tree_sitter_cpp").language(),
}

FUNCTION_KINDS = {"function", "method", "macro"}
CLASS_KINDS = {"class", "struct", "interface", "trait", "enum", "record", "union"}


# ----------------------------------------------------------------------------
# Result types
# ----------------------------------------------------------------------------
@dataclass
class Symbol:
    name: str
    kind: str                      # function|method|macro|class|struct|interface|trait|enum|record|union|type
    parent: Optional[str]          # enclosing class-like container (or enclosing function for nested fns)
    start_line: int                # 1-based, includes decorators / attributes / doc comments
    end_line: int
    calls: List[Tuple[str, Optional[str], bool]] = field(default_factory=list)  # (name, qualifier, is_member_call)

    @property
    def qualname(self) -> str:
        return f"{self.parent}.{self.name}" if self.parent else self.name

    def to_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "parent": self.parent,
                "start_line": self.start_line, "end_line": self.end_line, "calls": self.calls}


@dataclass
class ImportRef:
    module: str                    # as written: "..core", "./x.js", "com.a.B", "crate::cfg::Config", "net/socket.h"
    names: List[str] = field(default_factory=list)
    kind: str = "import"           # import|from|require|dynamic|reexport|static|wildcard|use|mod|include|include_system

    def to_dict(self) -> dict:
        return {"module": self.module, "names": self.names, "kind": self.kind}


@dataclass
class ParsedFile:
    grammar: str
    symbols: List[Symbol]
    imports: List[ImportRef]
    has_main: bool = False
    package: Optional[str] = None
    type_refs: Set[str] = field(default_factory=set)
    error_ratio: float = 0.0       # share of the tree that failed to parse

    @property
    def functions(self) -> List[str]:
        return _unique(s.name for s in self.symbols if s.kind in FUNCTION_KINDS)

    @property
    def classes(self) -> List[str]:
        return _unique(s.name for s in self.symbols if s.kind in CLASS_KINDS)

    @property
    def import_strings(self) -> List[str]:
        out = []
        for ref in self.imports:
            if ref.kind == "mod":
                out.append(f"mod {ref.module}")
            elif ref.kind == "from" and ref.module.strip(".") == "" and ref.names:
                out.extend(f"{ref.module}{n}" for n in ref.names)  # "from . import views" -> ".views"
            else:
                out.append(ref.module)
        return _unique(out)


def _unique(items) -> list:
    seen, out = set(), []
    for i in items:
        if i and i not in seen:
            seen.add(i)
            out.append(i)
    return out


# ----------------------------------------------------------------------------
# Grammar / parser management (parsers are not thread-safe -> one per thread)
# ----------------------------------------------------------------------------
_languages: Dict[str, object] = {}
_lang_lock = threading.Lock()
_local = threading.local()
_unavailable: Set[str] = set()


def _language(grammar: str):
    if grammar in _languages:
        return _languages[grammar]
    with _lang_lock:
        if grammar not in _languages and grammar not in _unavailable:
            try:
                _languages[grammar] = _ts.Language(_GRAMMAR_LOADERS[grammar]())
            except Exception as e:  # missing grammar wheel
                print(f"[parser] grammar '{grammar}' unavailable: {e}")
                _unavailable.add(grammar)
    return _languages.get(grammar)


def _parser(grammar: str):
    parsers = getattr(_local, "parsers", None)
    if parsers is None:
        parsers = _local.parsers = {}
    if grammar not in parsers:
        lang = _language(grammar)
        if lang is None:
            return None
        parsers[grammar] = _ts.Parser(lang)
    return parsers[grammar]


def available() -> bool:
    return _ts is not None


def supports(ext: str) -> bool:
    return _ts is not None and ext.lower() in EXTENSION_GRAMMAR


def parse_source(content: str, ext: str) -> Optional[ParsedFile]:
    grammar = EXTENSION_GRAMMAR.get(ext.lower())
    if not grammar or _ts is None or len(content) > MAX_PARSE_BYTES:
        return None
    parser = _parser(grammar)
    if parser is None:
        return None
    data = content.encode("utf-8", errors="replace")
    tree = parser.parse(data)
    extractor = _EXTRACTORS[grammar](grammar, content)
    try:
        return extractor.run(tree.root_node)
    except RecursionError:  # pathological nesting; regex fallback will be used
        return None


# ----------------------------------------------------------------------------
# Generic extractor
# ----------------------------------------------------------------------------
def _text(node) -> str:
    return node.text.decode("utf-8", errors="replace") if node is not None else ""


class _Extractor:
    """Walks the tree once; subclasses classify nodes."""

    WRAPPERS: Set[str] = set()                       # nodes whose start should be used for a symbol inside them
    LEADING = {"comment", "line_comment", "block_comment"}  # siblings to absorb above a symbol

    def __init__(self, grammar: str, content: str):
        self.grammar = grammar
        self.content = content
        self.symbols: List[Symbol] = []
        self.imports: List[ImportRef] = []
        self.type_refs: Set[str] = set()
        self.package: Optional[str] = None
        self.has_main = False
        self._errors = 0
        self._nodes = 0

    # -- to override --------------------------------------------------------
    def symbol(self, node, parent: Optional[str], cur: Optional[Symbol]) -> Optional[Tuple[str, str, Optional[str]]]:
        """Return (name, kind, parent_override_or_None) if `node` defines a symbol."""
        return None

    def container(self, node) -> Optional[str]:
        """Class-like containers that are not themselves symbols (e.g. Rust `impl Foo`)."""
        return None

    def handle_import(self, node) -> bool:
        """Record imports; return True if the subtree needs no further walking."""
        return False

    def call(self, node) -> Optional[Tuple[str, Optional[str], bool]]:
        return None

    def finish(self) -> None:
        pass

    # -- walk ---------------------------------------------------------------
    def run(self, root) -> ParsedFile:
        # (node, class_parent, current_function_symbol)
        stack = [(root, None, None)]
        while stack:
            node, parent, cur = stack.pop()
            self._nodes += 1
            if node.type == "ERROR":
                self._errors += 1

            if self.handle_import(node):
                continue

            new_parent, new_cur = parent, cur
            found = self.symbol(node, parent, cur)
            if found:
                name, kind, parent_override = found
                sym_parent = parent_override if parent_override is not None else (cur.name if cur else parent)
                if kind in FUNCTION_KINDS and cur is not None and parent_override is None:
                    kind = "function"  # nested function / closure-like definition
                sym = Symbol(name=name, kind=kind, parent=sym_parent,
                             start_line=self.start_line(node), end_line=node.end_point[0] + 1)
                self.symbols.append(sym)
                if kind in FUNCTION_KINDS:
                    new_cur = sym
                else:
                    new_parent, new_cur = name, None
            else:
                cont = self.container(node)
                if cont:
                    new_parent, new_cur = cont, None
                else:
                    c = self.call(node)
                    if c and cur is not None:
                        cur.calls.append(c)

            children = node.named_children
            for child in reversed(children):
                stack.append((child, new_parent, new_cur))

        self.finish()
        for s in self.symbols:  # de-duplicate calls, keep order
            s.calls = list(dict.fromkeys(s.calls))
        return ParsedFile(
            grammar=self.grammar, symbols=self.symbols, imports=self.imports,
            has_main=self.has_main, package=self.package, type_refs=self.type_refs,
            error_ratio=self._errors / max(self._nodes, 1),
        )

    def start_line(self, node) -> int:
        n = node
        while n.parent is not None and n.parent.type in self.WRAPPERS:
            n = n.parent
        start = n.start_point[0]
        # A leading comment on the first member of a body can attach to the body's parent
        # (e.g. Python's `block` starts at the first `def`): climb while the parent starts here.
        cur, prev = n, n.prev_named_sibling
        while prev is None and cur.parent is not None and cur.parent.start_point[0] == start:
            cur = cur.parent
            prev = cur.prev_named_sibling
        while prev is not None and prev.type in self.LEADING and prev.end_point[0] >= start - 1:
            start = prev.start_point[0]
            prev = prev.prev_named_sibling
        return start + 1


# ----------------------------------------------------------------------------
# Python
# ----------------------------------------------------------------------------
class _PythonExtractor(_Extractor):
    WRAPPERS = {"decorated_definition"}

    def symbol(self, node, parent, cur):
        if node.type == "function_definition":
            name = _text(node.child_by_field_name("name"))
            return name, ("method" if parent and cur is None else "function"), None
        if node.type == "class_definition":
            return _text(node.child_by_field_name("name")), "class", None
        return None

    def handle_import(self, node):
        if node.type == "import_statement":
            for n in node.children_by_field_name("name"):
                target = n.child_by_field_name("name") if n.type == "aliased_import" else n
                self.imports.append(ImportRef(_text(target), [], "import"))
            return True
        if node.type == "import_from_statement":
            module = _text(node.child_by_field_name("module_name"))
            names = []
            for n in node.children_by_field_name("name"):
                target = n.child_by_field_name("name") if n.type == "aliased_import" else n
                names.append(_text(target))
            if any(c.type == "wildcard_import" for c in node.named_children):
                names.append("*")
            self.imports.append(ImportRef(module, names, "from"))
            return True
        return False

    def call(self, node):
        if node.type != "call":
            return None
        fn = node.child_by_field_name("function")
        if fn is None:
            return None
        if fn.type == "identifier":
            return _text(fn), None, False
        if fn.type == "attribute":
            obj = fn.child_by_field_name("object")
            qual = _text(obj) if obj is not None and obj.type == "identifier" else None
            return _text(fn.child_by_field_name("attribute")), qual, True
        return None

    def finish(self):
        c = self.content
        self.has_main = bool(re.search(r"^if\s+__name__\s*==\s*['\"]__main__['\"]", c, re.M)
                             or re.search(r"^def main\s*\(", c, re.M))


# ----------------------------------------------------------------------------
# JavaScript / TypeScript / TSX
# ----------------------------------------------------------------------------
_JS_FUNCTION_VALUES = {"arrow_function", "function_expression", "function", "generator_function"}
_JS_HOOK_WRAPPERS = {"useCallback", "useMemo", "memo", "forwardRef", "React.memo", "React.forwardRef",
                     "React.useCallback", "React.useMemo", "observer", "styled"}


_JS_NON_PARENT_OBJECTS = {"exports", "module", "window", "global", "globalThis", "self"}


class _JsExtractor(_Extractor):
    WRAPPERS = {"export_statement", "lexical_declaration", "variable_declaration", "expression_statement"}

    def _assignment_symbol(self, node):
        """CommonJS / prototype style: `exports.x = function`, `res.send = function send()`,
        `Foo.prototype.bar = () => {}`, `module.exports = function createApp() {}`."""
        left, right = node.child_by_field_name("left"), node.child_by_field_name("right")
        if left is None or right is None or right.type not in _JS_FUNCTION_VALUES:
            return None
        if left.type == "identifier":
            return _text(left), "function", None
        if left.type != "member_expression":
            return None
        prop = _text(left.child_by_field_name("property"))
        obj = left.child_by_field_name("object")
        if obj is not None and obj.type == "identifier" and _text(obj) == "module" and prop == "exports":
            own = right.child_by_field_name("name")
            return (_text(own), "function", None) if own is not None else None
        parent = None
        if obj is not None and obj.type == "member_expression" \
                and _text(obj.child_by_field_name("property")) == "prototype":
            parent = _text(obj.child_by_field_name("object"))
        elif obj is not None and obj.type == "identifier" and _text(obj) not in _JS_NON_PARENT_OBJECTS:
            parent = _text(obj)
        return (prop, "method", parent) if parent else (prop, "function", None)

    def symbol(self, node, parent, cur):
        t = node.type
        if t in ("function_declaration", "generator_function_declaration"):
            return _text(node.child_by_field_name("name")), "function", None
        if t == "assignment_expression":
            return self._assignment_symbol(node)
        if t in ("class_declaration", "abstract_class_declaration"):
            return _text(node.child_by_field_name("name")), "class", None
        if t == "method_definition":
            return _text(node.child_by_field_name("name")).lstrip("#"), "method", None
        if t in ("public_field_definition", "field_definition"):
            value = node.child_by_field_name("value")
            if value is not None and value.type in _JS_FUNCTION_VALUES:
                key = node.child_by_field_name("name") or node.child_by_field_name("property")
                return _text(key).lstrip("#"), "method", None
        if t == "variable_declarator":
            name_node, value = node.child_by_field_name("name"), node.child_by_field_name("value")
            if name_node is None or value is None or name_node.type != "identifier":
                return None
            if value.type in _JS_FUNCTION_VALUES:
                return _text(name_node), "function", None
            if value.type == "class":
                return _text(name_node), "class", None
            if value.type == "call_expression":
                callee = _text(value.child_by_field_name("function"))
                if callee in _JS_HOOK_WRAPPERS:
                    return _text(name_node), "function", None
        if t == "pair":
            key, value = node.child_by_field_name("key"), node.child_by_field_name("value")
            if key is not None and value is not None and value.type in _JS_FUNCTION_VALUES \
                    and key.type in ("property_identifier", "identifier"):
                return _text(key), "method", None
        if t == "interface_declaration":
            return _text(node.child_by_field_name("name")), "interface", None
        if t == "enum_declaration":
            return _text(node.child_by_field_name("name")), "enum", None
        if t == "type_alias_declaration":
            return _text(node.child_by_field_name("name")), "type", None
        return None

    def handle_import(self, node):
        t = node.type
        if t == "import_statement":
            source = _string_value(node.child_by_field_name("source"))
            names = []
            for clause in node.named_children:
                if clause.type == "import_clause":
                    for c in clause.named_children:
                        if c.type == "identifier":
                            names.append(_text(c))
                        elif c.type == "named_imports":
                            names.extend(_text(s.child_by_field_name("name")) for s in c.named_children
                                         if s.type == "import_specifier")
                        elif c.type == "namespace_import":
                            names.append("*")
            if source:
                self.imports.append(ImportRef(source, names, "import"))
            return True
        if t == "export_statement" and node.child_by_field_name("source") is not None:
            source = _string_value(node.child_by_field_name("source"))
            if source:
                self.imports.append(ImportRef(source, [], "reexport"))
            return True
        if t == "call_expression":
            fn = node.child_by_field_name("function")
            if fn is not None and (fn.type == "import" or (fn.type == "identifier" and _text(fn) == "require")):
                args = node.child_by_field_name("arguments")
                first = args.named_children[0] if args is not None and args.named_children else None
                source = _string_value(first) if first is not None and first.type == "string" else ""
                if source:
                    self.imports.append(ImportRef(source, [], "dynamic" if fn.type == "import" else "require"))
        return False

    def call(self, node):
        t = node.type
        if t == "call_expression":
            fn = node.child_by_field_name("function")
            if fn is None:
                return None
            if fn.type == "identifier":
                return _text(fn), None, False
            if fn.type == "member_expression":
                obj = fn.child_by_field_name("object")
                qual = None
                if obj is not None and obj.type in ("identifier", "this", "super"):
                    qual = "this" if obj.type in ("this", "super") else _text(obj)
                return _text(fn.child_by_field_name("property")).lstrip("#"), qual, True
            return None
        if t == "new_expression":
            ctor = node.child_by_field_name("constructor")
            if ctor is not None and ctor.type == "identifier":
                return _text(ctor), None, False
            return None
        if t in ("jsx_opening_element", "jsx_self_closing_element"):
            name = node.child_by_field_name("name")
            if name is not None and name.type == "identifier" and _text(name)[:1].isupper():
                return _text(name), None, False  # <Component /> renders (calls) Component
            if name is not None and name.type == "member_expression":
                return _text(name.child_by_field_name("property")), None, True
        return None

    def finish(self):
        c = self.content
        self.has_main = any(x in c for x in ("createRoot(", "ReactDOM.render", "createApp(", "hydrateRoot(")) \
            or bool(re.search(r"\b(?:app|server|fastify)\.listen\s*\(", c))


def _string_value(node) -> str:
    if node is None:
        return ""
    frag = [c for c in node.named_children if c.type == "string_fragment"]
    if frag:
        return _text(frag[0])
    return _text(node).strip("'\"`")


# ----------------------------------------------------------------------------
# Java
# ----------------------------------------------------------------------------
_JAVA_CLASS_NODES = {
    "class_declaration": "class", "interface_declaration": "interface", "enum_declaration": "enum",
    "record_declaration": "record", "annotation_type_declaration": "interface",
}


class _JavaExtractor(_Extractor):

    def symbol(self, node, parent, cur):
        t = node.type
        if t in _JAVA_CLASS_NODES:
            return _text(node.child_by_field_name("name")), _JAVA_CLASS_NODES[t], None
        if t in ("method_declaration", "constructor_declaration", "compact_constructor_declaration"):
            name = _text(node.child_by_field_name("name")) or parent or ""
            if name == "main" and t == "method_declaration":
                mods = next((c for c in node.children if c.type == "modifiers"), None)
                if mods is not None and "static" in _text(mods):
                    self.has_main = True
            return name, "method", None
        return None

    def handle_import(self, node):
        if node.type == "package_declaration":
            target = next((c for c in node.named_children if c.type in ("scoped_identifier", "identifier")), None)
            self.package = _text(target)
            return True
        if node.type == "import_declaration":
            target = next((c for c in node.named_children if c.type in ("scoped_identifier", "identifier")), None)
            module = _text(target)
            is_static = any(c.type == "static" for c in node.children)
            if any(c.type == "asterisk" for c in node.children):
                self.imports.append(ImportRef(module + ".*", [], "wildcard"))
            else:
                self.imports.append(ImportRef(module, [], "static" if is_static else "import"))
            return True
        if node.type == "type_identifier":
            self.type_refs.add(_text(node))
        return False

    def call(self, node):
        if node.type == "method_invocation":
            name = _text(node.child_by_field_name("name"))
            obj = node.child_by_field_name("object")
            if obj is None:
                return name, None, False
            if obj.type in ("this", "super"):
                return name, "this", True
            if obj.type == "identifier" and _text(obj)[:1].isupper():
                return name, _text(obj), False  # static call: Util.helper()
            return name, None, True
        if node.type == "object_creation_expression":
            typ = node.child_by_field_name("type")
            if typ is not None:
                name = _text(typ).split("<")[0].split(".")[-1]
                self.type_refs.add(name)
                return name, None, False  # constructor
        return None


# ----------------------------------------------------------------------------
# Rust
# ----------------------------------------------------------------------------
_RUST_TYPE_ITEMS = {"struct_item": "struct", "enum_item": "enum", "union_item": "union", "trait_item": "trait"}


def _rust_type_name(node) -> Optional[str]:
    if node is None:
        return None
    if node.type == "type_identifier":
        return _text(node)
    if node.type == "generic_type":
        return _rust_type_name(node.child_by_field_name("type"))
    if node.type == "scoped_type_identifier":
        return _text(node.child_by_field_name("name"))
    if node.type in ("reference_type", "pointer_type"):
        return _rust_type_name(node.child_by_field_name("type"))
    return None


def _rust_use_paths(node, prefix: str = "") -> List[str]:
    """Expand a use tree into full paths: `a::{b, c::d as e, f::*}` -> a::b, a::c::d, a::f::*"""
    if node is None:
        return []
    t = node.type
    join = (lambda s: f"{prefix}::{s}" if prefix else s)
    if t in ("identifier", "scoped_identifier", "crate", "self", "super", "metavariable"):
        return [join(_text(node))]
    if t == "use_as_clause":
        return _rust_use_paths(node.child_by_field_name("path"), prefix)
    if t == "use_wildcard":
        inner = node.named_children[0] if node.named_children else None
        return [join((_text(inner) + "::*") if inner is not None else "*")]
    if t == "scoped_use_list":
        path = node.child_by_field_name("path")
        new_prefix = join(_text(path)) if path is not None else prefix
        return _rust_use_paths(node.child_by_field_name("list"), new_prefix)
    if t == "use_list":
        out = []
        for c in node.named_children:
            if c.type == "self":
                out.append(prefix)
            else:
                out.extend(_rust_use_paths(c, prefix))
        return out
    return []


class _RustExtractor(_Extractor):
    LEADING = {"line_comment", "block_comment", "attribute_item"}

    def symbol(self, node, parent, cur):
        t = node.type
        if t == "function_item":
            name = _text(node.child_by_field_name("name"))
            if name == "main" and parent is None and cur is None:
                self.has_main = True
            return name, ("method" if parent and cur is None else "function"), None
        if t == "function_signature_item":
            return _text(node.child_by_field_name("name")), "method", None
        if t in _RUST_TYPE_ITEMS:
            return _text(node.child_by_field_name("name")), _RUST_TYPE_ITEMS[t], None
        if t == "macro_definition":
            return _text(node.child_by_field_name("name")), "macro", None
        if t == "type_item":
            return _text(node.child_by_field_name("name")), "type", None
        return None

    def container(self, node):
        if node.type == "impl_item":
            return _rust_type_name(node.child_by_field_name("type"))
        return None

    def handle_import(self, node):
        t = node.type
        if t == "use_declaration":
            for path in _rust_use_paths(node.child_by_field_name("argument")):
                self.imports.append(ImportRef(path, [], "use"))
            return True
        if t == "mod_item" and node.child_by_field_name("body") is None:
            self.imports.append(ImportRef(_text(node.child_by_field_name("name")), [], "mod"))
            return True
        if t == "extern_crate_declaration":
            self.imports.append(ImportRef(_text(node.child_by_field_name("name")), [], "use"))
            return True
        return False

    def call(self, node):
        t = node.type
        if t == "call_expression":
            fn = node.child_by_field_name("function")
            if fn is not None and fn.type == "generic_function":
                fn = fn.child_by_field_name("function")
            if fn is None:
                return None
            if fn.type == "identifier":
                return _text(fn), None, False
            if fn.type == "scoped_identifier":
                path = fn.child_by_field_name("path")
                qual = _rust_type_name(path) if path is not None and path.type == "generic_type" else \
                    (_text(path).split("::")[-1] if path is not None else None)
                return _text(fn.child_by_field_name("name")), qual, False
            if fn.type == "field_expression":
                value = fn.child_by_field_name("value")
                qual = "self" if value is not None and value.type == "self" else None
                return _text(fn.child_by_field_name("field")), qual, True
            return None
        if t == "macro_invocation":
            m = node.child_by_field_name("macro")
            if m is not None:
                name = _text(m.child_by_field_name("name")) if m.type == "scoped_identifier" else _text(m)
                return name, None, False
        return None


# ----------------------------------------------------------------------------
# C / C++
# ----------------------------------------------------------------------------
_CPP_CLASS_NODES = {"class_specifier": "class", "struct_specifier": "struct",
                    "union_specifier": "union", "enum_specifier": "enum"}
_CPP_DECLARATOR_WRAPPERS = {"pointer_declarator", "reference_declarator", "attributed_declarator",
                            "parenthesized_declarator"}


def _strip_template(name: str) -> str:
    return re.sub(r"<.*>$", "", name).strip()


def _cpp_function_name(declarator) -> Tuple[Optional[str], Optional[str]]:
    """(name, scope_parent) from a function_definition's declarator."""
    n = declarator
    while n is not None and n.type in _CPP_DECLARATOR_WRAPPERS:
        n = n.child_by_field_name("declarator") or (n.named_children[-1] if n.named_children else None)
    if n is None or n.type != "function_declarator":
        return None, None
    d = n.child_by_field_name("declarator")
    if d is None:
        return None, None
    if d.type in ("identifier", "field_identifier", "destructor_name", "operator_name"):
        return _text(d), None
    if d.type == "template_function":
        return _text(d.child_by_field_name("name")), None
    if d.type == "qualified_identifier":
        scope, name = d.child_by_field_name("scope"), d.child_by_field_name("name")
        while name is not None and name.type == "qualified_identifier":
            scope, name = name.child_by_field_name("scope"), name.child_by_field_name("name")
        if name is not None and name.type == "template_function":
            name = name.child_by_field_name("name")
        parent = _strip_template(_text(scope).split("::")[-1]) if scope is not None else None
        return _text(name), (parent or None)
    return None, None


class _CppExtractor(_Extractor):
    WRAPPERS = {"template_declaration"}

    def symbol(self, node, parent, cur):
        t = node.type
        if t == "function_definition":
            name, scope_parent = _cpp_function_name(node.child_by_field_name("declarator"))
            if not name:
                return None
            if name == "main" and parent is None and scope_parent is None and cur is None:
                self.has_main = True
            if scope_parent:
                return name, "method", scope_parent
            return name, ("method" if parent and cur is None else "function"), None
        if t in _CPP_CLASS_NODES and node.child_by_field_name("body") is not None:
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return None  # anonymous struct/enum
            return _strip_template(_text(name_node).split("::")[-1]), _CPP_CLASS_NODES[t], None
        return None

    def handle_import(self, node):
        if node.type == "preproc_include":
            path = node.child_by_field_name("path")
            if path is None:
                return True
            if path.type == "system_lib_string":
                self.imports.append(ImportRef(_text(path).strip("<>"), [], "include_system"))
            else:
                self.imports.append(ImportRef(_string_value_cpp(path), [], "include"))
            return True
        return False

    def call(self, node):
        t = node.type
        if t == "call_expression":
            fn = node.child_by_field_name("function")
            if fn is None:
                return None
            if fn.type == "identifier":
                return _text(fn), None, False
            if fn.type == "template_function":
                return _text(fn.child_by_field_name("name")), None, False
            if fn.type == "qualified_identifier":
                scope, name = fn.child_by_field_name("scope"), fn.child_by_field_name("name")
                while name is not None and name.type == "qualified_identifier":
                    scope, name = name.child_by_field_name("scope"), name.child_by_field_name("name")
                if name is not None and name.type == "template_function":
                    name = name.child_by_field_name("name")
                qual = _strip_template(_text(scope).split("::")[-1]) if scope is not None else None
                return _text(name), (None if qual == "std" else qual), False
            if fn.type == "field_expression":
                arg = fn.child_by_field_name("argument")
                qual = "this" if arg is not None and arg.type == "this" else None
                return _text(fn.child_by_field_name("field")), qual, True
            return None
        if t == "new_expression":
            typ = node.child_by_field_name("type")
            if typ is not None:
                return _strip_template(_text(typ).split("::")[-1]), None, False
        return None


def _string_value_cpp(node) -> str:
    content = next((c for c in node.named_children if c.type == "string_content"), None)
    return _text(content) if content is not None else _text(node).strip('"')


_EXTRACTORS = {
    "python": _PythonExtractor,
    "javascript": _JsExtractor, "typescript": _JsExtractor, "tsx": _JsExtractor,
    "java": _JavaExtractor,
    "rust": _RustExtractor,
    "cpp": _CppExtractor,
}
