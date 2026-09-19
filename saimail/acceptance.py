"""Profile identity is not profile acceptance.

A digest proves *these exact semantics correspond to this exact identity*. It
proves nothing about whether this receiver agrees to read anything under them.
Those are different questions and conflating them is how external content ends
up defining its own meaning.

```
PROFILE_IDENTITY   = deterministic identity of exact profile semantics
PROFILE_ACCEPTANCE = receiver-owned authorization to interpret wire under them
```

The registry here answers the second question and only the second. It is owned
by the receiver, populated from profiles the receiver loaded itself, and it
never learns a profile from the wire. A container that names an unknown profile
is refused; there is no path by which an arriving message supplies the
dictionary that gives its own tokens meaning.

``receive()`` is the only public route from raw wire to decoded views, and the
registry is the only place acceptance is minted: ``Batch.parse`` itself takes
the receiver's acceptance capability, never a bare Profile object, so no public
route binds external wire without a receiver decision (T-39/CORE-001).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Tuple

from sailang.errors import SailangError
from sailang.frame import (
    AcceptedProfile,
    Batch,
    Profile,
    TriageView,
    _mint_accepted,
    decode,
)

ACCEPTED = "ACCEPTED"
UNKNOWN = "UNKNOWN"

_HEADER_RE = re.compile(r"^(?:SAIB3|SAIB4)\|P:(sha256:[0-9a-f]{64})\|N:(\d+)\|D:(\d+)$")


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


@dataclass
class ProfileRegistry:
    """Profiles this receiver has decided it will interpret wire under.

    Two states only. ``REJECTED``/``REVOKED`` are deliberately absent: nothing
    in current behaviour distinguishes them from ``UNKNOWN``, and a state that
    changes no decision is a state that will eventually be wrong.
    """

    _accepted: Dict[str, AcceptedProfile]

    def __init__(self) -> None:
        self._accepted = {}

    @classmethod
    def with_profiles(cls, *profiles: Profile) -> "ProfileRegistry":
        registry = cls()
        for profile in profiles:
            registry.accept(profile)
        return registry

    def accept(self, profile: Profile) -> None:
        """The receiver decides. A Profile object must already be in hand.

        Acceptance mints the capability ``Batch.parse`` requires: the registry
        is the only place raw-wire binding is authorized.
        """
        if not isinstance(profile, Profile):
            _reject("NOT_A_PROFILE",
                    "acceptance takes a Profile the receiver loaded, never a description of one")
        self._accepted[profile.id] = _mint_accepted(profile)

    def status(self, profile_id: str) -> str:
        return ACCEPTED if profile_id in self._accepted else UNKNOWN

    def resolve(self, profile_id: str) -> AcceptedProfile:
        if profile_id not in self._accepted:
            _reject(
                "PROFILE_NOT_ACCEPTED",
                f"{profile_id} is not accepted by this receiver; arriving content does not get "
                "to supply the dictionary that gives its own tokens meaning",
            )
        return self._accepted[profile_id]

    @property
    def accepted_ids(self) -> Tuple[str, ...]:
        return tuple(sorted(self._accepted))


def declared_profile_id(container: str) -> str:
    """Read the profile a container CLAIMS, without believing anything about it."""
    if not isinstance(container, str) or not container.strip():
        _reject("BAD_BATCH", "empty container")
    header = container.replace("\r\n", "\n").split("\n", 1)[0]
    match = _HEADER_RE.match(header)
    if not match:
        _reject("BAD_BATCH", f"container header is not a SAIB3 or SAIB4 header: {header[:60]!r}")
    return match.group(1)


def receive(container: str, registry: ProfileRegistry) -> Tuple[TriageView, ...]:
    """Raw wire in, typed non-authoritative views out. The only public route.

    Order matters: the container states an identity, the RECEIVER decides
    whether that identity is acceptable, and only then is anything parsed under
    it. A caller cannot assert a profile into existence.
    """
    if not isinstance(registry, ProfileRegistry):
        _reject("REGISTRY_REQUIRED", "receiving external wire needs the receiver's own registry")
    accepted = registry.resolve(declared_profile_id(container))
    return tuple(decode(frame) for frame in Batch.parse(container, accepted).frames)
