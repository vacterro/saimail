"""Compatibility entry for the checkout-only operator replay tool.

Host integration effects belong to tools/agent_cycle_replay.py. This module
keeps the previously recorded command usable without owning those effects.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def main():
    # The optional checkout tool is loaded only when this entry is invoked.
    from tools.agent_cycle_replay import main as replay_main

    return replay_main()

if __name__ == "__main__":
    raise SystemExit(main())
