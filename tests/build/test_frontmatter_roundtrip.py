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
PLUGIN = REPO_ROOT / "dist" / "claude-code"
PLUGIN_MD = sorted(str(p.relative_to(REPO_ROOT)) for p in PLUGIN.rglob("*.md"))


def test_the_real_plugin_file_corpus_is_not_accidentally_empty():
    """The checks below only prove anything if they actually run against the real set of
    shipped plugin files. This guards against that file discovery silently finding nothing,
    which would let every check that follows pass without testing anything at all."""
    assert len(PLUGIN_MD) >= 25


@pytest.mark.parametrize("rel", PLUGIN_MD)
def test_splitting_a_file_into_metadata_and_content_loses_no_bytes(rel):
    """Taking apart one of the real shipped files into its metadata header and main content,
    then joining the two pieces back together, must reproduce the file exactly as it was.
    Losing or adding even one byte here means the built output would silently diverge from
    the source file it came from."""
    raw = (REPO_ROOT / rel).read_text(encoding="utf-8")
    fm_block, body = split_document(raw)
    assert (fm_block or "") + body == raw


@pytest.mark.parametrize("rel", PLUGIN_MD)
def test_rewriting_a_files_metadata_header_reproduces_it_exactly(rel):
    """Reading a real shipped file's metadata header and then writing it back out must produce
    the exact same bytes as the original -- not just equivalent-looking content. Any drift here
    would corrupt a file's metadata in the built output even though splitting it apart stayed
    lossless."""
    raw = (REPO_ROOT / rel).read_text(encoding="utf-8")
    fm_block, _ = split_document(raw)
    if fm_block is None:
        pytest.skip("no frontmatter")
    meta, _ = parse_frontmatter(fm_block)
    # render_frontmatter yields the fenced block without a trailing newline; the block carries one.
    assert render_frontmatter(meta) + "\n" == fm_block
