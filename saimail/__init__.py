"""SAIMAIL — routing and attention over SAILANG records.

Currently one thing: a deterministic R1 interest filter that reads typed views
and nothing else.
"""

from .acceptance import ProfileRegistry, receive
from .selector import (DEFER, IGNORE, OPEN_R2, OPEN_R3, Decision, Interest, select,
                       select_all)

__all__ = ["select", "select_all", "Interest", "Decision", "IGNORE", "DEFER",
           "OPEN_R2", "OPEN_R3", "ProfileRegistry", "receive"]
