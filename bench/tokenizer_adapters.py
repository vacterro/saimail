"""Tokenizer adapters for the T-9 benchmark.

One adapter per encoding family. A count from one tokenizer is evidence about
that tokenizer and nothing else — adding a family means adding an adapter here,
not editing the measurement code.

No model weights are downloaded for this benchmark; ``tiktoken`` BPE tables are
small data files, not models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List


@dataclass(frozen=True)
class Adapter:
    name: str
    family: str
    count: Callable[[str], int]


def available() -> List[Adapter]:
    """Return every adapter this environment can actually run."""
    adapters: List[Adapter] = []
    try:
        import tiktoken
    except ImportError:
        return adapters

    for name, family in (
        ("cl100k_base", "openai-gpt35-gpt4"),
        ("o200k_base", "openai-gpt4o"),
        ("p50k_base", "openai-codex-davinci"),
        ("gpt2", "gpt2-legacy"),
    ):
        try:
            encoding = tiktoken.get_encoding(name)
        except Exception:  # an encoding this install cannot load is simply absent
            continue
        adapters.append(
            Adapter(name=name, family=family, count=lambda text, e=encoding: len(e.encode(text)))
        )
    return adapters
