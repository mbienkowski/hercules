"""The architecture the scanner can show, not guess: which directories grow by one-more-file-of-a-
kind, which areas import which, which single modules everything flows through, and where execution
enters. These are the facts a code-of-conduct's valuable rules stand on — a rule that names the
engine or the extension point cannot be drafted from config probes — and they are derived by regex
over import lines, so every one of them says it is inferred, never measured."""

from __future__ import annotations

import pytest

from tests.scripts.tools.code_of_conduct.coc_scan.conftest import (
    AGE_HEAD, AGE_RECENT, _commit, _write, build_repo, fact, fact_ids)


def build_arch_repo(root, base_epoch: int = 1_900_000_000):
    """A repository whose architecture is placed deliberately: one chokepoint three modules import,
    one directed edge between areas, two families, and three ways in."""
    build_repo(root, base_epoch)
    # The chokepoint: three importers over one module, crossing an area boundary.
    _write(root, "src/core/engine.py", "def run():\n    return 4\n")
    _write(root, "src/api/routes.py", "from src.core.engine import run\n")
    _write(root, "src/api/views.py", "import src.core.engine\n")
    _write(root, "src/cli/main.py",
           "from src.core.engine import run\n\nif __name__ == \"__main__\":\n    run()\n")
    # A relative TypeScript import inside one area: an edge the resolver must place, not invent.
    _write(root, "builder/build.mts", "import { render } from './template-engine.mjs';\n"
                                      "// reads src/targets at build time\n")
    _write(root, "builder/template-engine.mts", "export const render = () => null;\n")
    # Two families: one of content, one of configuration.
    for name in ("alpha", "beta", "gamma", "delta"):
        _write(root, f"src/agents/{name}.md", f"# {name}\n")
        _write(root, f"src/targets/{name}.json", "{}\n")
    _write(root, "bin/cli.py", "print('hi')\n")
    _commit(root, "feat: lay the architecture down", AGE_RECENT, base_epoch)
    _write(root, "src/core/engine.py", "def run():\n    return 5\n")
    _commit(root, "fix(core): adjust the engine", AGE_HEAD, base_epoch)
    return root


@pytest.fixture
def arch_repo(tmp_path):
    return build_arch_repo(tmp_path / "arch")


def test_a_directory_of_same_shaped_files_is_reported_as_a_family(scan, arch_repo):
    """A family is an extension point: the standard way this repository grows is one more file
    here, in this shape — which is exactly what a worked example teaches."""
    code, document = scan(arch_repo)
    assert code == 0
    families = fact(document, "arch.families")["value"]
    by_path = {entry["path"]: entry for entry in families}
    assert by_path["src/agents"]["files"] == 4
    assert by_path["src/agents"]["suffix"] == ".md"
    assert by_path["src/targets"]["suffix"] == ".json"


def build_many_families_repo(root, base_epoch: int = 1_900_000_000):
    """A repository with more real families (>=4 files each) than any reasonable cap should silently
    drop. Hercules itself has 24; this fixture builds 30 to prove the cap is not tuned to one repo."""
    build_repo(root, base_epoch)
    for group in range(30):
        for member in range(4):
            _write(root, f"src/group{group:02d}/file{member}.py", f"x = {member}\n")
    _commit(root, "feat: thirty families", AGE_RECENT, base_epoch)
    return root


@pytest.fixture
def many_families_repo(tmp_path):
    return build_many_families_repo(tmp_path / "many")


def test_a_repository_with_more_families_than_the_cap_says_so(scan, many_families_repo):
    """Silently dropping a family drops its worked example with it — the drafting agent never learns
    the extension point existed. A cap that truncates must say so, not just return fewer entries."""
    code, document = scan(many_families_repo)
    assert code == 0
    assert "arch.families_truncated" in document["unknowns"]


def test_a_repository_within_the_cap_reports_no_truncation(scan, arch_repo):
    code, document = scan(arch_repo)
    assert "arch.families_truncated" not in document["unknowns"]


