# Canonical verification commands

The repository-declared full test suite is `python -m pytest -q` from the
project root. `pyproject.toml` defines the `test` extra for that command, and
the GUI contract tests run as `python -m pytest -q tests/test_gui_surface.py`.

This checkout is based on source version `0.0.2a3`, while the separately frozen
candidate bundle remains immutable. Do not build or replace that candidate as
part of checkout-only product work.
