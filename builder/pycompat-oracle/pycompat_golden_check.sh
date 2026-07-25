#!/usr/bin/env bash
#
# Freshness gate for tests/testdata/pycompat-golden.json.
#
# builder/pyCompat.mts reproduces Python's character classification, and that
# classification is UNICODE-VERSION dependent: CPython 3.9 ships Unicode 13.0 and 3.12 ships 15.0,
# which disagree on 93 code points below U+3101. The golden was once generated on a developer's
# 3.12 while CI runs 3.9, so the shipped table encoded a Unicode version the parity harness never
# compares against — and nothing failed, because no test exercised those code points.
#
# This regenerates the dump with the interpreter actually running and diffs it against the committed
# file, the same shape as the dist/ byte-drift gate. Pinning one end without the other is exactly
# the reader-only pin the code-of-conduct warns about.
set -euo pipefail

cd "$(dirname "$0")/../.."

work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT
fresh="${work}/pycompat-golden.json"

# Lead with the version, not a thousand-line diff: a mismatch is almost always "you are not running
# the interpreter CI pins", and the remedy is to switch interpreters rather than to regenerate.
committed_unicode="$(python -c 'import json,sys; print(json.load(open("tests/testdata/pycompat-golden.json"))["unidataVersion"])')"
running_unicode="$(python -c 'import unicodedata; print(unicodedata.unidata_version)')"

if [[ "${committed_unicode}" != "${running_unicode}" ]]; then
  echo "pycompat golden targets Unicode ${committed_unicode}; this interpreter ships ${running_unicode}." >&2
  echo >&2
  echo "  running: $(python -c 'import sys; print(sys.version.split()[0])')" >&2
  echo "  CI pins: python-version 3.9 in .github/workflows/ci.yml" >&2
  echo >&2
  echo "The tables must encode the Unicode database the parity harness actually compares against," >&2
  echo "which is CI's. Re-run this under the pinned interpreter; only regenerate the golden if you" >&2
  echo "are deliberately moving the whole project to a new Python." >&2
  exit 1
fi

python builder/pycompat-oracle/gen_pycompat_golden.py "${fresh}"

if diff -q tests/testdata/pycompat-golden.json "${fresh}" > /dev/null; then
  echo "pycompat golden: current for $(python -c 'import unicodedata; print("Unicode " + unicodedata.unidata_version)')"
  exit 0
fi

echo "pycompat golden is STALE for the interpreter running here." >&2
echo >&2
diff -u --label committed tests/testdata/pycompat-golden.json --label regenerated "${fresh}" \
  | head -40 | sed 's/^/    /' >&2
echo >&2
echo "Regenerate it and rebuild the NON_PRINTABLE table in builder/pyCompat.mts:" >&2
echo "    python builder/pycompat-oracle/gen_pycompat_golden.py" >&2
echo "The table and the golden must encode the SAME Unicode version as the CI-pinned CPython." >&2
exit 1