def test_the_cap_is_not_tuned_to_a_single_small_repository(scan, many_families_repo):
    """A cap of 12 was measured, on this project alone, to drop `src/content/commands` — one of the
    most load-bearing extension points a user actually invokes. The cap must clear a repository with
    materially more real families than that without dropping the largest ones."""
    code, document = scan(many_families_repo)
    families = fact(document, "arch.families")["value"]
    assert len(families) >= 20


def test_a_generated_tree_joins_no_family(scan, arch_repo):
    """dist/ grows by rebuild, not by hand; a family there would teach editing build output."""
    code, document = scan(arch_repo)
    families = fact(document, "arch.families")["value"]
    assert not any(entry["path"].startswith("dist") for entry in families)


def test_imports_between_areas_become_directed_edges(scan, arch_repo):
    code, document = scan(arch_repo)
    edges = fact(document, "arch.graph")["value"]["edges"]
    assert {"from": "src/api", "to": "src/core", "imports": 2} in edges


def test_a_module_many_files_import_is_reported_as_a_chokepoint(scan, arch_repo):
    """The file every change flows through is the file a code-of-conduct must name."""
    code, document = scan(arch_repo)
    chokepoints = fact(document, "arch.chokepoints")["value"]
    assert chokepoints[0]["path"] == "src/core/engine.py"
    assert chokepoints[0]["fan_in"] == 3


def test_a_relative_import_resolves_to_its_file_not_to_a_guess(scan, arch_repo):
    """`./template-engine.mjs` from builder/build.mts is builder/template-engine.mts; a resolver
    that cannot place it must drop it rather than fabricate an edge."""
    code, document = scan(arch_repo)
    edges = fact(document, "arch.graph")["value"]["edges"]
    assert not any(edge["to"] == "template-engine.mjs" for edge in edges)


def test_entrypoints_are_collected_where_execution_starts(scan, arch_repo):
    code, document = scan(arch_repo)
    value = fact(document, "arch.entrypoints")["value"]
    assert "src/cli/main.py" in value["main_guards"]
    assert "bin/cli.py" in value["bin_files"]


def test_code_naming_a_configuration_family_is_reported_as_its_consumer(scan, arch_repo):
    """The recipe means nothing without the module that reads it; the pair is the architecture."""
    code, document = scan(arch_repo)
    consumers = fact(document, "arch.config_consumers")["value"]
    targets = next(entry for entry in consumers if entry["family"] == "src/targets")
    assert "builder/build.mts" in targets["consumers"]


def test_regex_derived_architecture_says_it_is_inferred(scan, arch_repo):
    """An import graph read by regex is approximate; a rule citing it must be able to see that."""
    code, document = scan(arch_repo)
    for fact_id in ("arch.graph", "arch.chokepoints", "arch.entrypoints"):
        assert fact(document, fact_id)["confidence"] == "inferred-medium"


def test_a_repository_with_no_architecture_to_show_emits_no_architecture_facts(scan, repo):
    """Absent evidence yields no fact — an empty edges list would read as 'measured: independent'."""
    code, document = scan(repo)
    assert code == 0
    assert not {"arch.graph", "arch.chokepoints", "arch.config_consumers"} & fact_ids(document)


def test_the_architecture_pass_survives_a_hostile_import_line(scan, arch_repo):
    """An import specifier is repository-authored text; a crafted one must not escape or crash."""
    _write(arch_repo, "src/api/hostile.py",
           "from " + "x" * 5000 + " import y\nimport ../../../etc/passwd\n")
    _commit(arch_repo, "chore: hostile import", AGE_HEAD, 1_900_000_000)
    code, document = scan(arch_repo)
    assert code == 0
    edges = fact(document, "arch.graph")["value"]["edges"]
    assert not any("etc" in edge["to"] or len(edge["to"]) > 200 for edge in edges)
