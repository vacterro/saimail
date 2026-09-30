"""Repository shim for the supported local entrypoint.

The implementation lives in the installable ``saimail_local`` module so the same
command works from a built package. This file only adds the checkout root to
``sys.path`` and delegates, keeping one runner rather than a second overlapping
one.

    python tools/fg05_local_scenario.py            # FG-05 demo
    python tools/fg05_local_scenario.py --utility  # FG-06 benchmark
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from saimail_local import main

if __name__ == "__main__":
    sys.exit(main())
