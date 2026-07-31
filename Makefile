.PHONY: test test-mutation test-smoke install install-py install-ts build build-check \
        typecheck compile test-py test-ts mutation-py mutation-ts \
        complexity-scan complexity-scan-ts complexity-scan-py vulnerability-scan \
        ci-build validate smoke-matrix smoke-install smoke-run smoke-annotate bless-content \
        release-verify release-meta release-version changelog release-commit npm-creds release-npm

# ── Which runtime owns what ──────────────────────────────────────────────────
# Python owns src/hooks/ and src/tools/ (both shipped to users); TypeScript owns src/{builder,release,metrics}/. The
# -py/-ts suffix is the same string in the make target, the CI job id and the CI display name, so a
# red check reproduces by copying its name into a terminal. Keep it that way.

install: install-py install-ts

install-py:
	pip install -e ".[dev]"

install-ts:
	npm ci

build: compile
	node .ts-out/builder/bin/cli.mjs --target all

build-check: compile
	node .ts-out/builder/bin/cli.mjs --target all --check

test: test-py test-ts

# The Python suite: src/hooks/ and src/tools/ (the two islands, see CODE_OF_CONDUCT.md § Testing)
# plus the repo-wide meta-guards under src/commons/repo/.
test-py: build-check
	python -m pytest src/commons/repo/ src/hooks/tests/ src/tools/tests/ -v --cov=src/hooks --cov=src/tools --cov-branch --cov-report=term-missing --cov-fail-under=90

test-ts:
	npm run typecheck
	npx vitest run --coverage

# Type-check both TypeScript projects without running anything.
typecheck:
	npm run typecheck

# `tsc -b` trusts tsbuildinfo, so drop the stamp when .ts-out/ is gone or compile becomes a no-op.
# `tsc` itself may be absent: release.yml's privileged job runs no `npm ci` and downloads a compiled
# .ts-out/ instead, so every compile-dependent target must work there too — hence the fallback to an
# already-populated .ts-out/, and a loud failure only when neither is available.
compile:
	@[ -d .ts-out ] || rm -f tsconfig.build.tsbuildinfo tsconfig.tests.tsbuildinfo
	@if [ -x node_modules/.bin/tsc ]; then \
		npm run compile; \
	elif [ -d .ts-out ] && [ -n "$$(ls -A .ts-out 2>/dev/null)" ]; then \
		echo "no local TypeScript toolchain (node_modules/.bin/tsc missing) — using the existing .ts-out/ as-is"; \
	else \
		echo "ERROR: .ts-out/ is missing or empty and there is no local TypeScript toolchain to compile it — run 'make install-ts' first" >&2; \
		exit 1; \
	fi

# ── Mutation testing — a developer tool, not a gate ──────────────────────────
# Run by hand, on the change you are working on; no CI job runs these and no threshold blocks a merge
# or a release (src/release/mutation-gate.json). Both report the kill rate and the surviving mutants,
# which is what a campaign is actually read for; what to do about a survivor stays a human call.
test-mutation: mutation-py mutation-ts

mutation-py:
	mutmut run || true
	mutmut results | tee mutmut-results.txt
	python src/release/check_mutation_gate.py

# The report script reads Stryker's JSON report and applies the same thresholds as the Python one
# (src/release/mutation-gate.json), so the two runtimes cannot drift to two answers.
mutation-ts: compile
	npx stryker run || true
	node .ts-out/release/bin/mutationGate.mjs

# ── Complexity gate ───────────────────────────────────────────────────────────
# Every first-party function stays under 15 on both cyclomatic and cognitive complexity, the same
# ceiling on both runtimes. Tests are excluded — a table-driven spec is legitimately branchy and is
# not shipped. See CODE_OF_CONDUCT.md § Complexity.
complexity-scan: complexity-scan-ts complexity-scan-py

# TypeScript domains (compiler / release / metrics). Config + ceiling live in eslint.config.mjs.
complexity-scan-ts:
	npx eslint --max-warnings=0 .

# Shipped Python, both islands. --select restricts flake8 to the two complexity checks (C901 =
# mccabe cyclomatic, CCR001 = cognitive); --extend-exclude drops each island's own tests.
complexity-scan-py:
	flake8 --select=C901,CCR001 --max-complexity=15 --max-cognitive-complexity=15 --extend-exclude=tests src/hooks src/tools

# ── Dependency vulnerability scan ─────────────────────────────────────────────
# Fail on any high or critical CVE. npm carries the entire dependency surface: the shipped plugin is
# zero-runtime-dep and the Python hooks are stdlib-only, so the whole exposure is the dev toolchain
# in package-lock.json. --audit-level=high leaves moderate and low visible but non-blocking.
vulnerability-scan:
	npm audit --audit-level=high

# Live CLI smoke checks: do the built plugins install and load in the real binaries? Each leg skips
# silently when its CLI is not installed locally.
test-smoke: build-check
	npx vitest run --config vitest.smoke.config.mts

# Re-baseline the shipped-content hash manifest after an INTENTIONAL content edit. Commit the manifest
# with the edit that caused it and say in the message what behaviour changed — the pin exists to make
# that one deliberate step.
#
# Depends on build-check, not just build: `make build` writes what the source declares but does not
# prune, so a stray file dropped into dist/ survives a rebuild and would be hashed straight into the
# manifest. build-check byte-compares the whole tree and is what actually catches that.
bless-content: build-check
	BLESS_CONTENT=1 npx vitest run src/content/tests/workflowAndProtocols/protocolFiles.spec.ts \
	  src/content/tests/workflowAndProtocols/normativeGolden.spec.ts
	BLESS_CONTENT=1 npx vitest run src/content/tests/docsAndPlugin/shippedContentManifest.spec.ts
	@echo "re-blessed: 4 goldens + the shipped-content manifest. Commit them with the edit that caused them."

# ── CI entry points ──────────────────────────────────────────────────────────
# The GitHub Actions workflows call only `make <target>`, so every step is testable and runnable
# locally. Add a target plus a src/release/ci/ script, never an inline YAML block.

ci-build:
	bash src/release/ci/build_gates.sh

validate: compile
	node .ts-out/release/bin/validatePackage.mjs

smoke-matrix: compile
	node .ts-out/release/bin/smokeMatrix.mjs

smoke-install:
	bash src/release/ci/install_cli.sh

smoke-run:
	bash src/release/ci/run_smoke.sh

smoke-annotate:
	bash src/release/ci/annotate_smoke.sh

# ── Release entry points (release.yml) ───────────────────────────────────────
release-verify:
	bash src/release/ci/release_verify_checkout.sh

release-meta:
	bash src/release/ci/release_meta.sh

release-version: compile
	node .ts-out/release/bin/setVersion.mjs "$${NEW_VERSION}"

changelog: compile
	node .ts-out/release/bin/updateChangelog.mjs

release-commit:
	bash src/release/ci/release_commit.sh

npm-creds:
	bash src/release/ci/npm_creds.sh

release-npm:
	npm publish --access public
