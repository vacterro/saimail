"""SAILANG v0.2 triage frame: three types, bound profiles, semantic atoms.

```
FORBIDDEN:  TriageFrame -> Record
REQUIRED:   raw wire -> verified container -> bound TriageFrame -> TriageView
```

Three separate things, never conflated (spec/DECISIONS.md D-012):

* **atom**  — canonical semantic identity. This is what a ``TriageView``
  exposes, so no consumer has to know what ``QSTALE`` means.
* **wire**  — a profile-specific abbreviation. This is what travels.
* **render** — a human phrase. Carries no authority whatsoever.

A raw wire string carries no provenance, so it is **not decodable on its own**
(D-013). Profile identity is established by the container, and a
``TriageFrame`` can only exist already bound to the profile that container
verified.

DATA ONLY: nothing here executes, routes, fetches or mutates.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
from dataclasses import InitVar, dataclass
from types import MappingProxyType
from typing import ClassVar, Mapping, Optional, Sequence, Tuple

from .errors import SailangError
from .record import (
    EVIDENCE_ATTACHED,
    EVIDENCE_EXPLICITLY_ABSENT,
    EVIDENCE_NOT_APPLICABLE,
    KINDS,
    RUNGS,
    Record,
)

FRAME_VERSION = "4"
BATCH_MARKER = "SAIB4"
PROFILE_MARKER = "SAIP4"
SUPPORTED_FRAME_VERSIONS = ("3", "4")
#: Batch-local alias for a canonical identity. Never canonical authority.
ALIAS_RE = re.compile(r"^@[0-9]+$")
DEF_RE = re.compile(r"^DEF (@[0-9]+)=(sha256:[0-9a-f]{64})$")
_FLAGS_RE = re.compile(r"^(?:[RSC](?:@[0-9]+)?|X)+$")
SEPARATOR = "|"
#: "this frame cannot carry that fact; open the canonical record"
OPEN_RECORD = "?"
#: "the record has no such field at all"
ABSENT = "-"
#: a wire token this profile has no atom for: unknown, never guessed
UNKNOWN_ATOM = "UNKNOWN"
SLOT_COUNT = 6

#: Receiving bounds (PERF-002). External wire accepted under a legitimate
#: profile could previously force memory and CPU proportional to an arbitrary
#: declared size, so a receiver states what it will materialize before it
#: materializes it. The numbers are part of the receiving contract, chosen from
#: the declared one-mailbox scan budget (MAX_RUNS-scale batches, not the current
#: benchmark corpus): a batch larger than one mailbox scan is not a batch this
#: receiver promised to read. Fail closed, never truncate.
MAX_BATCH_BYTES = 8 * 1024 * 1024
MAX_BATCH_FRAMES = 100_000
MAX_BATCH_DEFINITIONS = 100_000
MAX_BATCH_LINE_BYTES = 64 * 1024

_DICTIONARY_DIR = pathlib.Path(__file__).resolve().parent / "dictionary"

_SEGMENT_RE = re.compile(r"^[A-Z0-9_]+$")
_CHAIN_RE = re.compile(r"^[A-Z0-9_]+(?:>[A-Z0-9_]+)*$")
_COMPARISON_RE = re.compile(r"^([A-Z0-9_]+)(>=|<=|!=|=)(\S+)$")
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

_FLAG_FIELDS = (("REFUTES", "R"), ("SUPPORTS", "S"), ("CON", "C"), ("FALSIFY", "X"))
_FLAG_CHARS = frozenset("RSCX")


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


# --------------------------------------------------------------------
# profile — version and dictionary identity, established once
# --------------------------------------------------------------------


@dataclass(frozen=True)
class Profile:
    """Frame version plus the exact dictionary a frame was produced under.

    Identity binds the dictionary's content digest, so a revision mints a new
    profile and a historical frame can never silently acquire new semantics.
    The identity is computed once at construction and reused (PERF-005): the
    defining fields are immutable for the lifetime of the instance, so
    recomputing the descriptor hash per decoded frame paid the same
    cryptographic work once per message for nothing.

    ``@dataclass(frozen=True)`` freezes the fields, not the dictionaries they
    hold (T-42/A2). The three semantic mappings are therefore copied at
    construction and exposed as ``MappingProxyType``: no caller-owned mutable
    dictionary stays reachable, and a mutation through any exposed mapping is
    refused instead of silently re-defining what an accepted profile means
    while ``profile.id`` keeps naming the old semantics. The descriptor hashes
    the dictionary digest, not the mapping objects, so the wire ABI and every
    existing profile id are unchanged.
    """

    frame_version: str
    dictionary_version: str
    dictionary_digest: str
    atom_to_wire: Mapping[str, str]
    wire_to_atom: Mapping[str, str]
    render: Mapping[str, str]

    def __post_init__(self) -> None:
        for name in ("atom_to_wire", "wire_to_atom", "render"):
            # a private copy behind a read-only view: mutation of the mapping
            # the constructor was handed changes nothing after this point
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))
        object.__setattr__(self, "_cached_id",
                           "sha256:" + hashlib.sha256(self.descriptor()).hexdigest())

    # -- construction -------------------------------------------------

    @staticmethod
    def _build(
        version: str,
        atoms: Mapping[str, Mapping[str, str]],
        digest: str,
        frame_version: str = FRAME_VERSION,
    ) -> "Profile":
        atom_to_wire: dict = {}
        wire_to_atom: dict = {}
        render: dict = {}
        for atom, entry in atoms.items():
            if not _SEGMENT_RE.match(atom):
                _reject("DICTIONARY_MALFORMED", f"{atom!r} is not a semantic atom")
            if not isinstance(entry, dict) or "wire" not in entry or "render" not in entry:
                _reject("DICTIONARY_MALFORMED", f"{atom}: needs a wire and a render")
            wire, text = entry["wire"], entry["render"]
            if not isinstance(wire, str) or not _SEGMENT_RE.match(wire):
                _reject("DICTIONARY_MALFORMED", f"{atom}: {wire!r} is not a wire token")
            if not isinstance(text, str) or not text.strip():
                _reject("DICTIONARY_MALFORMED", f"{atom}: render must be a non-empty phrase")
            if wire in wire_to_atom:
                _reject(
                    "DICTIONARY_AMBIGUOUS",
                    f"wire token {wire!r} maps to both {wire_to_atom[wire]!r} and {atom!r}; "
                    "the atom -> wire map must be injective or the wire is ambiguous",
                )
            atom_to_wire[atom] = wire
            wire_to_atom[wire] = atom
            render[atom] = text
        return Profile(
            frame_version=str(frame_version),
            dictionary_version=str(version),
            dictionary_digest=digest,
            atom_to_wire=atom_to_wire,
            wire_to_atom=wire_to_atom,
            render=render,
        )

    @classmethod
    def load(cls, dictionary_version: str = "1", frame_version: str = FRAME_VERSION) -> "Profile":
        if str(frame_version) not in SUPPORTED_FRAME_VERSIONS:
            _reject(
                "UNSUPPORTED_FRAME_VERSION",
                f"frame version must be in {SUPPORTED_FRAME_VERSIONS}, got {frame_version!r}",
            )
        path = _DICTIONARY_DIR / f"v{dictionary_version}.json"
        if not path.is_file():
            _reject("DICTIONARY_MISSING", f"no dictionary at {path}")
        raw = path.read_bytes()
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            _reject("DICTIONARY_MALFORMED", f"{path}: {exc}")
        if not isinstance(data, dict) or "version" not in data or "atoms" not in data:
            _reject("DICTIONARY_MALFORMED", f"{path}: missing version or atoms")
        if str(data["version"]) != str(dictionary_version):
            _reject(
                "DICTIONARY_VERSION_MISMATCH",
                f"{path} declares version {data['version']!r}, loaded as {dictionary_version!r}",
            )
        if not isinstance(data["atoms"], dict):
            _reject("DICTIONARY_MALFORMED", f"{path}: atoms must be a mapping")
        return cls._build(
            str(data["version"]),
            data["atoms"],
            "sha256:" + hashlib.sha256(raw).hexdigest(),
            frame_version=str(frame_version),
        )

    @classmethod
    def inline(
        cls,
        dictionary_version: str,
        atoms: Mapping[str, Mapping[str, str]],
        frame_version: str = FRAME_VERSION,
    ) -> "Profile":
        """A profile over an in-memory atom table, for tests and experiments."""
        if str(frame_version) not in SUPPORTED_FRAME_VERSIONS:
            _reject(
                "UNSUPPORTED_FRAME_VERSION",
                f"frame version must be in {SUPPORTED_FRAME_VERSIONS}, got {frame_version!r}",
            )
        canonical = json.dumps(
            {"version": dictionary_version, "atoms": {k: dict(v) for k, v in atoms.items()}},
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return cls._build(
            str(dictionary_version),
            atoms,
            "sha256:" + hashlib.sha256(canonical).hexdigest(),
            frame_version=str(frame_version),
        )

    # -- identity and mapping ----------------------------------------

    @property
    def batch_marker(self) -> str:
        return f"SAIB{self.frame_version}"

    @property
    def profile_marker(self) -> str:
        return f"SAIP{self.frame_version}"

    def descriptor(self) -> bytes:
        return (
            f"{self.profile_marker}\n"
            f"FRAME:{self.frame_version}\n"
            f"DICT:{self.dictionary_version}\n"
            f"DIGEST:{self.dictionary_digest}\n"
        ).encode("utf-8")

    @property
    def id(self) -> str:
        """``sha256:<hex>`` over :meth:`descriptor`, computed once per instance."""
        return self.__dict__["_cached_id"]

    def to_wire(self, atom: str) -> str:
        """Atom to wire token. An atom with no abbreviation travels verbatim."""
        return self.atom_to_wire.get(atom, atom)

    def to_atom(self, wire: str) -> Optional[str]:
        """Wire token to canonical atom, or None when this profile has no atom.

        None means UNKNOWN and must stay unknown. It never means "probably the
        closest thing in the table".
        """
        if wire in self.wire_to_atom:
            return self.wire_to_atom[wire]
        return None

    def is_non_canonical(self, wire: str) -> bool:
        """Did this token arrive as an atom that should have travelled abbreviated?

        One atom, one canonical encoding (D-016). A second accepted spelling is
        a second cache key, a second dedup key and a second thing to sign.
        """
        return wire in self.atom_to_wire and self.atom_to_wire[wire] != wire


# --------------------------------------------------------------------
# the three types
# --------------------------------------------------------------------


#: Only code that has established provenance may mint a frame. Passing this is
#: the deliberate, named act of asserting "I verified which profile produced
#: these bytes" (D-013).
_BINDING = object()


@dataclass(frozen=True)
class TriageFrame:
    """Non-authoritative, deterministic, machine-decodable, profile-bound.

    ``profile`` is a Profile object, not an id, because a frame may not exist
    without the binding its container proved. The constructor is guarded: a
    frame is minted by ``project`` (the producer knows the profile it encoded
    with) or by ``Batch.parse`` (which bound the wire under a profile the
    receiver accepted), or explicitly through the internal ``_bind_verified`` by
    code inside this package verified provenance. Plain ``TriageFrame(...)`` is
    refused, because a forged binding that looks like an ordinary constructor
    call is exactly the escape hatch this type exists to close.

    ``binding`` is a constructor-only ``InitVar`` (T-40): it is checked by
    ``__post_init__`` and never stored, so an ordinary instance carries no
    reusable token that ``dataclasses.replace`` or a copy could transplant onto
    different wire or another profile.
    """

    wire: str
    profile: Profile
    binding: InitVar[object] = None
    aliases: Tuple[Tuple[str, str], ...] = ()
    authoritative: ClassVar[bool] = False

    def __post_init__(self, binding: object) -> None:
        if binding is not _BINDING:
            _reject(
                "UNVERIFIED_BINDING",
                "a TriageFrame carries verified provenance and is minted by project(), "
                "Batch.parse() or _bind_verified(); constructing one directly would "
                "assert a profile nobody checked",
            )
        # the shared alias lookup (PERF-001) is attached by the container that
        # minted the frame, or built lazily at most once for a standalone frame
        object.__setattr__(self, "_alias_map", None)

    @property
    def alias_lookup(self) -> Mapping[str, str]:
        """The alias table as one shared immutable mapping, materialized at most once.

        A batch declares its aliases once; every bound frame used to rebuild
        the whole dict per decode, which made an alias-bearing mailbox decode
        quadratic (PERF-001). A batch-minted frame carries the container's
        single shared lookup instead; a standalone frame builds its own lazily,
        at most once. The cached object is a ``MappingProxyType`` so no reader
        can alter the semantics of an already-bound frame through it (T-42/C1).
        """
        cached = self.__dict__.get("_alias_map")
        if cached is None:
            global _ALIAS_MAP_BUILDS
            _ALIAS_MAP_BUILDS += 1
            cached = MappingProxyType(dict(self.aliases))
            object.__setattr__(self, "_alias_map", cached)
        return cached

    @property
    def profile_id(self) -> str:
        return self.profile.id

    def __str__(self) -> str:
        return self.wire


def _bind_verified(wire: str, profile: Profile, aliases: Tuple[Tuple[str, str], ...] = (),
                   alias_map: Optional[Mapping[str, str]] = None) -> TriageFrame:
    """Internal: mint a frame whose provenance this package has just verified.

    NOT public. An assertion-style public API would let any caller declare a
    profile nobody checked, which is the escape hatch the type exists to close.
    This is a correctness / type-state boundary, not a security boundary --
    Python privacy stops accidents, not adversaries.
    """
    if not isinstance(profile, Profile):
        _reject("PROFILE_REQUIRED", "binding a frame needs a Profile")
    if not isinstance(wire, str) or not wire:
        _reject("BAD_FRAME", "a frame needs wire text")
    frame = TriageFrame(wire=wire, profile=profile, binding=_BINDING, aliases=aliases)
    if alias_map is not None:
        # the container shares ONE immutable lookup across its frames (PERF-001,
        # T-42/C1): it is stored as handed in, never re-copied per frame, and the
        # containers in this package hand in a MappingProxyType
        object.__setattr__(frame, "_alias_map", alias_map)
    return frame


#: How many times an alias lookup has been materialized (PERF-001 regression
#: instrument): one N-frame batch with D definitions must build it O(1) times,
#: not N times.
_ALIAS_MAP_BUILDS = 0


@dataclass(frozen=True)
class TriageView:
    """Exactly what the frame carried, in canonical atoms. Nothing inferred."""

    profile_id: str
    kind: str
    subject: Optional[str]
    subject_open_record: bool
    status: Optional[str]
    evidence_state: str                 # EVIDENCE_ATTACHED | EVIDENCE_EXPLICITLY_ABSENT | EVIDENCE_NOT_APPLICABLE
    has_evidence: Optional[bool]
    claim_shape: Optional[str]          # "chain" | "comparison" | None
    claim_atoms: Tuple[str, ...]        # canonical atoms, in order
    claim_unknown_wires: Tuple[str, ...]  # wire tokens this profile has no atom for
    claim_value: Optional[str]          # right-hand side of a comparison
    claim_operator: Optional[str]
    claim_token: Optional[str]          # the raw wire, for diagnostics only
    claim_open_record: bool
    refutes: bool
    supports: bool
    conflict: bool
    falsifiable: bool
    #: ((mark, canonical identity), ...) for relations that named a target.
    relation_targets: Tuple[Tuple[str, str], ...] = ()
    #: aliases in the flags slot the container never declared: unknown, not guessed.
    unresolved_aliases: Tuple[str, ...] = ()
    authoritative: ClassVar[bool] = False

    @property
    def has_unknown_atoms(self) -> bool:
        return bool(self.claim_unknown_wires)

    @property
    def is_evidence_attached(self) -> bool:
        return self.evidence_state == EVIDENCE_ATTACHED

    @property
    def is_evidence_absent(self) -> bool:
        return self.evidence_state == EVIDENCE_EXPLICITLY_ABSENT

    @property
    def is_evidence_applicable(self) -> bool:
        return self.evidence_state != EVIDENCE_NOT_APPLICABLE


#: Only the receiver's own registry may mint acceptance. A Profile object says
#: what a container's bytes mean; it never says this receiver agreed to read
#: them (T-39/CORE-001, D-011).
_ACCEPTED = object()


@dataclass(frozen=True)
class AcceptedProfile:
    """A Profile the receiver accepted for interpreting external wire.

    The capability, not the Profile, is what ``Batch.parse`` takes: possession
    of a Profile object alone must never authorize binding raw wire. Minted only
    by the receiver's ``saimail.acceptance.ProfileRegistry`` through the
    internal ``_mint_accepted`` seam; ordinary construction refuses. The mint is
    a constructor-only ``InitVar`` (T-40) and is not retained, so one accepted
    capability cannot be copied, replaced or transplanted into acceptance of
    another Profile. This is a correctness / type-state boundary, not a
    security boundary: Python privacy stops accidents, not adversaries (D-015).
    """

    profile: Profile
    binding: InitVar[object] = None

    def __post_init__(self, binding: object) -> None:
        if binding is not _ACCEPTED:
            _reject(
                "UNVERIFIED_ACCEPTANCE",
                "an accepted profile is minted by the receiver's ProfileRegistry.accept(); "
                "constructing one directly would assert an acceptance nobody granted",
            )


def _mint_accepted(profile: Profile) -> AcceptedProfile:
    """Internal: mint receiver acceptance for one Profile.

    NOT public (same seam as ``_bind_verified``): the receiver's registry is the
    only code that calls this, and it calls it only when it decides to accept.
    """
    if not isinstance(profile, Profile):
        _reject("PROFILE_REQUIRED", "acceptance is minted for a Profile")
    return AcceptedProfile(profile=profile, binding=_ACCEPTED)


@dataclass(frozen=True)
class Batch:
    """The verified container. Profile identity and aliases are declared here, once."""

    profile: Profile
    frames: tuple
    aliases: tuple = ()

    def render(self) -> str:
        for frame in self.frames:
            if frame.profile.id != self.profile.id:
                _reject("PROFILE_MISMATCH",
                        "a batch cannot carry a frame produced under a different profile")
        header = (f"{self.profile.batch_marker}{SEPARATOR}P:{self.profile.id}"
                  f"{SEPARATOR}N:{len(self.frames)}{SEPARATOR}D:{len(self.aliases)}")
        defs = [f"DEF {alias}={cid}" for alias, cid in self.aliases]
        return "\n".join([header] + defs + [frame.wire for frame in self.frames]) + "\n"

    @staticmethod
    def parse(text: str, accepted: "AcceptedProfile") -> "Batch":
        """The ONLY route from raw wire to bound frames -- under receiver acceptance.

        Takes the acceptance capability, never a bare Profile: a Profile object
        proves identity, not that this receiver agreed to read anything under
        it (D-011, T-39/CORE-001). The capability is minted by the receiver's
        own registry, so raw external wire cannot select its own semantics.

        Receiving is bounded (PERF-002): container bytes, declared frame and
        definition counts and per-line length are refused before the body is
        split or any frame is materialized, so external wire cannot force
        memory proportional to a declaration the receiver never agreed to.
        """
        if not isinstance(accepted, AcceptedProfile):
            _reject(
                "ACCEPTED_PROFILE_REQUIRED",
                "raw wire is bound only under a profile the receiver accepted; pass the "
                "capability from ProfileRegistry.resolve(), never a Profile object",
            )
        profile = accepted.profile
        if not isinstance(text, str):
            _reject("BAD_BATCH", f"cannot parse {type(text).__name__}")
        if len(text) > MAX_BATCH_BYTES:
            _reject("BATCH_OVERSIZE",
                    f"container exceeds {MAX_BATCH_BYTES} characters; a receiver bounds "
                    "what it materializes before it parses it")
        # the header is read with a bounded first-line operation, and the
        # declared counts are checked before the body is split at all
        first_line, _, _ = text.partition("\n")
        header = first_line.split(SEPARATOR)
        expected_marker = profile.batch_marker
        if len(header) != 4 or header[0] != expected_marker:
            _reject("BAD_BATCH", f"line 1 must be {expected_marker}|P:<id>|N:<count>|D:<defs>")
        if (not header[1].startswith("P:") or not header[2].startswith("N:")
                or not header[3].startswith("D:")):
            _reject("BAD_BATCH", "container header must carry P:, N: and D:")
        declared = header[1][2:]
        if not _HASH_RE.match(declared):
            _reject("BAD_PROFILE_ID", f"profile id must be sha256:<64 hex>, got {declared!r}")
        if declared != profile.id:
            _reject(
                "PROFILE_MISMATCH",
                f"container was produced under profile {declared} but {profile.id} was supplied; "
                "a frame never silently acquires the semantics of another dictionary",
            )
        try:
            count = int(header[2][2:])
            def_count = int(header[3][2:])
        except ValueError:
            _reject("BAD_BATCH", f"N: and D: must be integers, got {header[2:]!r}")
        if count > MAX_BATCH_FRAMES:
            _reject("BATCH_TOO_MANY_FRAMES",
                    f"container declares {count} frames, over the receiving bound of "
                    f"{MAX_BATCH_FRAMES}; nothing was materialized")
        if def_count > MAX_BATCH_DEFINITIONS:
            _reject("BATCH_TOO_MANY_DEFINITIONS",
                    f"container declares {def_count} alias definitions, over the receiving "
                    f"bound of {MAX_BATCH_DEFINITIONS}; nothing was materialized")
        lines = text.replace("\r\n", "\n").split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        if not lines:
            _reject("BAD_BATCH", "empty container")
        if max(len(line) for line in lines) > MAX_BATCH_LINE_BYTES:
            _reject("BATCH_LINE_OVERSIZE",
                    f"a container line exceeds {MAX_BATCH_LINE_BYTES} characters")
        rest = lines[1:]
        if len(rest) != count + def_count:
            _reject("BAD_BATCH",
                    f"header declares {def_count} definitions and {count} frames, "
                    f"body carries {len(rest)} lines")
        aliases = []
        seen = set()
        for line in rest[:def_count]:
            match = DEF_RE.match(line)
            if not match:
                _reject("BAD_ALIAS_DEF", f"{line[:50]!r} is not DEF @n=sha256:<64 hex>")
            alias, cid = match.groups()
            if alias in seen:
                _reject("DUPLICATE_ALIAS", f"{alias} is defined twice")
            seen.add(alias)
            aliases.append((alias, cid))
        table = tuple(aliases)
        # ONE alias lookup per parsed batch, immutable, shared by identity by
        # every frame this container mints (PERF-001, T-42/C1): the receiver's
        # parse used to copy it again inside _bind_verified for each frame
        shared_map = MappingProxyType(dict(table))
        return Batch(profile=profile, aliases=table,
                     frames=tuple(_bind_verified(line, profile, table, shared_map)
                                  for line in rest[def_count:]))


# --------------------------------------------------------------------
# record -> frame
# --------------------------------------------------------------------


def _claim_wire(claim: str, profile: Profile) -> str:
    if _CHAIN_RE.match(claim):
        return ">".join(profile.to_wire(part) for part in claim.split(">"))
    comparison = _COMPARISON_RE.match(claim)
    if comparison:
        left, operator, right = comparison.groups()
        if SEPARATOR in right:
            return OPEN_RECORD
        return f"{profile.to_wire(left)}{operator}{right}"
    return OPEN_RECORD


def _safe_slot(value: str) -> str:
    return OPEN_RECORD if SEPARATOR in value else value


def project(record: Record, profile: Profile, alias_of=None) -> TriageFrame:
    """Render a record's triage frame. Pure: the record is untouched.

    ``alias_of`` maps a canonical identity to a batch-local alias. With it, a
    relation names its target (``R@3``); without it the relation is still
    reported but its target is not on the wire.
    """
    if not isinstance(record, Record):
        _reject("NOT_A_RECORD",
                f"project() takes a canonical Record, got {type(record).__name__}; "
                "a view or a frame is never promoted back into one")
    if not isinstance(profile, Profile):
        _reject("PROFILE_REQUIRED", "projection needs an explicit profile; there is no default")
    subject = record.get("SUBJ")
    status = record.get("STATUS")
    alias_of = alias_of or {}
    marks = []
    for field, mark in _FLAG_FIELDS:
        if field not in record:
            continue
        target = record.get(field)
        alias = alias_of.get(target) if field != "FALSIFY" else None
        marks.append(f"{mark}{alias}" if alias else mark)
    flags = "".join(marks)
    if profile.frame_version == "3":
        ev_slot = "EV+" if record.has_evidence else "EV0"
    else:
        if record.evidence_state == EVIDENCE_ATTACHED:
            ev_slot = "EV+"
        elif record.evidence_state == EVIDENCE_EXPLICITLY_ABSENT:
            ev_slot = "EV0"
        else:
            ev_slot = "EV-"
    slots = [
        record.kind,
        _safe_slot(subject) if subject else ABSENT,
        status if status else ABSENT,
        ev_slot,
        _claim_wire(record.claim, profile),
        flags if flags else ABSENT,
    ]
    return _bind_verified(SEPARATOR.join(slots), profile)


#: Fields whose value is a canonical identity a relation can point at.
_TARGET_FIELDS = ("REFUTES", "SUPPORTS", "CON")


def project_batch(records: Sequence[Record], profile: Profile, with_aliases: bool = True) -> Batch:
    """Render a container. Relation targets become batch-local aliases.

    The alias is transport only: it is declared once in the container and
    expands to the canonical identity. It never becomes the identity.
    """
    alias_of = {}
    if with_aliases:
        for record in records:
            for field in _TARGET_FIELDS:
                target = record.get(field)
                if target and target not in alias_of:
                    alias_of[target] = f"@{len(alias_of) + 1}"
    table = tuple((alias, cid) for cid, alias in alias_of.items())
    frames = tuple(project(r, profile, alias_of) for r in records)
    # same invariant as Batch.parse: one immutable lookup, shared by identity
    shared_map = MappingProxyType(dict(table))
    for frame in frames:
        object.__setattr__(frame, "_alias_map", shared_map)
    return Batch(profile=profile, aliases=table, frames=frames)


# --------------------------------------------------------------------
# frame -> view (never -> record)
# --------------------------------------------------------------------


def _decode_claim(token: str, profile: Profile) -> dict:
    if token == OPEN_RECORD:
        return {"claim_shape": None, "claim_atoms": (), "claim_unknown_wires": (),
                "claim_value": None, "claim_operator": None, "claim_token": None,
                "claim_open_record": True}
    comparison = _COMPARISON_RE.match(token)
    if comparison:
        left, operator, right = comparison.groups()
        if profile.is_non_canonical(left):
            _reject("NON_CANONICAL_ENCODING",
                    f"{left!r} is an atom that travels as {profile.atom_to_wire[left]!r} "
                    "under this profile; one atom has one canonical encoding (D-016)")
        atom = profile.to_atom(left)
        return {"claim_shape": "comparison",
                "claim_atoms": (atom,) if atom else (),
                "claim_unknown_wires": () if atom else (left,),
                "claim_value": right, "claim_operator": operator,
                "claim_token": token, "claim_open_record": False}
    if _CHAIN_RE.match(token):
        atoms, unknown = [], []
        for segment in token.split(">"):
            if profile.is_non_canonical(segment):
                _reject("NON_CANONICAL_ENCODING",
                        f"{segment!r} is an atom that travels as "
                        f"{profile.atom_to_wire[segment]!r} under this profile; one atom has one "
                        "canonical encoding (D-016)")
            atom = profile.to_atom(segment)
            if atom is None:
                unknown.append(segment)
            else:
                atoms.append(atom)
        return {"claim_shape": "chain", "claim_atoms": tuple(atoms),
                "claim_unknown_wires": tuple(unknown), "claim_value": None,
                "claim_operator": None, "claim_token": token, "claim_open_record": False}
    _reject("BAD_FRAME", f"claim slot {token!r} is neither a chain, a comparison nor {OPEN_RECORD!r}")


def _decode_flags(flags: str, aliases: Mapping[str, str]):
    """Split the flags slot into marks, resolved targets and unresolved aliases.

    An alias the container never declared stays UNRESOLVED. It is never treated
    as absent and never guessed at: a relation whose target cannot be named is
    still a relation, and a reader must be told so.
    """
    if flags == ABSENT:
        return "", (), ()
    marks, targets, unresolved = [], [], []
    index = 0
    while index < len(flags):
        mark = flags[index]
        marks.append(mark)
        index += 1
        if index < len(flags) and flags[index] == "@":
            end = index + 1
            while end < len(flags) and flags[end].isdigit():
                end += 1
            alias = flags[index:end]
            index = end
            if alias in aliases:
                targets.append((mark, aliases[alias]))
            else:
                unresolved.append(alias)
    return "".join(marks), tuple(targets), tuple(unresolved)


def decode(frame: TriageFrame) -> TriageView:
    """Decode a bound frame into a typed, non-authoritative view.

    Takes no profile argument on purpose: the frame already carries the profile
    its container verified. A raw string has no such binding and is refused.
    """
    if isinstance(frame, str):
        _reject(
            "UNBOUND_WIRE",
            "a raw frame string carries no profile identity and cannot be decoded; "
            "route it through the receiver's accepted route (receive() or "
            "Batch.parse with an accepted profile) first (D-013)",
        )
    if not isinstance(frame, TriageFrame):
        _reject("BAD_FRAME", f"cannot decode {type(frame).__name__}")

    slots = frame.wire.split(SEPARATOR)
    if len(slots) != SLOT_COUNT:
        _reject("BAD_FRAME", f"a frame has exactly {SLOT_COUNT} slots, got {len(slots)}")
    kind, subject, status, evidence, claim, flags = slots
    if kind not in KINDS:
        _reject("BAD_FRAME", f"unknown kind {kind!r}")
    if status not in RUNGS and status != ABSENT:
        _reject("BAD_FRAME", f"unknown status {status!r}")
    if frame.profile.frame_version == "3":
        if evidence not in ("EV0", "EV+"):
            _reject("BAD_FRAME", f"evidence slot on V3 must be EV0 or EV+, got {evidence!r}")
        ev_state = EVIDENCE_ATTACHED if evidence == "EV+" else EVIDENCE_EXPLICITLY_ABSENT
        has_ev = evidence == "EV+"
    else:
        if evidence not in ("EV0", "EV+", "EV-"):
            _reject("BAD_FRAME", f"evidence slot must be EV0, EV+ or EV-, got {evidence!r}")
        if evidence == "EV+":
            ev_state = EVIDENCE_ATTACHED
            has_ev = True
        elif evidence == "EV0":
            ev_state = EVIDENCE_EXPLICITLY_ABSENT
            has_ev = False
        else:
            ev_state = EVIDENCE_NOT_APPLICABLE
            has_ev = None
    if flags != ABSENT and not _FLAGS_RE.match(flags):
        _reject("BAD_FRAME", f"malformed flags slot {flags!r}")
    if not subject or not claim:
        _reject("BAD_FRAME", "empty slot")
    # PERF-001: the alias lookup is shared per batch and skipped entirely for
    # frames that carry no relation flags
    if flags == ABSENT:
        marks, targets, unresolved = "", (), ()
    else:
        marks, targets, unresolved = _decode_flags(flags, frame.alias_lookup)
    return TriageView(
        relation_targets=targets,
        unresolved_aliases=unresolved,
        profile_id=frame.profile.id,
        kind=kind,
        subject=None if subject in (ABSENT, OPEN_RECORD) else subject,
        subject_open_record=subject == OPEN_RECORD,
        status=None if status == ABSENT else status,
        evidence_state=ev_state,
        has_evidence=has_ev,
        refutes="R" in marks,
        supports="S" in marks,
        conflict="C" in marks,
        falsifiable="X" in marks,
        **_decode_claim(claim, frame.profile),
    )
