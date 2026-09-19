"""Authorship over immutable receipts: additive, declared, never inferred.

    RECEIPT PRESERVES BYTES.
    AUTHORITY PRESERVES AUTHORSHIP.

A captured conversation is one artifact and several voices. A user stating
intent, an assistant proposing an architecture, a measurement, and a later
acceptance all arrive in the same bytes. Treating the whole artifact as one
source class is how an assistant's brainstorm quietly becomes a user's order.

This layer sits **beside** the receipts and never touches them. A receipt is
bytes; a segment map says which spans of those bytes carry which authorship;
a derived requirement cites the exact segment it came from.

Two rules that shape everything here:

* **Authorship is declared, not detected.** There is no classifier in this
  module and there must never be one. Guessing an author from writing style is
  exactly the narrative-authority leak the whole project exists to avoid.
* **Unexamined is not unattributed-but-probably-fine.** A span nobody has
  classified is ``AMBIGUOUS``, and ``AMBIGUOUS`` carries no authority at all.

And one compatibility rule, because the receipts predate this layer
(RECEIPT-KIND-SCOPE-01, D-017):

* **A receipt's intake ``source_kind`` is transport, never authorship.** It
  says how the bytes arrived and which intake class filed them. SRC-005 arrived
  as ``user_instruction`` and is wholly ``AMBIGUOUS``; both statements are true,
  about different questions. Segments are the only authorship authority, every
  segment map declares that scope in its own JSON, and no function here reads
  ``source_kind`` to produce a class.

And one proof rule (CAPTURE-PROOF-02), because a claim is not the bytes it
names: a capture this repository cannot resolve stays readable under its own
name, but it caps the rung it can support. External-asserted acceptance is
``USER_ACCEPTANCE_OBSERVED``, never plain ``USER_ACCEPTANCE``; a declared
intent with no observed form refuses rather than borrowing the captured name.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

from sailang.errors import SailangError

#: Closed set. A class outside it is refused rather than tolerated.
USER_INTENT = "USER_INTENT"
USER_ACCEPTANCE = "USER_ACCEPTANCE"
ASSISTANT_PROPOSAL = "ASSISTANT_PROPOSAL"
MEASURED_EVIDENCE = "MEASURED_EVIDENCE"
SYSTEM_OBSERVATION = "SYSTEM_OBSERVATION"
AMBIGUOUS = "AMBIGUOUS"

SOURCE_CLASSES = (USER_INTENT, USER_ACCEPTANCE, ASSISTANT_PROPOSAL,
                  MEASURED_EVIDENCE, SYSTEM_OBSERVATION, AMBIGUOUS)

#: Not a source class: the RESULT of adopting a proposal through an observed
#: act rather than a captured word. Weaker than USER_ACCEPTANCE on purpose, and
#: visible everywhere it is returned.
USER_ACCEPTANCE_OBSERVED = "USER_ACCEPTANCE_OBSERVED"

#: What each class may authorize. Intent is what may direct work; evidence is
#: what may support a claim; neither substitutes for the other.
_CARRIES_INTENT = frozenset({USER_INTENT, USER_ACCEPTANCE})
_CARRIES_EVIDENCE = frozenset({MEASURED_EVIDENCE, SYSTEM_OBSERVATION})

#: The authority ladder, in its actual form. Not "SRC-001 > spec": a single
#: receipt id is one link, and the top of the ladder is the lineage.
AUTHORITY_LADDER = (
    "AUTHORITATIVE RECEIPT LINEAGE > DERIVED SPEC > IMPLEMENTATION > TESTS"
)

#: RECEIPT-KIND-SCOPE-01. The only legal value of ``receipt_source_kind_scope``
#: in a segment map, and the scope the rule file in ``provenance/`` declares.
RECEIPT_KIND_SCOPE_RULE = "RECEIPT-KIND-SCOPE-01"
TRANSPORT_INTAKE_ONLY = "TRANSPORT_INTAKE_ONLY"
SEGMENT_PROVENANCE = "SEGMENT_PROVENANCE"
SCOPE_RULE_FILE = "RECEIPT_KIND_SCOPE.json"
#: The verdict a conflict row carries. A finding about a naive reading of a
#: receipt, never an error in the receipt, which is immutable and whose kind was
#: a correct transport label when it was written.
SOURCE_KIND_IS_NOT_AUTHORSHIP = "SOURCE_KIND_IS_NOT_AUTHORSHIP"
UNEXAMINED_NO_AUTHORITY = "UNEXAMINED_NO_AUTHORITY"
#: Intake kinds whose NAME reads like a user voice, and so invite the naive
#: reading. Used only to report that hazard, never to grant anything.
_USER_SOUNDING_KINDS = frozenset({"user_instruction", "user_audit"})

#: Closed set of capture channels a map may declare as the basis of its classes.
HOST_USER_TURN = "HOST_USER_TURN"
CAPTURE_CHANNELS = (HOST_USER_TURN,)

#: Named proof statuses of a capture claim (capture_status). A capture is never
#: self-authenticating metadata: authority minting through a capture consults
#: these statuses and fails closed (CAPTURE-PROOF-01, correction 002).
#: The carrier bytes were produced locally, resolved by identity, and the exact
#: span was re-hashed against the receipt digest.
VERIFIED_LOCAL_CAPTURE = "VERIFIED_LOCAL_CAPTURE"
#: The carrier is an external host record this repository cannot resolve or
#: re-read. Historical declarations keep their standing under this name, but a
#: status query never reports them as verified, and no NEW proof may rest on
#: one: an assertion is named as an assertion. Authority minting is capped by
#: it (CAPTURE-PROOF-02): external-asserted acceptance resolves to
#: ``USER_ACCEPTANCE_OBSERVED``, never plain ``USER_ACCEPTANCE``.
EXTERNAL_CAPTURE_ASSERTION = "EXTERNAL_CAPTURE_ASSERTION"
#: A capture that declares a locally verifiable carrier, but whose carrier
#: bytes were not supplied to the verifier. Named unresolved state: refused,
#: never silently treated as external.
CAPTURE_UNRESOLVED = "CAPTURE_UNRESOLVED"


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


@dataclass(frozen=True)
class Segment:
    """A byte span of one receipt body, with a declared authorship class."""

    receipt: str
    start: int
    end: int
    source_class: str
    note: str = ""

    def __post_init__(self) -> None:
        if self.source_class not in SOURCE_CLASSES:
            _reject("BAD_SOURCE_CLASS",
                    f"{self.source_class!r} is not one of {SOURCE_CLASSES}")
        if self.start < 0 or self.end <= self.start:
            _reject("BAD_SEGMENT", f"{self.receipt}[{self.start}:{self.end}] is not a span")

    @property
    def carries_intent(self) -> bool:
        return self.source_class in _CARRIES_INTENT

    @property
    def carries_evidence(self) -> bool:
        return self.source_class in _CARRIES_EVIDENCE


@dataclass(frozen=True)
class Capture:
    """How the bytes of a receipt were obtained, when that is itself the basis
    of a declared class. A marker outside the bytes that is not style: the host
    recorded this text as one turn of one channel.

    A capture that claims a LOCAL carrier must carry the whole verification
    triple -- the carrier's own digest and the exact byte span the receipt was
    extracted from -- so ``capture_status`` can mechanically confirm
    ``carrier[start:end]`` hashes to ``extracted_sha256``. A capture with no
    triple names an external host record and stays exactly an assertion
    (CAPTURE-PROOF-01): authority minting may keep the claim visible at the
    observed rung and never as captured bytes (CAPTURE-PROOF-02); if the named
    carrier turns out to be locally addressable anyway, the claim is refused
    rather than believed.
    """

    channel: str
    host_record: str
    extracted_sha256: str
    carrier_sha256: Optional[str] = None
    carrier_start: Optional[int] = None
    carrier_end: Optional[int] = None

    def __post_init__(self) -> None:
        if self.channel not in CAPTURE_CHANNELS:
            _reject("BAD_CAPTURE_CHANNEL",
                    f"{self.channel!r} is not one of {CAPTURE_CHANNELS}")
        if not self.host_record:
            _reject("BAD_CAPTURE", "a capture names the host record it was taken from")
        triple = (self.carrier_sha256, self.carrier_start, self.carrier_end)
        if any(field is None for field in triple) and any(field is not None for field in triple):
            _reject("BAD_CAPTURE",
                    "a local carrier claim carries carrier_sha256, carrier_start and "
                    "carrier_end together, or none of them")
        if self.carrier_start is not None and self.carrier_end is not None:
            if self.carrier_start < 0 or self.carrier_end <= self.carrier_start:
                _reject("BAD_CAPTURE",
                        f"carrier span [{self.carrier_start}:{self.carrier_end}] is not a span")

    @property
    def declares_local_carrier(self) -> bool:
        """True when the capture carries the local verification triple."""
        return self.carrier_sha256 is not None


@dataclass(frozen=True)
class SegmentMap:
    """Declared authorship over one receipt. The receipt itself is untouched."""

    receipt: str
    body_sha256: str
    body_length: int
    segments: Tuple[Segment, ...]
    #: RECEIPT-KIND-SCOPE-01, carried by every map so a consumer holding only
    #: the map still reads the rule. There is exactly one legal value.
    source_kind_scope: str = TRANSPORT_INTAKE_ONLY
    capture: Optional[Capture] = None

    def __post_init__(self) -> None:
        if self.source_kind_scope != TRANSPORT_INTAKE_ONLY:
            _reject("SOURCE_KIND_SCOPE_INVALID",
                    f"{self.receipt}: receipt source_kind is {TRANSPORT_INTAKE_ONLY}, "
                    f"never {self.source_kind_scope!r}")
        if self.capture is not None and self.capture.extracted_sha256 != self.body_sha256:
            _reject("CAPTURE_MISMATCH",
                    f"{self.receipt}: the capture extracted {self.capture.extracted_sha256[:12]}, "
                    f"the map describes {self.body_sha256[:12]}")
        if not self.segments:
            _reject("EMPTY_SEGMENT_MAP", f"{self.receipt} has no declared segments")
        cursor = 0
        for segment in self.segments:
            if segment.receipt != self.receipt:
                _reject("SEGMENT_RECEIPT_MISMATCH",
                        f"{segment.receipt} appears in the map for {self.receipt}")
            if segment.start != cursor:
                _reject("SEGMENT_GAP",
                        f"{self.receipt}: byte {cursor} is unclassified; unexamined text is "
                        "declared AMBIGUOUS, never skipped")
            cursor = segment.end
        if cursor != self.body_length:
            _reject("SEGMENT_COVERAGE",
                    f"{self.receipt}: coverage ends at {cursor}, body is {self.body_length} bytes")

    def verify_against(self, body: bytes) -> None:
        """The map is only meaningful for the exact bytes it was written for."""
        if len(body) != self.body_length:
            _reject("RECEIPT_CHANGED",
                    f"{self.receipt}: map describes {self.body_length} bytes, body has {len(body)}")
        digest = hashlib.sha256(body).hexdigest()
        if digest != self.body_sha256:
            _reject("RECEIPT_CHANGED",
                    f"{self.receipt}: map was written for {self.body_sha256[:12]}, "
                    f"body hashes to {digest[:12]}")

    def segment_at(self, index: int) -> Segment:
        if index < 0 or index >= len(self.segments):
            _reject("NO_SUCH_SEGMENT", f"{self.receipt} has no segment {index}")
        return self.segments[index]

    def classes(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for segment in self.segments:
            out[segment.source_class] = out.get(segment.source_class, 0) + segment.end - segment.start
        return out


@dataclass(frozen=True)
class Attribution:
    """What a derived requirement claims as its source."""

    requirement: str
    receipt: str
    segment_index: int
    accepted_by: Optional[Tuple[str, int]] = None   # (receipt, segment index)

    def resolve(self, maps: Dict[str, SegmentMap]) -> Segment:
        if self.receipt not in maps:
            _reject("NO_SEGMENT_MAP", f"{self.requirement} cites {self.receipt}, which has no map")
        return maps[self.receipt].segment_at(self.segment_index)


def capture_status(segment_map: "SegmentMap",
                   carriers: Optional[Dict[str, bytes]] = None) -> str:
    """Named proof status of a map's capture claim. Fails closed (CAPTURE-PROOF-01).

    ``carriers`` maps a host record id to its locally available bytes. The
    statuses and refusals:

    * triple declared, carrier bytes present, digest and span verified --
      ``VERIFIED_LOCAL_CAPTURE``;
    * triple declared, carrier bytes absent -- ``CAPTURE_UNRESOLVED`` (named
      unresolved state; never falls back to "external");
    * no triple, carrier id not locally addressable -- ``EXTERNAL_CAPTURE_ASSERTION``
      (historical standing, named as an assertion, verified by nobody; it caps
      the authority a capture can support, CAPTURE-PROOF-02);
    * no triple, but the named carrier IS locally addressable -- refused with
      ``CAPTURE_UNVERIFIABLE``: the bytes exist to check the claim against, and
      a claim this repository could verify but did not is exactly the
      self-asserted carrier correction 002 removed;
    * wrong carrier digest -- ``CARRIER_DIGEST_MISMATCH``; wrong span --
      ``CARRIER_SPAN_MISMATCH``.
    """
    capture = segment_map.capture
    if capture is None:
        _reject("NO_CAPTURE", f"{segment_map.receipt} declares no capture")
    carriers = carriers or {}
    locally_addressable = capture.host_record in carriers
    if capture.declares_local_carrier:
        if not locally_addressable:
            return CAPTURE_UNRESOLVED
        blob = carriers[capture.host_record]
        if hashlib.sha256(blob).hexdigest() != capture.carrier_sha256:
            _reject("CARRIER_DIGEST_MISMATCH",
                    f"{segment_map.receipt}: capture names carrier {capture.host_record} with "
                    f"digest {capture.carrier_sha256[:12]}, the bytes hash to "
                    f"{hashlib.sha256(blob).hexdigest()[:12]}")
        if capture.carrier_end > len(blob):
            _reject("CARRIER_SPAN_MISMATCH",
                    f"{segment_map.receipt}: carrier span [{capture.carrier_start}:"
                    f"{capture.carrier_end}] exceeds the {len(blob)} carrier bytes")
        span = blob[capture.carrier_start:capture.carrier_end]
        span_digest = hashlib.sha256(span).hexdigest()
        if span_digest != capture.extracted_sha256:
            _reject("CARRIER_SPAN_MISMATCH",
                    f"{segment_map.receipt}: carrier[{capture.carrier_start}:"
                    f"{capture.carrier_end}] hashes to {span_digest[:12]}, the capture "
                    f"extracted {capture.extracted_sha256[:12]}")
        return VERIFIED_LOCAL_CAPTURE
    if locally_addressable:
        _reject("CAPTURE_UNVERIFIABLE",
                f"{segment_map.receipt}: capture names local record {capture.host_record} as "
                "carrier but declares no carrier digest and span to verify against it; a "
                "locally addressable carrier is verified or refused, never believed")
    return EXTERNAL_CAPTURE_ASSERTION


def _capture_ceiling(segment_map: "SegmentMap",
                     carriers: Optional[Dict[str, bytes]]) -> Optional[str]:
    """The strongest rung this map's capture can mechanically support.

    ``None`` means no ceiling: the map declares no capture, or its local
    carrier verified. ``CAPTURE_UNRESOLVED`` refuses rather than minting;
    captured intent is minted from verified bytes, not from a claim. An
    ``EXTERNAL_CAPTURE_ASSERTION`` is returned to the caller as a ceiling --
    the claim stays visible at the observed rung, never as captured bytes
    (CAPTURE-PROOF-02).
    """
    if segment_map.capture is None:
        return None
    status = capture_status(segment_map, carriers)
    if status == CAPTURE_UNRESOLVED:
        _reject("CAPTURE_UNRESOLVED",
                f"{segment_map.receipt}: capture claims carrier "
                f"{segment_map.capture.host_record} as local proof, but its bytes were not "
                "supplied; captured intent is minted from verified bytes, not from a claim")
    return status if status == EXTERNAL_CAPTURE_ASSERTION else None


def _asserted_rung(segment_map: "SegmentMap", carriers: Optional[Dict[str, bytes]],
                   source_class: str) -> str:
    """The rung a declared intent class keeps under this map's capture proof.

    A verified local capture -- or no capture at all -- leaves the declared
    class alone. An external assertion that this repository cannot resolve
    caps acceptance at ``USER_ACCEPTANCE_OBSERVED`` (the operator act stays
    visible as observed/asserted) and refuses a class with no observed form:
    an authorship that can only be asserted is never returned under the
    captured name (CAPTURE-PROOF-02, UNVERIFIED ASSERTION != CAPTURED USER ACT).
    """
    if _capture_ceiling(segment_map, carriers) != EXTERNAL_CAPTURE_ASSERTION:
        return source_class
    if source_class == USER_ACCEPTANCE:
        return USER_ACCEPTANCE_OBSERVED
    _reject("EXTERNAL_CAPTURE_NOT_PROOF",
            f"{segment_map.receipt}: capture names external host record "
            f"{segment_map.capture.host_record!r} that this repository cannot resolve; an "
            f"assertion is not proof of captured bytes and cannot mint {source_class}")


def intent_authority(attribution: Attribution, maps: Dict[str, SegmentMap],
                     carriers: Optional[Dict[str, bytes]] = None) -> str:
    """Does this requirement carry authority to direct work, and on what basis?

    Refuses rather than guesses. An assistant proposal becomes actionable only
    through an explicitly cited acceptance segment; nothing about the proposal
    itself can supply that.
    """
    segment = attribution.resolve(maps)
    if segment.carries_intent:
        return _asserted_rung(maps[attribution.receipt], carriers, segment.source_class)
    if segment.carries_evidence:
        _reject("EVIDENCE_IS_NOT_INTENT",
                f"{attribution.requirement} cites {segment.source_class}; measurement supports a "
                "claim, it does not ask for work")
    # ASSISTANT_PROPOSAL or AMBIGUOUS. Neither carries authority on its own, and
    # both can be adopted: what authorizes work is the acceptance, not where the
    # idea came from. The origin class stays visible either way.
    if attribution.accepted_by is None:
        if segment.source_class == AMBIGUOUS:
            _reject("AMBIGUOUS_AUTHORSHIP",
                    f"{attribution.requirement} cites a span whose author is undetermined and "
                    "no acceptance; ambiguous authorship stays ambiguous")
        _reject("ADOPTION_WITHOUT_ACCEPTANCE",
                f"{attribution.requirement} cites an assistant proposal with no cited acceptance; "
                "a proposal is not an instruction")
    receipt, index = attribution.accepted_by
    if receipt not in maps:
        _reject("NO_SEGMENT_MAP", f"{attribution.requirement} cites acceptance in {receipt}, "
                                  "which has no map")
    acceptance = maps[receipt].segment_at(index)
    if acceptance.source_class == USER_ACCEPTANCE:
        return _asserted_rung(maps[receipt], carriers, USER_ACCEPTANCE)
    if acceptance.source_class == SYSTEM_OBSERVATION:
        # An agent's note that a person said something is evidence ABOUT an act,
        # never the act. Adoption still happens, and it is labelled differently
        # wherever it appears, so nobody later mistakes it for a captured word.
        return USER_ACCEPTANCE_OBSERVED
    _reject("NOT_AN_ACCEPTANCE",
            f"{attribution.requirement} cites {acceptance.source_class} as acceptance; only "
            f"{USER_ACCEPTANCE} or an observed act adopts a proposal")


def receipt_intent_authority(receipt: str, maps: Dict[str, SegmentMap],
                             meta: Optional[dict] = None,
                             carriers: Optional[Dict[str, bytes]] = None) -> str:
    """May this WHOLE receipt direct work, and as what? (RECEIPT-KIND-SCOPE-01)

    ``meta`` is the intake metadata a consumer may be holding. Its
    ``source_kind`` is transport/intake classification: it supplies no class,
    upgrades no class and never stands in for a missing map. Only its digest is
    read, to prove the metadata and the map describe the same bytes.

    A receipt carries intent as a whole only when every declared segment does.
    Anything else is answered at segment level through ``intent_authority``,
    where a proposal can be adopted by a cited acceptance and the origin stays
    visible. An unresolvable external capture assertion caps the answer
    (CAPTURE-PROOF-02): acceptance resolves to ``USER_ACCEPTANCE_OBSERVED``,
    never plain ``USER_ACCEPTANCE``.
    """
    if receipt not in maps:
        _reject("NO_SEGMENT_MAP",
                f"{receipt} has no segment map: its authorship is unexamined and carries no "
                "authority, whatever its intake kind says")
    segment_map = maps[receipt]
    if meta is not None:
        if meta.get("receipt_id", receipt) != receipt:
            _reject("SEGMENT_RECEIPT_MISMATCH",
                    f"metadata for {meta.get('receipt_id')!r} offered for {receipt}")
        if meta.get("source_sha256") != segment_map.body_sha256:
            _reject("RECEIPT_CHANGED",
                    f"{receipt}: metadata digest does not match the bytes the map describes")
    classes = {segment.source_class for segment in segment_map.segments}
    if AMBIGUOUS in classes:
        _reject("AMBIGUOUS_AUTHORSHIP",
                f"{receipt} contains spans whose author is undetermined; a receipt is not "
                "user intent because it arrived through a user-sounding intake")
    if classes - _CARRIES_INTENT:
        _reject("MIXED_AUTHORSHIP",
                f"{receipt} mixes {sorted(classes)}; cite the exact segment instead")
    if USER_ACCEPTANCE in classes:
        return _asserted_rung(segment_map, carriers, USER_ACCEPTANCE)
    return _asserted_rung(segment_map, carriers, USER_INTENT)


def source_kind_conflicts(maps: Dict[str, SegmentMap],
                          metas: Dict[str, dict]) -> Tuple[dict, ...]:
    """Receipts whose intake kind would mislead a consumer that skipped segments.

    One machine-readable row per hazard. The rows are the detectable form of
    RECEIPT-KIND-SCOPE-01; nothing here grants or refuses authority, and the
    receipts themselves are never touched.
    """
    rows = []
    for receipt in sorted(metas):
        kind = metas[receipt].get("source_kind")
        if kind not in _USER_SOUNDING_KINDS:
            continue
        if receipt not in maps:
            rows.append({"receipt": receipt, "source_kind": kind, "segment_classes": None,
                         "rule": RECEIPT_KIND_SCOPE_RULE, "verdict": UNEXAMINED_NO_AUTHORITY})
            continue
        classes = maps[receipt].classes()
        if set(classes) - _CARRIES_INTENT:
            rows.append({"receipt": receipt, "source_kind": kind, "segment_classes": classes,
                         "rule": RECEIPT_KIND_SCOPE_RULE,
                         "verdict": SOURCE_KIND_IS_NOT_AUTHORSHIP})
    return tuple(rows)


def load_map(path: pathlib.Path) -> SegmentMap:
    data = json.loads(path.read_text(encoding="utf-8"))
    receipt = data["receipt"]
    if "receipt_source_kind_scope" not in data:
        _reject("SOURCE_KIND_SCOPE_UNDECLARED",
                f"{path.name} does not declare receipt_source_kind_scope; a map that is silent "
                "about the scope of source_kind lets a consumer read it as authorship")
    capture = data.get("capture")
    return SegmentMap(
        receipt=receipt,
        body_sha256=data["body_sha256"],
        body_length=data["body_length"],
        segments=tuple(
            Segment(receipt=receipt, start=s["start"], end=s["end"],
                    source_class=s["source_class"], note=s.get("note", ""))
            for s in data["segments"]
        ),
        source_kind_scope=data["receipt_source_kind_scope"],
        capture=Capture(channel=capture["channel"], host_record=capture["host_record"],
                        extracted_sha256=capture["extracted_sha256"],
                        carrier_sha256=capture.get("carrier_sha256"),
                        carrier_start=capture.get("carrier_start"),
                        carrier_end=capture.get("carrier_end")) if capture else None,
    )


#: Files in the provenance directory that are not segment maps.
_NOT_A_MAP = frozenset({"ATTRIBUTIONS.json", SCOPE_RULE_FILE})


def load_scope_rule(directory: pathlib.Path) -> dict:
    """The rule file is part of the map set: no rule, no maps."""
    path = directory / SCOPE_RULE_FILE
    if not path.is_file():
        _reject("SOURCE_KIND_SCOPE_UNDECLARED", f"{SCOPE_RULE_FILE} is missing from {directory}")
    rule = json.loads(path.read_text(encoding="utf-8"))
    expected = {"rule": RECEIPT_KIND_SCOPE_RULE, "field": "source_kind",
                "scope": TRANSPORT_INTAKE_ONLY, "authorship_authority": SEGMENT_PROVENANCE}
    for key, value in expected.items():
        if rule.get(key) != value:
            _reject("SOURCE_KIND_SCOPE_INVALID",
                    f"{SCOPE_RULE_FILE}: {key} must be {value!r}, got {rule.get(key)!r}")
    return rule


def load_maps(directory: pathlib.Path) -> Dict[str, SegmentMap]:
    """Load every segment map, fail closed on any ambiguity about one receipt.

    One receipt has one declared authorship (T-39/CORE-003). A second file
    declaring an already-seen receipt is a conflict, never an ordering: it is
    refused with ``DUPLICATE_SEGMENT_MAP`` regardless of lexical order. A map
    file whose stem is not the receipt it declares is refused with
    ``MAP_NAME_MISMATCH``, so an alias filename cannot shadow another receipt's
    canonical map. Conflicts are decided before any name binding, so the
    failure does not depend on which file sorted first.
    """
    load_scope_rule(directory)
    paths = [p for p in sorted(directory.glob("*.json")) if p.name not in _NOT_A_MAP]
    loaded = [(path, load_map(path)) for path in paths]
    declared: Dict[str, pathlib.Path] = {}
    for path, segment_map in loaded:
        if segment_map.receipt in declared:
            _reject(
                "DUPLICATE_SEGMENT_MAP",
                f"{path.name} declares {segment_map.receipt}, already declared by "
                f"{declared[segment_map.receipt].name}; a conflict is a conflict, "
                "not a lexical order",
            )
        declared[segment_map.receipt] = path
    maps: Dict[str, SegmentMap] = {}
    for path, segment_map in loaded:
        if path.stem != segment_map.receipt:
            _reject(
                "MAP_NAME_MISMATCH",
                f"{path.name} holds the map for {segment_map.receipt}; a provenance map is "
                "named after the receipt it describes",
            )
        maps[segment_map.receipt] = segment_map
    return maps


def load_attributions(path: pathlib.Path) -> Tuple[Attribution, ...]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        Attribution(
            requirement=row["requirement"],
            receipt=row["receipt"],
            segment_index=row["segment_index"],
            accepted_by=tuple(row["accepted_by"]) if row.get("accepted_by") else None,
        )
        for row in data["attributions"]
    )


def iter_classes(maps: Iterable[SegmentMap]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for segment_map in maps:
        for name, count in segment_map.classes().items():
            out[name] = out.get(name, 0) + count
    return out
