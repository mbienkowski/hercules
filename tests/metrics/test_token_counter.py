"""Unit tests for the offline token counter."""

import tiktoken

from tests.metrics.token_counter import count_tokens


def test_the_count_always_matches_the_real_cl100k_base_tokenizer():
    """Counting a sentence must always agree with what the actual cl100k_base tokenizer
    produces for that same text -- not a number frozen at one point in time. Pinning an exact
    token count would make this test fail on a harmless tiktoken library upgrade even though
    counting still works correctly; comparing against the real tokenizer catches an actually
    broken counter (wrong encoding, off-by-one, wrong text passed) while staying correct
    across library versions, so billing and context-limit calculations for users stay accurate
    either way."""
    # Given / When / Then
    text = "hello world, this is a token test"
    assert count_tokens(text) == len(tiktoken.get_encoding("cl100k_base").encode(text))


def test_counting_the_same_text_twice_always_gives_the_same_result():
    """Counting the same text twice in a row must report the identical total both times. A
    counter that isn't deterministic would make repeated budget checks on the same content
    silently disagree, which would make usage and limit tracking unreliable."""
    # Given / When / Then
    text = "hello world, this is a token test"
    assert count_tokens(text) == count_tokens(text)


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
