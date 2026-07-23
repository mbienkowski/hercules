"""Token-parity harness, Python side. Temporary — deleted with the Python compiler.

Proves that js-tiktoken produces byte-identical cl100k_base tokenization to Python's tiktoken
before any token-counting code changes language. The budgets in tests/testdata/thresholds.json are
hard gates (a2a-core-token-budget is 1050 tokens); a one-token disagreement is a spec change, not a
port, so this runs as a go/no-go spike ahead of the metrics migration.

Two modes:

  corpus <out.json>   Build the corpus: every exact string the threshold suite tokenizes today,
                      plus an adversarial set. Python owns this step because it owns the A2A core
                      extraction the thresholds depend on.
  dump <corpus.json>  Tokenize each corpus entry and print canonical JSON to stdout.

Splitting corpus construction from tokenization is what makes the comparison meaningful: both
engines tokenize THE SAME strings, so the tokenizer is the only variable. If each side resolved
its own file list, a disagreement about which files to read would masquerade as agreement about
how to tokenize them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.metrics.a2a_grammar import extract_a2a_core  # noqa: E402
from tests.metrics.threshold_runner import load_thresholds, resolve_targets  # noqa: E402

# Metrics in thresholds.json that consume the tokenizer. Entry-count metrics do not.
_TOKEN_METRICS = {"token_count", "core_token_count"}

# Categories where a pure-JS BPE port is most likely to diverge from the Rust/WASM original.
# Named individually so a failure report says WHICH class broke, not just "the corpus".
_ADVERSARIAL: dict[str, str] = {
    "zwj-emoji-family": "👩‍👦‍👦 👩‍👧‍👦 👨‍👩‍👧‍👦",
    "skin-tone-modifiers": "🧑🏾‍💻️🧑🏿‍🎓️🧑🏿‍🏭️🧑🏻‍💻️",
    "regional-indicators": "🇨🇿🇵🇱🇬🇧🇺🇸🇯🇵",
    "cjk": "是美國一個人工智能研究實驗室 由非營利組織OpenAI Inc",
    "mixed-rtl": "العربية עברית mixed with latin",
    "whitespace-runs": "New lines\n\n\n\n\n       Spaces\t\t\ttabs   \n  trailing   ",
    "special-token-literal": "<|endoftext|> <|im_start|>test<|im_end|> <|fim_prefix|>",
    "code-fence": "```python\ndef f(x: int) -> int:\n    return x ** 2  # comment\n```",
    "markdown-structure": "- item one\n- item two\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n> quote\n",
    "combining-marks": "é vs é — á é í (NFC vs NFD)",
    "zero-width": "zero​width‌joiner‍test﻿",
    "long-repeat": "ab" * 512,
    "empty": "",
    "single-space": " ",
    "lone-newline": "\n",
}


def build_corpus(repo_root: Path) -> list[dict[str, str]]:
    """Every exact string the threshold suite tokenizes, plus the adversarial set."""
    entries: list[dict[str, str]] = []
    seen: set[str] = set()

    checks = load_thresholds(repo_root / "tests" / "testdata" / "thresholds.json")
    for check in checks:
        if check.metric not in _TOKEN_METRICS:
            continue
        for path in resolve_targets(repo_root, check.target):
            text = path.read_text(encoding="utf-8")
            rel = str(path.relative_to(repo_root))

            if check.metric == "token_count":
                key = f"file:{rel}"
                if key not in seen:
                    seen.add(key)
                    entries.append({"id": key, "text": text})
            else:
                # core_token_count tokenizes only the fenced Core block. Its boundaries are exactly
                # where a substring tokenization could diverge from the whole file's, so it is
                # compared as its own entry rather than assumed to follow from the file.
                core, ok = extract_a2a_core(text)
                if not ok:
                    raise SystemExit(f"token-parity: no A2A core block in {rel}")
                key = f"core:{rel}"
                if key not in seen:
                    seen.add(key)
                    entries.append({"id": key, "text": core})

    for name, text in _ADVERSARIAL.items():
        entries.append({"id": f"adversarial:{name}", "text": text})

    entries.sort(key=lambda e: e["id"])
    return entries


def dump(corpus_path: Path) -> str:
    """Tokenize every corpus entry; return canonical JSON both engines must match byte-for-byte.

    A refusal is part of the contract, not an obstacle to it. Both tiktoken and js-tiktoken reject
    text containing a special token such as ``<|endoftext|>`` rather than encoding it, so an entry
    that raises is recorded as ``throws: true`` and compared like any other result. Dropping such
    entries from the corpus would leave the two engines free to disagree exactly where a document
    smuggles a control token into the budget.
    """
    import tiktoken

    encoder = tiktoken.get_encoding("cl100k_base")
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    out = []
    for entry in corpus:
        try:
            out.append({"id": entry["id"], "throws": False, "tokens": encoder.encode(entry["text"])})
        except ValueError:
            out.append({"id": entry["id"], "throws": True, "tokens": None})
    return json.dumps(out, indent=1, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    mode, target = argv[1], Path(argv[2])
    if mode == "corpus":
        corpus = build_corpus(repo_root)
        target.write_text(
            json.dumps(corpus, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"token-parity: corpus of {len(corpus)} entries -> {target}", file=sys.stderr)
        return 0
    if mode == "dump":
        sys.stdout.write(dump(target))
        return 0
    print(f"token-parity: unknown mode {mode!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
