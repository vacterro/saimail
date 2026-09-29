"""SRC-084: a letter to a person is rare on purpose, and `send --help` says so."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _send_help() -> str:
    spec = importlib.util.spec_from_file_location("saimail_local_for_help", ROOT / "saimail_local.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    parser = module._build_parser()
    sub = next(action for action in parser._actions if getattr(action, "choices", None) and "send" in action.choices)
    return " ".join(sub.choices["send"].format_help().split())


def test_send_help_states_the_etiquette() -> None:
    text = _send_help()
    assert "RARE on purpose" in text
    assert "probably not reading the chat" in text
    assert "finished ticket" in text
    assert "at most one per decision" in text


def test_readme_names_the_rule_and_both_conditions() -> None:
    readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
    assert "## When a letter is worth writing" in readme
    assert "Write a letter only when both hold" in readme.replace("**", "")
    assert "the operator is probably not reading the chat" in readme
    assert "Never a letter for: a ticket or Work that finished" in readme
