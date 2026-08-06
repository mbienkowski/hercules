"""Architecture read from repositories this project is not. The import patterns are a head start,
never the ceiling: what matters is that each language the extractor claims resolves correctly, that
an area boundary is found where the paths actually diverge rather than at a depth tuned to one
layout, and that a language it cannot parse is REPORTED rather than silently contributing nothing.
"""

from __future__ import annotations

import pytest

from tests.scripts.tools.code_of_conduct.coc_scan.conftest import _commit, _git, _write, fact, fact_ids

BASE = 1_900_000_000


def _repo(root, files: dict, subject: str = "feat: initial"):
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "user.name", "Fixture")
    _git(root, "config", "commit.gpgsign", "false")
    for relative, text in files.items():
        _write(root, relative, text)
    _commit(root, subject, 10, BASE)
    return root


@pytest.fixture
def jvm_repo(tmp_path):
    """A Maven layout: the package path is deep, and every real edge lives many segments in."""
    return _repo(tmp_path / "jvm", {
        "pom.xml": "<project/>",
        "src/main/java/com/shop/core/OrderService.java":
            "package com.shop.core;\npublic class OrderService {}\n",
        "src/main/java/com/shop/web/CartController.java":
            "package com.shop.web;\nimport com.shop.core.OrderService;\npublic class C {}\n",
        "src/main/java/com/shop/web/UserController.java":
            "package com.shop.web;\nimport com.shop.core.OrderService;\npublic class U {}\n",
        "src/main/java/com/shop/web/PayController.java":
            "package com.shop.web;\nimport com.shop.core.OrderService;\npublic class P {}\n",
        "src/main/java/com/shop/Application.java":
            "package com.shop;\npublic class Application {\n"
            "  public static void main(String[] a) {}\n}\n",
    })


@pytest.fixture
def go_repo(tmp_path):
    return _repo(tmp_path / "go", {
        "go.mod": "module github.com/acme/svc\n\ngo 1.22\n",
        "internal/store/store.go": "package store\n\nfunc Get() int { return 1 }\n",
        "internal/api/orders.go":
            'package api\n\nimport (\n\t"fmt"\n\t"github.com/acme/svc/internal/store"\n)\n\n'
            'func Orders() { fmt.Println(store.Get()) }\n',
        "internal/api/users.go":
            'package api\n\nimport "github.com/acme/svc/internal/store"\n\n'
            'func Users() int { return store.Get() }\n',
        "internal/api/billing.go":
            'package api\n\nimport "github.com/acme/svc/internal/store"\n\n'
            'func Billing() int { return store.Get() }\n',
        "cmd/server/main.go":
            'package main\n\nimport "github.com/acme/svc/internal/api"\n\nfunc main() { api.Orders() }\n',
    })


@pytest.fixture
def ruby_rust_repo(tmp_path):
    return _repo(tmp_path / "mixed", {
        "Gemfile": "source 'https://rubygems.org'\n",
        "lib/parser.rb": "class Parser; end\n",
        "app/cli.rb": "require_relative '../lib/parser'\n",
        "app/web.rb": "require_relative '../lib/parser'\n",
        "Cargo.toml": "[package]\nname='mixed'\n",
        "src/engine.rs": "pub fn run() {}\n",
        "src/main.rs": "use crate::engine;\n\nfn main() { engine::run() }\n",
    })


@pytest.fixture
def python_layout_repo(tmp_path):
    """The two Python layouts a root-relative reading is blind to, in one repository: a package
    living under `src/` whose modules import each other relatively and by bare package name."""
    return _repo(tmp_path / "pylayout", {
        "pyproject.toml": "[project]\nname = 'svc'\n",
        "src/svc/__init__.py": "",
        "src/svc/store.py": "def get():\n    return 1\n",
        "src/svc/api/__init__.py": "",
        "src/svc/api/orders.py": "from ..store import get\n\n\ndef orders():\n    return get()\n",
        "src/svc/api/users.py": "from svc.store import get\n\n\ndef users():\n    return get()\n",
        "src/svc/api/pay.py": "from ..store import get\n\n\ndef pay():\n    return get()\n",
        "src/svc/api/billing.py":
            "from .orders import orders\n\n\ndef billing():\n    return orders()\n",
    })


@pytest.fixture
def unparsed_repo(tmp_path):
    """A language the extractor has no pattern for. It must say so, not imply independence."""
    return _repo(tmp_path / "unparsed", {
        "App.sln": "",
        "src/Core/Engine.cs": "namespace App.Core { class Engine {} }\n",
        "src/Services/OrderService.cs": "using App.Core;\nnamespace App.Services { class O {} }\n",
    })


