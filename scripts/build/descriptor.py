"""Ecosystem descriptors — the ONE per-ecosystem file, loaded and validated (closed vocabulary).

An ecosystem is described entirely by ``src/ecosystems/<name>.json``: token ``vars``, ``models``
tiers, the ``smoke`` install matrix entry, per-role output shapes (``roles``), destination
``routes``, inline JSON ``artifacts``, shared-``guard`` modules, write-``gate`` params, and named
``generate`` steps. The filename is the registry key; discovery is a glob — a new ecosystem is one
new JSON file, never new Python.

The DIRECTORY itself has a definitive schema, validated on discovery: every file is either a
``<name>.json`` descriptor or a ``<name>.dist.<dest>`` shipped file — the filename IS the contract
(``gemini-cli.dist.CAPABILITIES.md`` ships byte-identically to ``dist/gemini-cli/CAPABILITIES.md``),
so the input→output mapping is a pure, testable function of the name. A stray file, an unknown
ecosystem prefix, or a nested dest fails discovery loudly.

The vocabulary is **closed**: a descriptor selects named, mutation-covered Python behaviors (the
serialization modes, field generators, route kinds, and generators in ``genserialize``/``genextras``)
and supplies operands only. An unknown key or enum value raises :class:`DescriptorError` naming the
offending key and the allowed set — control flow stays typed Python; descriptors stay data.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
ECOSYSTEMS_DIR = REPO_ROOT / "src" / "ecosystems"

_TOP_KEYS = {"schema", "name", "vars", "models", "smoke", "dispatch", "roles",
             "routes", "artifacts", "guard", "gate", "generate"}
# The one shipped-file marker in a sibling filename: everything after "<eco>.dist." is the
# destination filename at the built plugin's root.
_DIST_MARKER = ".dist."
# The write-gate protocols the shared adapter (src/hooks/hercules_gate.py) implements. A new host
# behavior is a new named protocol in that mutation-covered file — never logic in the descriptor.
_GATE_PROTOCOLS = {"pre_tool", "cursor_events"}
_GATE_KEYS = {
    "pre_tool": {"protocol", "tools", "path_keys", "nested_keys", "allow", "deny", "reason_key"},
    "cursor_events": {"protocol"},
}
_ROLE_NAMES = ("agent", "command", "persona", "default")
_MODES = {"preserve", "fields", "wrap", "plain", "toml_command"}
_BODY_POLICIES = {"keep", "lstrip_newlines", "strip_newlines"}
_FIELD_FROMS = {"frontmatter", "stem", "literal", "primary_mode", "flag_if_name_in"}
_ROUTE_KINDS = {"exact", "suffix_swap"}
_DISPATCHES = {"path", "frontmatter"}
_MODEL_TIERS = {"high", "medium", "low"}
_SMOKE_KEYS = {"cli", "test", "npm_package", "npm_version", "install"}
_GENERATORS = {"opencode_plugin_js": {"default_agent"}, "opencode_json": set()}
# Per-mode allowed role-spec keys — the schema's shape lives here, not in prose.
_ROLE_KEYS = {
    "preserve": {"mode", "resolve_model_tier", "required"},
    "fields": {"mode", "fields", "body"},
    "wrap": {"mode", "fields"},
    "plain": {"mode"},
    "toml_command": {"mode", "fields", "body"},
}
# Per-generator allowed field-spec keys.
_FIELD_KEYS = {
    "frontmatter": {"key", "from", "field", "render"},
    "stem": {"key", "from"},
    "literal": {"key", "from", "value"},
    "primary_mode": {"key", "from", "primary"},
    "flag_if_name_in": {"key", "from", "names", "value"},
}
_ROUTE_KEYS = {
    "exact": {"kind", "src", "dest"},
    "suffix_swap": {"kind", "prefix", "from_suffix", "to_suffix"},
}


class DescriptorError(ValueError):
    """Raised when an ecosystem descriptor uses a key or value outside the closed vocabulary."""


def _fail(name: str, message: str) -> None:
    raise DescriptorError(f"ecosystem descriptor {name!r}: {message}")  # pragma: no mutate


def _check_keys(name: str, what: str, obj: dict, allowed: set) -> None:
    unknown = sorted(set(obj) - allowed)
    if unknown:
        _fail(name, f"{what} has unknown key(s) {unknown} — allowed: {sorted(allowed)}")


def _check_str(name: str, what: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        _fail(name, f"{what} must be a non-empty string, got {value!r}")
    return value


def _check_rel_path(name: str, what: str, value: object) -> str:
    """A dest/src path inside the tree: relative, no parent escapes."""
    path = _check_str(name, what, value)
    if path.startswith("/") or ".." in path.split("/"):
        _fail(name, f"{what} must be a relative path without '..', got {path!r}")
    return path


@dataclass(frozen=True)
class FieldSpec:
    """One emitted frontmatter field: its output ``key`` and the named generator producing it."""

    key: str
    source: str                       # a _FIELD_FROMS member ("from" in JSON)
    field: Optional[str] = None       # frontmatter: the source frontmatter key
    render: bool = False              # frontmatter: token-render the value
    value: Optional[str] = None       # literal / flag_if_name_in: the emitted value
    primary: Optional[str] = None     # primary_mode: the primary agent name
    names: tuple = ()                 # flag_if_name_in: names that receive the flag


@dataclass(frozen=True)
class RoleSpec:
    """How one role (agent/command/persona/default) serializes for this ecosystem."""

    mode: str                         # a _MODES member
    fields: tuple = ()                # FieldSpec tuple (fields/wrap/toml_command)
    body: str = "keep"                # a _BODY_POLICIES member
    resolve_model_tier: bool = False  # preserve: swap model_tier for the resolved model, in-slot
    required: tuple = ()              # preserve: frontmatter keys that must exist


@dataclass(frozen=True)
class Route:
    """One src→dest relocation rule (ordered, first match wins, identity fallback)."""

    kind: str                         # a _ROUTE_KINDS member
    src: Optional[str] = None         # exact: the source rel
    dest: Optional[str] = None        # exact: the destination rel
    prefix: Optional[str] = None      # suffix_swap: required rel prefix
    from_suffix: Optional[str] = None
    to_suffix: Optional[str] = None


@dataclass(frozen=True)
class Artifact:
    """One inline-JSON file the build emits: ``content`` dumped canonically to ``dest``."""

    dest: str
    content: dict = field(default_factory=dict)
    versioned: bool = False           # substitute the single ${version} token (fail-loud)


@dataclass(frozen=True)
class Generate:
    """One named generator invocation (genuinely generated output, e.g. OpenCode's plugin.js)."""

    name: str
    args: dict = field(default_factory=dict)


@dataclass(frozen=True)
class EcosystemDescriptor:
    """The validated, immutable form of one ``src/ecosystems/<name>.json``."""

    name: str
    vars: dict
    models: dict
    smoke: dict
    dispatch: str
    roles: dict                       # role name -> RoleSpec
    routes: tuple = ()
    artifacts: tuple = ()
    guard: tuple = ()
    gate: Optional[dict] = None       # write-gate params, emitted verbatim as hooks/gate.json
    generate: tuple = ()


def _parse_field(name: str, raw: object) -> FieldSpec:
    if not isinstance(raw, dict):
        _fail(name, f"a field spec must be an object, got {raw!r}")
    source = raw.get("from")
    if source not in _FIELD_FROMS:
        _fail(name, f"field 'from' must be one of {sorted(_FIELD_FROMS)}, got {source!r}")
    _check_keys(name, f"field (from={source})", raw, _FIELD_KEYS[source])
    key = _check_str(name, "field 'key'", raw.get("key"))
    if source == "frontmatter":
        if not isinstance(raw.get("render", False), bool):
            _fail(name, "field 'render' must be a boolean")
        return FieldSpec(key=key, source=source,
                         field=_check_str(name, "field 'field'", raw.get("field")),
                         render=raw.get("render", False))
    if source == "literal":
        return FieldSpec(key=key, source=source, value=_check_str(name, "field 'value'", raw.get("value")))
    if source == "primary_mode":
        return FieldSpec(key=key, source=source, primary=_check_str(name, "field 'primary'", raw.get("primary")))
    if source == "flag_if_name_in":
        names = raw.get("names")
        if not isinstance(names, list) or not names:
            _fail(name, "field 'names' must be a non-empty list")
        return FieldSpec(key=key, source=source, value=_check_str(name, "field 'value'", raw.get("value")),
                         names=tuple(_check_str(name, "field 'names' entry", n) for n in names))
    return FieldSpec(key=key, source=source)  # stem


def _parse_role(name: str, role: str, raw: object) -> RoleSpec:
    if not isinstance(raw, dict):
        _fail(name, f"role {role!r} must be an object, got {raw!r}")
    mode = raw.get("mode")
    if mode not in _MODES:
        _fail(name, f"role {role!r} 'mode' must be one of {sorted(_MODES)}, got {mode!r}")
    _check_keys(name, f"role {role!r} (mode={mode})", raw, _ROLE_KEYS[mode])
    body = raw.get("body", "keep")
    if body not in _BODY_POLICIES:
        _fail(name, f"role {role!r} 'body' must be one of {sorted(_BODY_POLICIES)}, got {body!r}")
    fields_raw = raw.get("fields", [])
    if mode in ("fields", "wrap", "toml_command"):
        if not isinstance(fields_raw, list) or not fields_raw:
            _fail(name, f"role {role!r} (mode={mode}) requires a non-empty 'fields' list")
    fields = tuple(_parse_field(name, f) for f in fields_raw)
    if mode == "wrap" and any(f.source != "literal" for f in fields):
        _fail(name, f"role {role!r}: wrap-mode fields must all be literals (generated frontmatter)")
    if mode == "toml_command" and [f.key for f in fields] != ["description"]:
        _fail(name, f"role {role!r}: toml_command emits exactly one field, 'description'")
    if not isinstance(raw.get("resolve_model_tier", False), bool):
        _fail(name, f"role {role!r} 'resolve_model_tier' must be a boolean")
    required = raw.get("required", [])
    if not isinstance(required, list):
        _fail(name, f"role {role!r} 'required' must be a list")
    return RoleSpec(mode=mode, fields=fields, body=body,
                    resolve_model_tier=raw.get("resolve_model_tier", False),
                    required=tuple(_check_str(name, "'required' entry", r) for r in required))


def _parse_route(name: str, raw: object) -> Route:
    if not isinstance(raw, dict):
        _fail(name, f"a route must be an object, got {raw!r}")
    kind = raw.get("kind")
    if kind not in _ROUTE_KINDS:
        _fail(name, f"route 'kind' must be one of {sorted(_ROUTE_KINDS)}, got {kind!r}")
    _check_keys(name, f"route (kind={kind})", raw, _ROUTE_KEYS[kind])
    if kind == "exact":
        return Route(kind=kind, src=_check_rel_path(name, "route 'src'", raw.get("src")),
                     dest=_check_rel_path(name, "route 'dest'", raw.get("dest")))
    return Route(kind=kind, prefix=_check_str(name, "route 'prefix'", raw.get("prefix")),
                 from_suffix=_check_str(name, "route 'from_suffix'", raw.get("from_suffix")),
                 to_suffix=_check_str(name, "route 'to_suffix'", raw.get("to_suffix")))


def _parse_artifact(name: str, raw: object) -> Artifact:
    if not isinstance(raw, dict):
        _fail(name, f"an artifact must be an object, got {raw!r}")
    _check_keys(name, "artifact", raw, {"dest", "content", "versioned"})
    if not isinstance(raw.get("content"), dict):
        _fail(name, "artifact 'content' must be a JSON object")
    if not isinstance(raw.get("versioned", False), bool):
        _fail(name, "artifact 'versioned' must be a boolean")
    return Artifact(dest=_check_rel_path(name, "artifact 'dest'", raw.get("dest")),
                    content=raw["content"], versioned=raw.get("versioned", False))


def _parse_gate(name: str, raw: object) -> dict:
    if not isinstance(raw, dict):
        _fail(name, f"'gate' must be an object, got {raw!r}")
    protocol = raw.get("protocol")
    if protocol not in _GATE_PROTOCOLS:
        _fail(name, f"gate 'protocol' must be one of {sorted(_GATE_PROTOCOLS)}, got {protocol!r}")
    _check_keys(name, f"gate (protocol={protocol})", raw, _GATE_KEYS[protocol])
    if protocol == "pre_tool":
        tools = raw.get("tools")
        if not isinstance(tools, dict) or not tools:
            _fail(name, "gate 'tools' must be a non-empty object mapping host tool → canonical tool")
        for host_tool, canonical in tools.items():
            _check_str(name, f"gate tools[{host_tool!r}]", canonical)
        path_keys = raw.get("path_keys")
        if not isinstance(path_keys, list) or not path_keys:
            _fail(name, "gate 'path_keys' must be a non-empty list")
        for key in ("deny",):
            if not isinstance(raw.get(key), dict):
                _fail(name, f"gate {key!r} must be an object (the host's decision shape)")
        if "allow" in raw and not isinstance(raw["allow"], dict):
            _fail(name, "gate 'allow' must be an object when present")
        _check_str(name, "gate 'reason_key'", raw.get("reason_key"))
        if "nested_keys" in raw and not isinstance(raw["nested_keys"], list):
            _fail(name, "gate 'nested_keys' must be a list")
    return dict(raw)


def _parse_generate(name: str, raw: object) -> Generate:
    if not isinstance(raw, dict):
        _fail(name, f"a generate step must be an object, got {raw!r}")
    _check_keys(name, "generate", raw, {"name", "args"})
    gen = raw.get("name")
    if gen not in _GENERATORS:
        _fail(name, f"generate 'name' must be one of {sorted(_GENERATORS)}, got {gen!r}")
    args = raw.get("args", {})
    if not isinstance(args, dict):
        _fail(name, "generate 'args' must be an object")
    _check_keys(name, f"generate {gen!r} args", args, _GENERATORS[gen])
    missing = sorted(_GENERATORS[gen] - set(args))
    if missing:
        _fail(name, f"generate {gen!r} is missing required arg(s) {missing}")
    for key, value in args.items():
        _check_str(name, f"generate arg {key!r}", value)
    return Generate(name=gen, args=args)


def parse_descriptor(name: str, raw: object) -> EcosystemDescriptor:
    """Validate *raw* (a decoded ``<name>.json``) against the closed vocabulary; return the dataclass."""
    if not isinstance(raw, dict):
        _fail(name, f"descriptor must be a JSON object, got {type(raw).__name__}")
    _check_keys(name, "descriptor", raw, _TOP_KEYS)
    for key in ("schema", "name", "vars", "models", "smoke", "dispatch", "roles", "routes"):
        if key not in raw:
            _fail(name, f"missing required key {key!r}")
    if raw["schema"] != 1:
        _fail(name, f"'schema' must be 1, got {raw['schema']!r}")
    if raw["name"] != name:
        _fail(name, f"'name' must equal the filename stem, got {raw['name']!r}")
    if not isinstance(raw["vars"], dict) or not raw["vars"]:
        _fail(name, "'vars' must be a non-empty object")
    for key, value in raw["vars"].items():
        if not isinstance(value, str):
            _fail(name, f"vars[{key!r}] must be a string, got {value!r}")
    models = raw["models"]
    if not isinstance(models, dict) or not models:
        _fail(name, "'models' must be a non-empty object")
    _check_keys(name, "'models'", models, _MODEL_TIERS)
    for tier, value in models.items():
        if value is not None and not isinstance(value, str):
            _fail(name, f"models[{tier!r}] must be a string or null, got {value!r}")
    smoke = raw["smoke"]
    if not isinstance(smoke, dict):
        _fail(name, "'smoke' must be an object")
    _check_keys(name, "'smoke'", smoke, _SMOKE_KEYS)
    for key in ("cli", "test"):
        _check_str(name, f"smoke[{key!r}]", smoke.get(key))
    if raw["dispatch"] not in _DISPATCHES:
        _fail(name, f"'dispatch' must be one of {sorted(_DISPATCHES)}, got {raw['dispatch']!r}")
    roles_raw = raw["roles"]
    if not isinstance(roles_raw, dict):
        _fail(name, "'roles' must be an object")
    if sorted(roles_raw) != sorted(_ROLE_NAMES):
        _fail(name, f"'roles' must define exactly {sorted(_ROLE_NAMES)}, got {sorted(roles_raw)}")
    for key in ("routes", "artifacts", "guard", "generate"):
        if key in raw and not isinstance(raw[key], list):
            _fail(name, f"{key!r} must be a list")
    guard = tuple(_check_str(name, "'guard' entry", g) for g in raw.get("guard", []))
    for module in guard:
        if "/" in module:
            _fail(name, f"'guard' entries are module filenames (no '/'), got {module!r}")
    return EcosystemDescriptor(
        name=name,
        vars=dict(raw["vars"]),
        models=dict(models),
        smoke=dict(smoke),
        dispatch=raw["dispatch"],
        roles={role: _parse_role(name, role, spec) for role, spec in roles_raw.items()},
        routes=tuple(_parse_route(name, r) for r in raw["routes"]),
        artifacts=tuple(_parse_artifact(name, a) for a in raw.get("artifacts", [])),
        guard=guard,
        gate=_parse_gate(name, raw["gate"]) if "gate" in raw else None,
        generate=tuple(_parse_generate(name, g) for g in raw.get("generate", [])),
    )


def load(path: Path) -> EcosystemDescriptor:
    """Load and validate one descriptor file (the filename stem is the ecosystem name)."""
    return parse_descriptor(path.stem, json.loads(path.read_text(encoding="utf-8")))


def _validate_layout(root: Path, names: set) -> None:
    """Enforce the directory's definitive schema: every non-descriptor file is
    ``<known-eco>.dist.<dest>`` with a flat, non-empty dest. A stray file, an unknown ecosystem
    prefix, or a nested dest fails LOUDLY — nothing in this directory is ever silently ignored.
    (Hidden dotfiles — editor/OS droppings — are the one tolerated exception.)"""
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.suffix == ".json" or path.name.startswith("."):
            continue
        eco, marker, dest = path.name.partition(_DIST_MARKER)
        if not marker or eco not in names or not dest:
            raise DescriptorError(  # pragma: no mutate - message text only
                f"src/ecosystems/{path.name}: every shipped file must be named "
                f"'<ecosystem>{_DIST_MARKER}<dest-filename>' for a known ecosystem {sorted(names)}"
            )


def dist_files(name: str, root: Path = ECOSYSTEMS_DIR) -> dict:
    """The shipped sibling files for ecosystem *name*: ``{dest_filename: source_path}``, derived
    purely from the filename schema (``<name>.dist.<dest>`` → plugin-root ``<dest>``) — the
    deterministic input→output contract the build and its tests both read."""
    prefix = name + _DIST_MARKER
    return {p.name[len(prefix):]: p
            for p in sorted(root.glob(prefix + "*")) if p.is_file()}


_CACHE: dict = {}


def discover(root: Path = ECOSYSTEMS_DIR) -> dict:
    """All descriptors under *root*, keyed by name, sorted — cached per root (the build reads many
    times; descriptors are immutable within a run). Validates the whole directory layout, so a
    malformed sibling file fails the FIRST build step, not a late copy."""
    key = str(root)
    if key not in _CACHE:
        found = {d.name: d for d in (load(p) for p in sorted(root.glob("*.json")))}
        _validate_layout(root, set(found))
        _CACHE[key] = found
    return _CACHE[key]
