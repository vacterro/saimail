"""SAILANG error type.

One exception with a stable machine code. Callers branch on ``code``; the
``detail`` is for humans and tests, never for control flow.
"""

from __future__ import annotations


class SailangError(Exception):
    """A SAILANG parse or validation failure.

    ``code`` is a stable, closed-set token. ``detail`` explains it.
    """

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)