def test_a_jvm_import_resolves_by_its_path_tail(jvm_repo, scan):
    """A dotted name is not a path; only its tail is, and the basename narrows the search."""
    code, document = scan(jvm_repo)
    assert code == 0
    chokepoints = fact(document, "arch.chokepoints")["value"]
    assert chokepoints[0]["path"] == "src/main/java/com/shop/core/OrderService.java"
    assert chokepoints[0]["fan_in"] == 3


def test_python_relative_and_src_layout_imports_resolve(python_layout_repo, scan):
    """`from ..store import get` climbs from the importing file's own package, and a bare
    `svc.store` in an src-layout lives at `src/svc/store.py`. These are the two most common real
    Python layouts, and a root-relative reading resolved neither — reporting `.py` as parsed while
    the graph it fed stayed systematically empty."""
    code, document = scan(python_layout_repo)
    assert code == 0
    chokepoints = fact(document, "arch.chokepoints")["value"]
    assert chokepoints[0]["path"] == "src/svc/store.py"
    assert chokepoints[0]["fan_in"] == 3  # two relative importers and one bare-package importer


def test_an_area_boundary_is_found_where_the_paths_diverge(jvm_repo, scan):
    """A fixed depth is a property of one repository's layout: at depth two a Maven tree reads as
    `src/main` importing `src/main`, and every real edge vanishes into a self-loop."""
    code, document = scan(jvm_repo)
    edges = fact(document, "arch.graph")["value"]["edges"]
    assert {"from": "src/main/java/com/shop/web",
            "to": "src/main/java/com/shop/core", "imports": 3} in edges


def test_a_go_import_resolves_under_its_own_module_prefix(go_repo, scan):
    """A Go import is the module path plus the package directory, and the module names itself."""
    code, document = scan(go_repo)
    edges = fact(document, "arch.graph")["value"]["edges"]
    assert {"from": "internal/api", "to": "internal/store", "imports": 3} in edges


def test_a_go_package_directory_is_the_chokepoint_rather_than_a_file(go_repo, scan):
    """Go imports a package, never a file, so what several callers depend on is the DIRECTORY —
    and reporting a file there would send the reader looking for an import that names none."""
    code, document = scan(go_repo)
    chokepoints = fact(document, "arch.chokepoints")["value"]
    assert chokepoints[0] == {"path": "internal/store", "fan_in": 3}


def test_ruby_and_rust_resolve_alongside_each_other(ruby_rust_repo, scan):
    """One repository, two languages, one graph — neither extractor may claim the other's files."""
    code, document = scan(ruby_rust_repo)
    edges = fact(document, "arch.graph")["value"]["edges"]
    assert {"from": "app", "to": "lib", "imports": 2} in edges


def test_each_language_declares_where_execution_enters(jvm_repo, go_repo, ruby_rust_repo, scan):
    for repo, expected in ((jvm_repo, "src/main/java/com/shop/Application.java"),
                           (go_repo, "cmd/server/main.go"),
                           (ruby_rust_repo, "src/main.rs")):
        code, document = scan(repo)
        assert expected in fact(document, "arch.entrypoints")["value"]["main_guards"]


def test_a_go_entrypoint_needs_both_marks(tmp_path, scan):
    """`func main` inside a library package is an ordinary function, not a way in."""
    repo = _repo(tmp_path / "notmain", {
        "go.mod": "module github.com/acme/x\n\ngo 1.22\n",
        "internal/helper/helper.go": "package helper\n\nfunc main() {}\n",
    })
    code, document = scan(repo)
    entrypoints = fact(document, "arch.entrypoints")["value"] if \
        "arch.entrypoints" in fact_ids(document) else {"main_guards": []}
    assert "internal/helper/helper.go" not in entrypoints["main_guards"]


def test_a_language_the_extractor_cannot_parse_is_named(unparsed_repo, scan):
    """Silence must never pass for a measurement: the drafting agent has to know the graph is its
    own job here, and for which files."""
    code, document = scan(unparsed_repo)
    assert code == 0
    coverage = fact(document, "arch.import_coverage")["value"]
    assert coverage["parsed"] == []
    assert {"suffix": ".cs", "files": 2} in coverage["unparsed"]
    assert "arch.graph.partial" in document["unknowns"]


def test_a_fully_parsed_repository_claims_no_blind_spot(go_repo, scan):
    code, document = scan(go_repo)
    coverage = fact(document, "arch.import_coverage")["value"]
    assert coverage["unparsed"] == []
    assert "arch.graph.partial" not in document["unknowns"]


def test_an_unparsed_language_still_yields_the_language_agnostic_facts(unparsed_repo, scan):
    """Families, liveness and history never parse a language, so they hold everywhere."""
    code, document = scan(unparsed_repo)
    assert "arch.graph" not in fact_ids(document)
    assert document["liveness"]["directories"]


def test_two_runs_of_a_foreign_repository_are_byte_identical(jvm_repo, scan):
    first = scan(jvm_repo)[1]
    second = scan(jvm_repo)[1]
    assert first == second
