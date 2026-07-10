"""Spec 01 KEYSTONE GATE — the byte-identity primitives against the real corpus.

``dist/claude-code`` byte-identity (Spec 02) rests entirely on these two properties holding for
*every* current ``plugin/`` file:
  1. ``split_document`` is lossless: ``(fm_block or "") + body == original``.
  2. ``render_frontmatter(parse_frontmatter(block))`` reproduces the frontmatter block byte-for-byte.

Frozen for spec-01-build-compiler-core.
"""
from pathlib import Path

import pytest

from scripts.build.parse import parse_frontmatter, render_frontmatter, split_document

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN = REPO_ROOT / "plugin"
PLUGIN_MD = sorted(str(p.relative_to(REPO_ROOT)) for p in PLUGIN.rglob("*.md"))


def test_corpus_is_non_empty():
    # Guards the parametrized tests from silently passing on an empty set.
    assert len(PLUGIN_MD) >= 25


@pytest.mark.parametrize("rel", PLUGIN_MD)
def test_split_document_is_lossless(rel):
    raw = (REPO_ROOT / rel).read_text(encoding="utf-8")
    fm_block, body = split_document(raw)
    assert (fm_block or "") + body == raw


@pytest.mark.parametrize("rel", PLUGIN_MD)
def test_frontmatter_block_round_trips_byte_for_byte(rel):
    raw = (REPO_ROOT / rel).read_text(encoding="utf-8")
    fm_block, _ = split_document(raw)
    if fm_block is None:
        pytest.skip("no frontmatter")
    meta, _ = parse_frontmatter(fm_block)
    # render_frontmatter yields the fenced block without a trailing newline; the block carries one.
    assert render_frontmatter(meta) + "\n" == fm_block
