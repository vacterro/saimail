"""Probe plugin: keep full collection, run only the canonical prefix.

Cuts execution after the last item of tests/test_quarantine.py while leaving
collection/import state identical to the full canonical run.
"""
CUT = "tests/test_quarantine.py::"


def pytest_collection_modifyitems(config, items):
    last = max(i for i, it in enumerate(items) if it.nodeid.startswith(CUT))
    deselected = items[last + 1:]
    if deselected:
        del items[last + 1:]
        config.hook.pytest_deselected(items=deselected)
