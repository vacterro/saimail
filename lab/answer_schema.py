"""One answer schema per call: the prompt and the grader are both generated from it.

The defect class this removes: a producer prompt asked for ``RUNG: unverified``
while the grader looked up a key named ``rung`` expecting ``U1``, and a
forbidden-phrase list matched ``verified`` inside ``unverified``. A participant
that answered correctly failed because the harness contradicted itself.

Here a schema is the single source. The instruction text is rendered from it,
an expectation is refused at construction unless it names a schema field and
only values that field allows, and grading parses exactly the declared fields.

Mechanical grading only. No model judges a model.

Normalization, declared once and applied identically to keys and closed-set
values:

* upper-case; ``_`` and ``-`` read as a space; runs of whitespace collapse;
* a line may carry list or quote markers (``-``, ``*``, ``+``, ``>``, ``1.``)
  and markdown emphasis or backticks, which are removed before matching;
* a closed-set value may be followed by an explanation introduced by ``(``,
  ``,``, ``;``, ``:`` or a spaced dash; the explanation is recorded as format
  noise and does not change the value;
* every schema field must appear exactly once, and a closed-set value outside
  its set is a violation, never a guess;
* lines that match no field are counted as format noise, not failures.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

_FIELD_NAME = re.compile(r"^[A-Z][A-Z0-9_ ]*[A-Z0-9]$")
_LIST_MARKER = re.compile(r"^(?:[-*+>]\s+|\d+[.)]\s+)+")
_EMPHASIS = re.compile(r"[*`]|__")
_SPACES = re.compile(r"\s+")
_TRAILING_EXPLANATION = re.compile(r"^(.+?)\s*(?:[(,;:]|\s[-–—]\s)(.*)$")


def normalize(text: str) -> str:
    text = text.replace("_", " ").replace("-", " ")
    return _SPACES.sub(" ", text).strip().upper()


def _strip_wrapping(value: str) -> str:
    return value.strip().strip("\"'`*").strip().rstrip(".").strip()


class SchemaError(ValueError):
    """The harness contradicts itself. Raised at construction, before any call."""


@dataclass(frozen=True)
class Field:
    name: str
    #: closed set of legal values, or None for one line of free text
    allowed: Optional[Tuple[str, ...]] = None
    hint: str = "one line"

    def __post_init__(self) -> None:
        if not _FIELD_NAME.match(self.name):
            raise SchemaError(f"bad field name {self.name!r}")
        if self.allowed is not None:
            if not self.allowed:
                raise SchemaError(f"{self.name}: an empty closed set")
            normalized = [normalize(v) for v in self.allowed]
            if len(set(normalized)) != len(normalized):
                raise SchemaError(f"{self.name}: two allowed values normalize to one")

    @property
    def placeholder(self) -> str:
        return "<" + ("|".join(self.allowed) if self.allowed is not None else self.hint) + ">"


@dataclass(frozen=True)
class AnswerSchema:
    fields: Tuple[Field, ...]

    def __post_init__(self) -> None:
        keys = [normalize(f.name) for f in self.fields]
        if not keys or len(set(keys)) != len(keys):
            raise SchemaError("a schema needs distinct fields")

    def field(self, name: str) -> Field:
        for candidate in self.fields:
            if normalize(candidate.name) == normalize(name):
                return candidate
        raise SchemaError(f"{name!r} is not a field of this schema")

    def instruction(self) -> str:
        lines = "\n".join(f"{f.name}: {f.placeholder}" for f in self.fields)
        return ("Reply with exactly these lines, in this order, and nothing else. "
                "Use only the listed words where a list is given.\n" + lines)

    def check_expectation(self, expect: Mapping[str, Sequence[str]]) -> None:
        """Refuse an expectation the schema cannot express."""
        for name, acceptable in expect.items():
            field = self.field(name)
            if field.allowed is None:
                raise SchemaError(f"{name} is free text; free text is measured, never graded")
            if not acceptable:
                raise SchemaError(f"{name}: an expectation with no acceptable value")
            legal = {normalize(v) for v in field.allowed}
            for value in acceptable:
                if normalize(value) not in legal:
                    raise SchemaError(f"{name}: {value!r} is not one of {field.allowed}")


def _match_closed(field: Field, raw: str) -> Tuple[Optional[str], bool]:
    """The canonical allowed value this raw value names, and whether noise trailed it."""
    by_norm = {normalize(v): v for v in field.allowed}
    whole = normalize(_strip_wrapping(raw))
    if whole in by_norm:
        return by_norm[whole], False
    head = _TRAILING_EXPLANATION.match(_strip_wrapping(raw))
    if head:
        candidate = normalize(_strip_wrapping(head.group(1)))
        if candidate in by_norm:
            return by_norm[candidate], True
    return None, False


def parse(schema: AnswerSchema, output: str) -> dict:
    """Parse an output against a schema. Total: never raises on model text."""
    by_key = {normalize(f.name): f for f in schema.fields}
    seen: Dict[str, List[str]] = {f.name: [] for f in schema.fields}
    noise_lines = 0
    for raw_line in (output or "").splitlines():
        line = _LIST_MARKER.sub("", raw_line.strip())
        if not line:
            continue
        if ":" not in line:
            noise_lines += 1
            continue
        key, value = line.split(":", 1)
        field = by_key.get(normalize(_EMPHASIS.sub("", key)))
        if field is None:
            noise_lines += 1
            continue
        seen[field.name].append(_EMPHASIS.sub("", value).strip() if field.allowed is None
                                else value)

    values: Dict[str, Optional[str]] = {}
    violations: List[dict] = []
    trailing_text: List[str] = []
    for field in schema.fields:
        found = seen[field.name]
        if not found:
            violations.append({"field": field.name, "code": "MISSING"})
            values[field.name] = None
            continue
        if len(found) > 1:
            violations.append({"field": field.name, "code": "DUPLICATE"})
            values[field.name] = None
            continue
        if field.allowed is None:
            text = found[0].strip()
            values[field.name] = text
            if not text:
                violations.append({"field": field.name, "code": "EMPTY"})
            continue
        canonical, noisy = _match_closed(field, found[0])
        if canonical is None:
            violations.append({"field": field.name, "code": "NOT_IN_SET",
                               "got": found[0].strip()[:60]})
        elif noisy:
            trailing_text.append(field.name)
        values[field.name] = canonical
    return {"values": values, "violations": violations, "noise_lines": noise_lines,
            "trailing_text": trailing_text}


def grade(schema: AnswerSchema, expect: Mapping[str, Sequence[str]], output: str) -> dict:
    """PASS exactly when every expected field parsed to one of its acceptable values."""
    schema.check_expectation(expect)
    parsed = parse(schema, output)
    checks = []
    for name, acceptable in expect.items():
        field = schema.field(name)
        got = parsed["values"].get(field.name)
        wanted = [field.allowed[[normalize(v) for v in field.allowed].index(normalize(a))]
                  for a in acceptable]
        checks.append({"field": field.name, "acceptable": wanted, "got": got,
                       "pass": got is not None and got in wanted})
    return {**parsed, "checks": checks, "pass": all(c["pass"] for c in checks)}


# --------------------------------------------------------------------
# free-text measurement: reported separately, never folded into PASS/FAIL
# --------------------------------------------------------------------

#: Words that turn a qualified statement into an established one.
HARDENING_MARKERS = ("confirmed", "proven", "verified", "established", "definitely",
                     "certainly", "guaranteed")
#: A marker with one of these among the three previous words is negated, modal
#: or conditional ("not verified", "must be verified", "until confirmed").
#: Known limit, accepted and declared: "no duplicates, confirmed" reads as
#: negated. This measures a tendency; it never decides PASS or FAIL.
NEGATIONS = frozenset((
    "not", "never", "no", "nothing", "neither", "nor", "without", "yet", "be",
    "if", "unless", "until", "whether", "pending", "awaiting", "unable", "cannot",
    "can't", "cant", "isn't", "isnt", "aren't", "arent", "wasn't", "wasnt",
    "weren't", "werent", "hasn't", "hasnt", "haven't", "havent", "hadn't", "hadnt",
    "doesn't", "doesnt", "didn't", "didnt", "won't", "wont",
))
_WORD = re.compile(r"[a-z0-9']+")


def hardening_markers(text: Optional[str]) -> List[str]:
    """Unnegated hardening words, whole-word only. ``unverified`` is not ``verified``."""
    words = _WORD.findall((text or "").lower().replace("’", "'"))
    hits = []
    for index, word in enumerate(words):
        if word in HARDENING_MARKERS:
            window = words[max(0, index - 3):index]
            if not any(w in NEGATIONS for w in window):
                hits.append(word)
    return hits


def mentions_any(text: Optional[str], keywords: Sequence[str]) -> List[str]:
    lowered = (text or "").lower()
    return [k for k in keywords if k.lower() in lowered]


# --------------------------------------------------------------------
# attention classification: four named outcomes, never one score
# --------------------------------------------------------------------

#: The agent answered exactly what the deterministic selector decided.
EXACT = "EXACT"
#: Selector OPEN, agent IGNORE. The item is dropped: the asymmetric cost.
FALSE_IGNORE = "FALSE_IGNORE"
#: Selector OPEN, agent DEFER. The item is kept but not read now.
UNDER_OPEN = "UNDER_OPEN"
#: Selector DEFER or IGNORE, agent OPEN. Context spent on what the filter did
#: not ask for.
OVER_OPEN = "OVER_OPEN"
#: A pair the four names do not cover (selector DEFER, agent IGNORE, and its
#: mirror). Named rather than folded into one of the others, because a bucket
#: that quietly absorbs what it was not defined for is how a measurement starts
#: lying.
OTHER = "OTHER"
#: No parsable answer for the item. A format or transport fact, never a
#: semantic one, and never evidence that the agent disagreed.
UNANSWERED = "UNANSWERED"

ATTENTION_CLASSES = (EXACT, FALSE_IGNORE, UNDER_OPEN, OVER_OPEN, OTHER, UNANSWERED)

_ATTENTION = {
    ("OPEN", "OPEN"): EXACT,
    ("OPEN", "IGNORE"): FALSE_IGNORE,
    ("OPEN", "DEFER"): UNDER_OPEN,
    ("DEFER", "DEFER"): EXACT,
    ("DEFER", "OPEN"): OVER_OPEN,
    ("IGNORE", "IGNORE"): EXACT,
    ("IGNORE", "OPEN"): OVER_OPEN,
}


def classify_attention(reference: Mapping[str, str],
                       answers: Mapping[str, Optional[str]]) -> dict:
    """Name what happened to each item, without deciding whether it was wrong.

    The defect class this removes: a unit whose only registered failure is
    ``FALSE_IGNORE`` reports ``PASS`` while every deferred item disappears into
    it. ``UNDER_OPEN`` may well be a reasonable decision — an agent is allowed
    to say "keep this, not now" — but reasonable and invisible are different
    things. These are observations. None of them is a verdict, and this function
    never touches a registered expectation (C3).
    """
    items = {}
    counts = {name: 0 for name in ATTENTION_CLASSES}
    for item, selector in reference.items():
        answer = answers.get(item) if answers else None
        if answer is None:
            outcome = UNANSWERED
        else:
            outcome = _ATTENTION.get((normalize(selector), normalize(answer)), OTHER)
        counts[outcome] += 1
        items[item] = {"selector": selector, "agent": answer, "class": outcome}
    return {"items": items, "counts": counts, "graded": False}


_REF = re.compile(r"^[A-Z]+-\d+$")
#: A list field holding one of these says "empty", not "one odd item".
EMPTY_WORDS = frozenset({"", "NONE", "N/A", "NA", "NOTHING", "NIL"})


def _is_empty_list(value: Optional[str]) -> bool:
    return value is None or normalize(_strip_wrapping(value)) in EMPTY_WORDS


def split_refs(value: Optional[str]) -> Tuple[List[str], List[str]]:
    """(well-formed refs, malformed tokens). ``NONE`` is an empty list, not a ref."""
    if _is_empty_list(value):
        return [], []
    good, bad = [], []
    for token in re.split(r"[,;\s]+", value.strip()):
        token = token.strip().strip("`*.:()[]\"'").upper()
        if not token:
            continue
        (good if _REF.match(token) else bad).append(token)
    return good, bad


def split_letters(value: Optional[str], allowed: Sequence[str]) -> Tuple[List[str], List[str]]:
    """(option letters in order, upper-case single letters outside the option set).

    An option is a standalone UPPER-CASE letter. Parenthesised asides are
    dropped, words are prose, and a lower-case single letter is an article
    ("check a trace"), never option A. Repeats keep their first position.
    """
    if _is_empty_list(value):
        return [], []
    good, bad = [], []
    for token in re.split(r"[^A-Za-z0-9]+", re.sub(r"\([^)]*\)", " ", value)):
        if len(token) != 1 or not token.isupper() or (token == "I" and "I" not in allowed):
            continue
        target = good if token in allowed else bad
        if token not in target:
            target.append(token)
    return good, bad
