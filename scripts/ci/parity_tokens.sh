#!/usr/bin/env bash
#
# Token-parity gate: does js-tiktoken tokenize cl100k_base byte-identically to Python's tiktoken,
# on THIS repository's actual corpus?
#
# This is the go/no-go spike for migrating tests/metrics/ off Python. The token budgets in
# tests/testdata/thresholds.json are hard gates, so a single-token disagreement is a spec change
# rather than a port, and the migration must stop rather than quietly re-baseline them.
#
# Python builds the corpus (it owns the A2A core extraction the thresholds depend on); both engines
# then tokenize the SAME strings. That isolates the tokenizer as the only variable — if each side
# resolved its own file list, a disagreement about which files to read would masquerade as
# agreement about how to tokenize them.
#
# Compared as token ARRAYS, not counts: two different tokenizations can coincidentally sum to the
# same length, and a budget that happens to match today would drift the moment the text changed.
set -euo pipefail

cd "$(dirname "$0")/../.."

work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT

corpus="${work}/corpus.json"
py_out="${work}/tokens.python.json"
ts_out="${work}/tokens.node.json"

python -m scripts.ci.token_parity corpus "${corpus}"

python -m scripts.ci.token_parity dump "${corpus}" > "${py_out}"
node .ts-out/bin/tokenParity.mjs "${corpus}" > "${ts_out}"

entries="$(python -c "import json,sys; print(len(json.load(open(sys.argv[1]))))" "${corpus}")"

if diff -q "${py_out}" "${ts_out}" > /dev/null; then
  echo "token parity: ${entries}/${entries} corpus entries tokenize identically (cl100k_base)"
else
  echo "TOKEN PARITY FAILED — js-tiktoken and Python tiktoken disagree." >&2
  echo >&2
  python - "${corpus}" "${py_out}" "${ts_out}" >&2 <<'PYEOF'
import json, sys
corpus = {e["id"]: e["text"] for e in json.load(open(sys.argv[1], encoding="utf-8"))}
py = {e["id"]: e["tokens"] for e in json.load(open(sys.argv[2], encoding="utf-8"))}
ts = {e["id"]: e["tokens"] for e in json.load(open(sys.argv[3], encoding="utf-8"))}
for key in sorted(py):
    if py[key] == ts.get(key):
        continue
    a, b = py[key], ts.get(key, [])
    at = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    print(f"  {key}: python={len(a)} tokens, node={len(b)} tokens, first differs at index {at}")
    print(f"    python[{at}:{at+6}] = {a[at:at+6]}")
    print(f"    node  [{at}:{at+6}] = {b[at:at+6]}")
    print(f"    context: {corpus[key][max(0, at-40):at+40]!r}")
PYEOF
  echo >&2
  echo "This is a SPEC CHANGE, not a port: every token budget in" >&2
  echo "tests/testdata/thresholds.json was generated with Python tiktoken. Stop the migration" >&2
  echo "and re-baseline the affected budgets in one reviewed commit before going further." >&2
  exit 1
fi

# Self-check: the harness must be able to FAIL. Perturb one corpus entry on the Node side only and
# confirm the diff catches it — otherwise a green result proves nothing about the comparison.
python - "${corpus}" "${work}/corpus.perturbed.json" <<'PYEOF'
import json, sys
corpus = json.load(open(sys.argv[1], encoding="utf-8"))
corpus[0]["text"] += "x"
json.dump(corpus, open(sys.argv[2], "w", encoding="utf-8"), indent=1, ensure_ascii=False)
PYEOF

node .ts-out/bin/tokenParity.mjs "${work}/corpus.perturbed.json" > "${work}/tokens.perturbed.json"
if diff -q "${py_out}" "${work}/tokens.perturbed.json" > /dev/null; then
  echo "TOKEN PARITY HARNESS IS BROKEN: a perturbed corpus still compared equal." >&2
  exit 1
fi
echo "token parity: harness self-check passed (a one-byte change is detected)"
