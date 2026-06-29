"""Offline token counting via tiktoken cl100k_base."""

import tiktoken

# Module-level singleton — one network fetch on first import, offline thereafter.
_ENCODER = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count cl100k_base tokens without a network call.

    Deterministic and offline after the first import; suitable for threshold gates.
    """
    return len(_ENCODER.encode(text))
