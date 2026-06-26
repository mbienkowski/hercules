"""Unit tests for the offline token counter."""

from hercules.methodology.token_counter import count_tokens


def test_token_count_is_correct_for_known_input():
    """cl100k_base must tokenise the test string as exactly 8 tokens — pins the encoder identity."""
    # Given / When / Then
    assert count_tokens("hello world, this is a token test") == 8


def test_longer_text_produces_more_tokens_than_shorter():
    """Token count must scale with content — a constant-returning stub fails this."""
    # Given / When / Then
    assert count_tokens("hello " * 20) > count_tokens("hello")


def test_empty_string_returns_zero_tokens():
    """An empty string has no tokens."""
    # Given / When / Then
    assert count_tokens("") == 0
