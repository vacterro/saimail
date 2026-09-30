"""Operator-side project layout. Protocol functions receive explicit paths only."""

from pathlib import Path

from sailang import SailangError


def project_paths(project_root):
    root = Path(project_root).resolve()
    memory = root / ".saipen"
    if not (memory / "STATE.md").is_file():
        raise SailangError("SAIPEN_PROJECT_MISSING", "choose a project containing .saipen/STATE.md")
    return {"root": root, "memory": memory, "state": memory / "STATE.md",
            "identity": memory / "IDENTITY.md", "board": memory / "BOARD.md",
            "logs": [memory / "LOG.md", *sorted((memory / "logs").glob("LOG-*.md"))]}


__all__ = ["project_paths"]
