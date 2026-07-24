#!/usr/bin/env bash
#
# Dual-run parity gate: does the TypeScript compiler behave identically to the Python one?
#
# This is the mechanical oracle behind every port commit in the migration. Each fixture under
# tests/testdata/parity/ is fed to BOTH engines through the same JSON protocol
# (scripts/ci/parity_run.py and .ts-out/bin/parityRun.mjs) and their canonical output is byte-diffed.
#
# Fixtures are data, not code: adding a case is a JSON file, and neither engine can special-case
# one, because neither knows which fixture it is running.
#
# What is compared: the return value, the error MESSAGE on the failure path, and — for fixtures
# that declare `capture` — the sha256 AND FILE MODE of every written file. Mode matters because a
# content comparison cannot see it: Python's shutil.copyfile leaves the destination at the umask
# while Node's fs.copyFileSync propagates the source's permission bits, and every file in the
# committed dist/ tree is 100644, so the divergence would be invisible to `diff -r` and surface
# later as a spurious permission change.
set -euo pipefail

cd "$(dirname "$0")/../.."

runner_ts=".ts-out/bin/parityRun.mjs"
if [[ ! -f "${runner_ts}" ]]; then
  echo "parity: ${runner_ts} is missing - run \`make compile\` first." >&2
  exit 1
fi

work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT

total=0
failed=0

for fixture in tests/testdata/parity/*.in.json; do
  name="$(basename "${fixture}" .in.json)"
  total=$((total + 1))

  py_out="${work}/${name}.python"
  ts_out="${work}/${name}.node"

  # A runner CRASH (as opposed to the function under test raising, which the runner reports as
  # {"ok": false}) must fail loudly rather than compare two empty files as equal.
  if ! python -m scripts.ci.parity_run < "${fixture}" > "${py_out}" 2> "${py_out}.err"; then
    echo "FAIL ${name}: the python runner itself crashed" >&2
    sed 's/^/    /' "${py_out}.err" >&2
    failed=$((failed + 1))
    continue
  fi
  if ! node "${runner_ts}" < "${fixture}" > "${ts_out}" 2> "${ts_out}.err"; then
    echo "FAIL ${name}: the node runner itself crashed" >&2
    sed 's/^/    /' "${ts_out}.err" >&2
    failed=$((failed + 1))
    continue
  fi

  if ! diff -q "${py_out}" "${ts_out}" > /dev/null; then
    failed=$((failed + 1))
    echo "FAIL ${name}" >&2
    echo "  fixture: ${fixture}" >&2
    diff -u --label "python" "${py_out}" --label "node" "${ts_out}" | sed 's/^/    /' >&2
    echo >&2
  fi
done

if [[ "${failed}" -gt 0 ]]; then
  echo "parity: ${failed}/${total} fixtures DIVERGED between python and node." >&2
  echo "The TypeScript port does not reproduce the Python behaviour. Fix the port, not the fixture." >&2
  exit 1
fi

echo "parity: ${total}/${total} fixtures produce byte-identical results (python vs node)"

# ── Leg 2 (commit 8+): full-tree parity ──────────────────────────────────────
#
# Both compilers render EVERY target from scratch into isolated temp trees, called directly
# (build_target/buildTarget) rather than through either CLI's argparse/argv layer, so this compares
# the two RENDERERS, not two option parsers. `diff -r` catches content drift; a separate `stat`-mode
# walk catches a permission drift `diff -r` cannot see (Python's shutil.copyfile leaves the
# destination at the umask, Node's fs.copyFileSync propagates the source's bits — every file in the
# committed dist/ tree is 100644, so this divergence is invisible to content-only comparison and
# would surface later as a spurious permission change).
targets="$(python -c 'from scripts.build import descriptor; print("\n".join(descriptor.names()))')"

tree_failed=0
for target in ${targets}; do
  py_tree="${work}/tree-py-${target}"
  ts_tree="${work}/tree-ts-${target}"

  if ! python -c "
from pathlib import Path
from scripts.build.cli import build_target
build_target('${target}', Path('${py_tree}'))
" 2> "${work}/tree-py-${target}.err"; then
    echo "FAIL full-tree ${target}: the python renderer crashed" >&2
    sed 's/^/    /' "${work}/tree-py-${target}.err" >&2
    tree_failed=$((tree_failed + 1))
    continue
  fi
  if ! node --input-type=module -e "
import { buildTarget } from './${runner_ts%/*}/cli.mjs';
buildTarget('${target}', '${ts_tree}');
" 2> "${work}/tree-ts-${target}.err"; then
    echo "FAIL full-tree ${target}: the node renderer crashed" >&2
    sed 's/^/    /' "${work}/tree-ts-${target}.err" >&2
    tree_failed=$((tree_failed + 1))
    continue
  fi

  if ! diff -rq "${py_tree}" "${ts_tree}" > "${work}/tree-${target}.diff"; then
    tree_failed=$((tree_failed + 1))
    echo "FAIL full-tree ${target}: content diverged" >&2
    sed 's/^/    /' "${work}/tree-${target}.diff" >&2
    continue
  fi

  mode_mismatch=0
  while IFS= read -r -d '' rel; do
    py_mode="$(stat -f '%Lp' "${py_tree}/${rel}" 2>/dev/null || stat -c '%a' "${py_tree}/${rel}")"
    ts_mode="$(stat -f '%Lp' "${ts_tree}/${rel}" 2>/dev/null || stat -c '%a' "${ts_tree}/${rel}")"
    if [[ "${py_mode}" != "${ts_mode}" ]]; then
      echo "FAIL full-tree ${target}: ${rel} mode diverged (python ${py_mode} vs node ${ts_mode})" >&2
      mode_mismatch=1
    fi
  done < <(cd "${py_tree}" && find . -type f -print0)
  if [[ "${mode_mismatch}" -ne 0 ]]; then
    tree_failed=$((tree_failed + 1))
  fi
done

if [[ "${tree_failed}" -gt 0 ]]; then
  echo "parity: full-tree leg DIVERGED for ${tree_failed} target(s)." >&2
  exit 1
fi

echo "parity: full-tree leg — ${targets} all byte-identical (content + mode, python vs node)" | tr '\n' ' '
echo
