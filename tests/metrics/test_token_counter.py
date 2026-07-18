"""Unit tests for the offline token counter."""

from tests.metrics.token_counter import count_tokens


def test_a_known_sentence_always_counts_the_same_number_of_tokens():
    """Counting a fixed, known sentence must always report the same token total (8). This
    pins down the exact counting behavior so that a change to how text is measured doesn't
    silently shift billing or context-limit calculations for users."""
    # Given / When / Then
    assert count_tokens("hello world, this is a token test") == 8


def test_a_longer_passage_counts_as_more_tokens_than_a_shorter_one():
    """A passage of repeated text must be counted as having more tokens than a short snippet
    of the same words. This guards against a broken counter that reports the same number no
    matter how much text is given, which would make usage and limit tracking meaningless."""
    # Given / When / Then
    assert count_tokens("hello " * 20) > count_tokens("hello")


def test_an_empty_string_counts_as_zero_tokens():
    """Text with no content at all must be counted as zero tokens, since there is nothing
    there to measure."""
    # Given / When / Then
    assert count_tokens("") == 0
