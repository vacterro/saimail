"""One registered LAB budget-only reachability experiment (T-74).

    BUDGET_ONLY_ARM: generator max_tokens 2048 -> 4096, everything else frozen.

This harness is the T-71 reachability experiment with exactly ONE experimental
variable changed: the generator's remote completion budget.  Reviewer stays
2048, probe stays 16, ``response_format`` stays absent, prompts and corpus are
byte-identical to T-71.  The local 4000-character parser-input projection is
replaced by the LAB-only ephemeral full-visible-output path
(``lab/ephemeral_output.py``), so a completion that is complete at the provider
reaches the unchanged strict parser intact.

    COMPLETE OR REFUSE -- never TRUNCATE AND PARSE.

Only metadata is durable: identities, hashes, byte lengths, routes, verdicts and
counts.  No prompt text, corpus content, generated prose, reviewer rationale or
provider error body is persisted.  The full ephemeral output exists only inside
one stage and is scrubbed in a ``finally`` block even on a parse failure.

    python lab/project_corpus_budget4096.py --dry-run
    python lab/project_corpus_budget4096.py --run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from lab import ally_generation_scenarios as sc
from lab import ephemeral_output as eph
from lab import parse_shape as shape
from lab import project_corpus_generation_pilot as pilot
from lab import project_corpus_reachability as reach
from lab import saifren_population as pop
from lab import saifren_run as live
from sailang.errors import SailangError
from saimail import ally_advice as aa
from saimail import ally_generation as ag
from saimail.credentials import CredentialError, CredentialNotProvisioned, resolve
from saimail.publish import PUBLISHED, publish_immutable

ROOT = pathlib.Path(__file__).resolve().parent.parent
REGISTRATION_PATH = ROOT / "lab/project_corpus_budget4096_registration.json"
REGISTRATION_SHA256 = "ac6a940220d65916355dc648f4c1dbc4cb24331254cb793cc1c2ec1a6c383190"
VERSION = "PROJECT-CORPUS-BUDGET4096-1"

ROUTES = {"A": "SAIFREN", "B": "goat/MiniMaxAI/MiniMax-M3"}
KNOWN_MODELS = frozenset({*ROUTES.values(), "deepseek/deepseek-v4-flash",
                          "MiniMaxAI/MiniMax-M3"})

TOKEN_BUDGETS = {"PROBE": live.PROBE_MAX_TOKENS, "GENERATOR": 4096, "REVIEWER": 2048}
LEGACY_OUTPUT_CHARS = live.MAX_OUTPUT_CHARS
RESPONSE_FORMAT_KIND = "NONE"
MAX_LIVE_CALLS = 6

ERRORS = reach.ERRORS
PARSE = reach.PARSE
STAGE_VALUES = reach.STAGE_VALUES
CODES = reach.CODES
LABEL_SCHEMA = reach.LABEL_SCHEMA

CALL_SCHEMA = {
    "call_id": ("regex", r"[0-9a-f]{12}"),
    "replicate": frozenset({0, 1, 2}), "role": frozenset({"A", "B"}),
    "function": frozenset({"PROBE", "GENERATOR", "REVIEWER"}),
    "requested_model": frozenset(ROUTES.values()), "reported_model": LABEL_SCHEMA,
    "provider": shape.TEXT_METADATA_SCHEMA,
    "provider_basis": frozenset({"RESPONSE_FIELD", "RESPONSE_HEADER", "NOT_EXPOSED", "OTHER"}),
    "request_max_tokens": frozenset(set(TOKEN_BUDGETS.values())),
    "response_format_kind": frozenset({RESPONSE_FORMAT_KIND}),
    "request_body_sha256": shape.nullable(shape.HASH),
    "request_body_bytes": shape.nullable(int),
    "sent": bool, "status": frozenset({"OK", "ERROR", "NOT_RUN"}),
    "error_class": shape.nullable(ERRORS), "error_body": shape.TEXT_METADATA_SCHEMA,
    "http_status": shape.nullable(int), "latency_s": shape.nullable(float),
    "finish_reason": shape.nullable(frozenset({"stop", "length", "content_filter",
                                               "tool_calls", "OTHER"})),
    "output_truncated": shape.nullable(bool), "inline_trace_removed": shape.nullable(bool),
    "prompt_sha256": shape.HASH, "visible_output": shape.TEXT_METADATA_SCHEMA,
    "full_output_sha256": shape.nullable(shape.HASH),
    "full_output_bytes": shape.nullable(int),
    "legacy_projection_would_truncate": shape.nullable(bool),
    "usage": {key: shape.nullable(int) for key in live._KEPT_USAGE},
    "local_estimated_input_tokens": int,
    "parse_shape": shape.nullable(shape.SHAPE_SCHEMA),
    "parser_status": PARSE, "parser_error_code": shape.nullable(CODES),
}

ARTIFACT_SCHEMA = {
    "version": frozenset({VERSION}), "registration_id": shape.IDENTITY,
    "implementation": {"observer_sha256": shape.HASH, "harness_sha256": shape.HASH,
                       "transport_sha256": shape.HASH},
    "started": ("regex", r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"), "dry_run": bool,
    "status": frozenset({"COMPLETED", "NO_GO_POPULATION", "CREDENTIAL_UNAVAILABLE",
                         "STOPPED"}),
    "input": {"registration_id": shape.IDENTITY, "build_id": shape.IDENTITY,
              "corpus_id": shape.IDENTITY, "artifact_count": int, "event_count": int},
    "routes": {key: frozenset({value}) for key, value in ROUTES.items()},
    "token_budgets": {"probe": frozenset({16}), "generator": frozenset({4096}),
                      "reviewer": frozenset({2048})},
    "response_format_kind": frozenset({RESPONSE_FORMAT_KIND}),
    "legacy_output_chars": frozenset({LEGACY_OUTPUT_CHARS}),
    "population_projection": frozenset({pilot.POPULATION_PROJECTION_VERSION}),
    "participant_count": int,
    "budget": {key: int for key in ("max_calls", "spent_total", "spent_probe",
        "spent_generation", "spent_review", "retries", "repair_calls", "network_calls")},
    "calls": ("list", CALL_SCHEMA, MAX_LIVE_CALLS),
    "replicates": ("list", reach.REPLICATE_SCHEMA, 2),
    "privacy": {key: frozenset({False}) for key in ("prompt_persisted", "output_persisted",
        "candidate_prose_persisted", "reviewer_rationale_persisted", "error_body_persisted",
        "full_output_persisted")},
    "side_effects": {key: frozenset({0}) for key in ("mail", "seal", "store", "attention",
                                                     "advice_presentation")},
    "provider_retention": frozenset({"NOT_VERIFIED_BY_SAIMAIL"}),
    "historical_shape": frozenset({"UNKNOWN_BYTES_DISCARDED"}),
    "stop_reason": shape.nullable(frozenset({"AUTH_REFUSED", "GATEWAY_UNREACHABLE", "OTHER"})),
}


def _reject(code, detail="registered budget4096 boundary refused"):
    raise SailangError(code, detail)


def implementation():
    return {"observer_sha256": hashlib.sha256(pathlib.Path(shape.__file__).read_bytes()).hexdigest(),
            "harness_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
            "transport_sha256": hashlib.sha256(pathlib.Path(eph.__file__).read_bytes()).hexdigest()}


def registration(root=ROOT, path=REGISTRATION_PATH):
    raw = pathlib.Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != REGISTRATION_SHA256:
        _reject("BUDGET4096_REGISTRATION_MISMATCH")
    doc = json.loads(raw)
    for row in doc["protected_files"]:
        if hashlib.sha256((pathlib.Path(root) / row["path"]).read_bytes()).hexdigest() != row["sha256"]:
            _reject("BUDGET4096_PROTECTED_INPUT_DRIFT")
    if (shape.digest(pilot.GENERATOR_TEMPLATE) != doc["prompts"]["generator_template_sha256"]
            or shape.digest(pilot.REVIEWER_TEMPLATE) != doc["prompts"]["reviewer_template_sha256"]
            or live.MAX_OUTPUT_CHARS != doc["prompts"]["legacy_max_output_chars"]):
        _reject("BUDGET4096_PROMPT_DRIFT")
    if (TOKEN_BUDGETS["GENERATOR"] != doc["token_budgets"]["generator_max_tokens"]
            or TOKEN_BUDGETS["REVIEWER"] != doc["token_budgets"]["reviewer_max_tokens"]
            or TOKEN_BUDGETS["PROBE"] != doc["token_budgets"]["probe_max_tokens"]):
        _reject("BUDGET4096_TOKEN_BUDGET_DRIFT")
    return doc


def _parse_outcome(text):
    """The unchanged strict generator parser's outcome for one exact input."""
    from lab import ally_generation_live as al
    try:
        al.parse_generator_output(text)
    except SailangError as exc:
        return exc.code
    return "OK"


def parse_full_valid(text):
    """True iff the complete serialized candidate passes the unchanged parser."""
    return _parse_outcome(text) == "OK"


def parse_len_prefix_invalid(text):
    """True iff the historical 4000-character prefix FAILS the unchanged parser."""
    return _parse_outcome(text[:LEGACY_OUTPUT_CHARS]) != "OK"


class EphemeralDispatch:
    """One logical call; per-function token budget; full output kept ephemerally.

    The Runner carrier is erased in a ``finally`` block, so no generic raw
    carrier -- and no full output -- survives the stage.  Only metadata
    (hash, byte length, legacy-projection flag, parse shape) is recorded.
    """

    def __init__(self, runner, current):
        self.runner = runner
        self.current = current
        self.calls = []

    def __call__(self, prompt, model, *, unit_id, replicate, role, function):
        self.current["function"] = function
        self.current["max_tokens"] = TOKEN_BUDGETS[function]
        before = self.runner.budget.used
        call = self.runner.call(unit_id, role, prompt, model=model)
        raw = call.get("full_output")
        if not isinstance(raw, str):
            # Probes ride the unchanged generic path; their tiny answer is not
            # parser input.  Fall back to the generic projection for metadata.
            raw = call.get("output") if isinstance(call.get("output"), str) else None
        try:
            usage = call.get("usage") if type(call.get("usage")) is dict else {}
            provider_basis = call.get("provider_basis")
            basis = ("RESPONSE_HEADER" if type(provider_basis) is str and
                     provider_basis.startswith("RESPONSE_HEADER:") else
                     reach._enum(provider_basis or "NOT_EXPOSED",
                                 CALL_SCHEMA["provider_basis"]))
            latency = call.get("latency_s")
            if type(latency) not in (float, int) or not 0 <= latency < 86400:
                latency = None
            record = {
                "call_id": call["call_id"], "replicate": replicate, "role": role,
                "function": function, "requested_model": model,
                "reported_model": reach._model(call.get("reported_model")),
                "provider": shape.text_metadata(call.get("provider")), "provider_basis": basis,
                "request_max_tokens": TOKEN_BUDGETS[function],
                "response_format_kind": RESPONSE_FORMAT_KIND,
                "request_body_sha256": call.get("request_body_sha256"),
                "request_body_bytes": call.get("request_body_bytes"),
                "sent": self.runner.budget.used > before,
                "status": call["status"],
                "error_class": reach._enum(call["error_class"], ERRORS) if call.get("error_class") else None,
                "error_body": shape.text_metadata(call.get("error")),
                "http_status": reach._number(call.get("http_status")), "latency_s": latency,
                "finish_reason": reach._enum(call["finish_reason"], CALL_SCHEMA["finish_reason"][1])
                    if call.get("finish_reason") is not None else None,
                "output_truncated": False if raw is not None else None,
                "inline_trace_removed": call.get("inline_trace_removed") if type(call.get("inline_trace_removed")) is bool else None,
                "prompt_sha256": shape.digest(prompt), "visible_output": shape.text_metadata(raw),
                "full_output_sha256": shape.digest(raw) if raw is not None else None,
                "full_output_bytes": len(raw.encode("utf-8", "surrogatepass")) if raw is not None else None,
                "legacy_projection_would_truncate": (len(raw) > LEGACY_OUTPUT_CHARS)
                    if raw is not None else None,
                "usage": {key: reach._number(usage.get(key)) for key in live._KEPT_USAGE},
                "local_estimated_input_tokens": live.estimate_tokens(prompt),
                "parse_shape": shape.safe_observe(raw, function) if function != "PROBE" else None,
                "parser_status": sc.STAGE_NOT_ATTEMPTED, "parser_error_code": None,
            }
            shape.validate(record, CALL_SCHEMA)
            self.calls.append(record)
            return {"output": raw,
                    "status": record["status"],
                    "error_class": record["error_class"],
                    "reported_model": record["reported_model"]["sha256"],
                    "metadata": record}
        finally:
            call.clear()


def _finish_stage(adapter):
    if adapter.record is not None:
        record = adapter.record["metadata"]
        record["parser_status"] = adapter.parse_status
        record["parser_error_code"] = (reach._enum(adapter.last_error, CODES)
                                       if adapter.last_error else None)
        adapter.record["output"] = None


class ObservedGenerator(pilot.PilotGenerator):
    def generate(self, corpus):
        try:
            return super().generate(corpus)
        finally:
            _finish_stage(self)


class ObservedReviewer(pilot.PilotReviewer):
    def review(self, evidence_resolved_advice, corpus):
        try:
            return super().review(evidence_resolved_advice, corpus)
        finally:
            _finish_stage(self)


def execute_replicate(dispatch, corpus, replicate):
    gen_role, rev_role = ("A", "B") if replicate == 1 else ("B", "A")
    common = {"unit_id": f"R{replicate}", "replicate": replicate}
    generator = ObservedGenerator(dispatch, role=gen_role, requested=ROUTES[gen_role], **common)
    reviewer = ObservedReviewer(dispatch, role=rev_role, requested=ROUTES[rev_role], **common)
    try:
        outcome = ag.generate_reviewed_ally_advice(corpus, generator, reviewer)
        candidate = generator.candidate
        observed = {ref for item in candidate.observed for ref in item.evidence_refs} if candidate else set()
        all_refs = {ref for item in (*candidate.observed, *candidate.counterevidence)
                    for ref in item.evidence_refs} if candidate else set()
        gen_model = (generator.record or {}).get("reported_model")
        rev_model = (reviewer.record or {}).get("reported_model")
        result = {
            "replicate": replicate, "generator_role": gen_role, "reviewer_role": rev_role,
            "stages": reach_stages(generator, reviewer, outcome),
            "outcome": outcome.status,
            "outcome_code": reach._enum(outcome.code, CODES) if outcome.code else None,
            "reviewer_calls": reviewer.calls,
            "candidate_id": ag.ally_candidate_id(candidate) if candidate else None,
            "candidate_emitted": candidate is not None,
            "observed_scope_exact": candidate.observed_scope == pilot.B018_PROJECT_SCOPE if candidate else None,
            "observed_item_count": len(candidate.observed) if candidate else 0,
            "counterevidence_item_count": len(candidate.counterevidence) if candidate else 0,
            "observed_event_count": len(corpus.event_refs_for(observed)),
            "outside_ref_count": len(all_refs - corpus.refs()),
            "review_verdicts": [{"dimension": v.dimension, "verdict": v.verdict,
                                  "evidence_refs": list(v.evidence_refs)}
                                 for v in reviewer.report.verdicts] if reviewer.report else [],
            "same_reported_model_pair": gen_model == rev_model if gen_model and rev_model else None,
            "reviewed_state_minted": outcome.reviewed is not None,
        }
        shape.validate(result, reach.REPLICATE_SCHEMA)
        return result
    finally:
        generator.candidate = None
        reviewer.report = None


def reach_stages(generator, reviewer, outcome):
    from lab import ally_generation_live as al
    return al._stages(generator, reviewer, outcome)


# ------------------------------------------------------------------ dry world


def large_valid_candidate(corpus, *, tail_canary=None):
    """A valid candidate whose serialized JSON is >4000 characters.

    Only a prose field is padded, so the candidate stays inside the existing
    product schema/bounds (MAX_PROSE_BYTES = 4096) while the serialized JSON
    crosses the historical 4000-character projection.  The tail canary, when
    given, sits only AFTER character 4000.
    """
    candidate = pilot.two_event_candidate(corpus)
    filler = "The bounded operational record shows a recurring maintenance signal. "
    padding = filler * 60  # ~3900 chars, stays under MAX_PROSE_BYTES = 4096
    if tail_canary:
        padding = padding[: max(0, 3900 - len(tail_canary))] + tail_canary
    return aa.AllyAdvice(
        created=sc.CREATED,
        work_context=candidate.work_context,
        observed_scope=pilot.B018_PROJECT_SCOPE,
        observed=candidate.observed,
        inferred=padding[:4096],
        guidance_mode=aa.CONSIDER_CHANGE,
        suggested="Bounded dry-run suggestion retained in memory only.",
        counterevidence=candidate.counterevidence,
        uncertainty=(tail_canary or "Bounded dry-run uncertainty retained in memory only."),
    )


class DryTransport:
    """Deterministic wire outputs through the same adapters and strict parsers."""

    def __init__(self, corpus, *, candidate=None):
        self.corpus = corpus
        self._candidate = candidate or pilot.two_event_candidate(corpus)

    def probe(self, model, max_tokens=None):
        return self._ok("OK", model)

    @staticmethod
    def _ok(output, model):
        return {"output": output, "full_output": output, "reported_model": model,
                "http_status": 200, "finish_reason": "stop", "output_truncated": False,
                "legacy_projection_would_truncate": len(output) > LEGACY_OUTPUT_CHARS
                    if isinstance(output, str) else None,
                "inline_trace_removed": False, "latency_s": 0.0, "usage": {},
                "request_body_sha256": shape.digest(output),
                "request_body_bytes": len(output.encode("utf-8"))}

    def send_ephemeral_full(self, prompt, model=None, max_tokens=None):
        if prompt == pilot.generator_prompt(self.corpus):
            if model == ROUTES["A"]:
                output = pilot.wire_candidate_text(self._candidate)
            else:
                output = '{"result":"NO_ADVICE"}'
        else:
            output = pilot.wire_review_text(self._candidate, self.corpus)
        return self._ok(output, model)


def _experiment(built, transport, *, dry_run, started):
    current = {"function": "PROBE", "max_tokens": TOKEN_BUDGETS["PROBE"]}

    def send(prompt, model=None):
        if prompt == pop.PROBE_PROMPT:
            return transport.probe(model)
        return transport.send_ephemeral_full(
            prompt, model=model, max_tokens=current["max_tokens"])

    budget = live.CallBudget(MAX_LIVE_CALLS)
    runner = live.Runner(send, budget, alias=ROUTES["A"])
    dispatch = EphemeralDispatch(runner, current)
    population = pop.offline_population(ROUTES["A"], started, "FIXED_T69_ROUTES")
    participants = []
    for role, route in ROUTES.items():
        probe = dispatch(pop.PROBE_PROMPT, route, unit_id="PROBE", replicate=0,
                         role=role, function="PROBE")
        probe["output"] = None
        if probe["status"] != "OK":
            break
        participants.append(pop.Participant(role=role, requested=route,
            reported_model=probe["reported_model"],
            member_status=pop.OBSERVED_COMBO_MEMBER if role == "A" else pop.NOT_PROVEN_COMBO_MEMBER,
            source="COMBO_ALIAS" if role == "A" else "T69_FIXED_ROUTE"))
    population.participants = tuple(participants)
    projected = pilot.sanitize_population_record_for_private_pilot(population)
    ready = pilot.participants_ready(projected["participants"])
    replicates = []
    if ready:
        for replicate in (1, 2):
            replicates.append(execute_replicate(dispatch, built.reflection_corpus, replicate))
    status = "NO_GO_POPULATION" if not ready else "STOPPED" if runner.stopped else "COMPLETED"
    return _artifact(built, dispatch, budget, replicates, started,
                     dry_run=dry_run, status=status, participants=len(participants))


def _artifact(built, dispatch, budget, replicates, started, *, dry_run, status, participants):
    stop = dispatch.runner.stopped
    result = {
        "version": VERSION, "registration_id": "sha256:" + REGISTRATION_SHA256,
        "implementation": implementation(),
        "started": started, "dry_run": dry_run, "status": status,
        "input": {"registration_id": pilot.B018_REGISTRATION_ID,
                  "build_id": built.build_id, "corpus_id": built.corpus_id,
                  "artifact_count": built.artifact_count, "event_count": built.event_count},
        "routes": dict(ROUTES),
        "token_budgets": {"probe": TOKEN_BUDGETS["PROBE"],
                          "generator": TOKEN_BUDGETS["GENERATOR"],
                          "reviewer": TOKEN_BUDGETS["REVIEWER"]},
        "response_format_kind": RESPONSE_FORMAT_KIND,
        "legacy_output_chars": LEGACY_OUTPUT_CHARS,
        "population_projection": pilot.POPULATION_PROJECTION_VERSION,
        "participant_count": participants,
        "budget": {"max_calls": MAX_LIVE_CALLS, "spent_total": budget.used,
            **{"spent_" + fn.lower(): sum(c["sent"] for c in dispatch.calls if c["function"] == fn)
               for fn in ("PROBE", "GENERATOR", "REVIEWER")},
            "retries": 0, "repair_calls": 0, "network_calls": 0 if dry_run else budget.used},
        "calls": dispatch.calls, "replicates": replicates,
        "privacy": {key: False for key in ARTIFACT_SCHEMA["privacy"]},
        "side_effects": {key: 0 for key in ARTIFACT_SCHEMA["side_effects"]},
        "provider_retention": "NOT_VERIFIED_BY_SAIMAIL",
        "historical_shape": "UNKNOWN_BYTES_DISCARDED",
        "stop_reason": "AUTH_REFUSED" if stop and stop.startswith("AUTH_REFUSED") else stop,
    }
    result["budget"]["spent_generation"] = result["budget"].pop("spent_generator")
    result["budget"]["spent_review"] = result["budget"].pop("spent_reviewer")
    shape.validate(result, ARTIFACT_SCHEMA)
    return result


def render(document):
    shape.validate(document, ARTIFACT_SCHEMA)
    lines = ["# Real-project 4096 budget-only reachability", "",
             f"Registration: `{document['registration_id']}`.",
             f"Status: `{document['status']}`; dry run: {document['dry_run']}.",
             f"Exact B-018 corpus: `{document['input']['corpus_id']}`; 8 artifacts / 5 declared events.",
             (f"Token budgets: probe {document['token_budgets']['probe']}, generator "
              f"{document['token_budgets']['generator']}, reviewer {document['token_budgets']['reviewer']}; "
              f"response_format {document['response_format_kind']}."),
             (f"Calls: {document['budget']['spent_total']}/6; probes {document['budget']['spent_probe']}, "
              f"generation {document['budget']['spent_generation']}, review {document['budget']['spent_review']}; "
              f"retries 0; repairs 0."), ""]
    for row in document["replicates"]:
        lines.extend([f"## R{row['replicate']}", "",
            f"Generator {row['generator_role']} / reviewer {row['reviewer_role']}: `{row['outcome']}`.",
            (f"Candidate parsed: {row['candidate_emitted']}; reviewer calls: {row['reviewer_calls']}; "
             f"reviewed state minted: {row['reviewed_state_minted']}."),
            "Stages: " + ", ".join(f"{k}={v}" for k, v in row["stages"].items()) + ".", ""])
    for call in document["calls"]:
        if call["parse_shape"] is not None:
            lines.extend([f"### R{call['replicate']} {call['function']}", "",
                (f"Requested `{call['requested_model']}`; max_tokens {call['request_max_tokens']}; "
                 f"response_format {call['response_format_kind']}."),
                (f"Reported known label `{call['reported_model']['known']}` "
                 f"(SHA256 `{call['reported_model']['sha256']}`)."),
                (f"Parser `{call['parser_status']}` / `{call['parser_error_code']}`; "
                 f"full output bytes {call['full_output_bytes']}; legacy 4000 would truncate "
                 f"{call['legacy_projection_would_truncate']}; finish `{call['finish_reason']}`."),
                "Shape: " + json.dumps(call["parse_shape"], sort_keys=True) + ".", ""])
    lines.extend(["## Interpretation limits", "",
        "Observability is not acceptance. Only unchanged strict parsers and B-016 gates decide outcomes.",
        ("The local 4000-character parser-input projection is replaced by an ephemeral full-output "
         "path; the generic transport keeps its historical 4000-character behaviour byte for byte."),
        "T-69 R1 shape remains UNKNOWN: its 3218 bytes were discarded; hashes cannot reconstruct them.",
        "Prompts, corpus and requested routes match T-71; only generator max_tokens changed 2048 -> 4096.",
        "Reported models can change behind a requested route. One sample per role assignment is not a model ranking.",
        "NO_ADVICE is successful; a reviewer PASS is not truth; corpus completeness remains NOT_PROVEN.",
        "No generated advice, prompt, corpus content, reviewer rationale or error body is persisted or presented.",
        "No mail, sealing, storage or attention operation is invoked. Provider retention is NOT_VERIFIED_BY_SAIMAIL.",
        "This single live attempt is terminal: no retry, repair, replacement or additional sample.", ""])
    return "\n".join(lines)


def _reserve(path, dry_sha256=None):
    payload = json.dumps({"registration_id": "sha256:" + REGISTRATION_SHA256,
                          "implementation": implementation(), "dry_sha256": dry_sha256,
                          "attempt_id": uuid.uuid4().hex, "started": live._now()})
    result = publish_immutable(pathlib.Path(path), (payload + "\n").encode(),
                               conflict_code="BUDGET4096_ALREADY_ATTEMPTED")
    if result != PUBLISHED:
        _reject("BUDGET4096_ALREADY_ATTEMPTED")


def _write(root, doc, document, api_key):
    shape.validate(document, ARTIFACT_SCHEMA)
    text = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    report = render(document)
    live.assert_no_secret(text, api_key)
    live.assert_no_secret(report, api_key)
    if document["dry_run"]:
        paths = {"dry": pathlib.Path(root) / doc["artifacts"]["dry"]}
    else:
        stamp = document["started"].replace("-", "").replace(":", "")
        paths = {
            "live": pathlib.Path(root) / doc["artifacts"]["live"].replace("<UTCSTAMP>", stamp),
            "report": pathlib.Path(root) / doc["artifacts"]["report"].replace("<UTCSTAMP>", stamp),
            "analysis": pathlib.Path(root) / doc["artifacts"]["analysis"].replace("<UTCSTAMP>", stamp),
        }
    for key, path in paths.items():
        publish_immutable(path, (text if key in ("dry", "live") else report).encode("utf-8"),
                          conflict_code="BUDGET4096_ARTIFACT_EXISTS")
    return {key: str(path) for key, path in paths.items()}


def run(*, dry_run=False, root=ROOT, registration_path=REGISTRATION_PATH):
    doc = registration(root, registration_path)
    built = pilot.prepare_input(root)
    started = live._now()
    api_key = ""
    if dry_run:
        transport = DryTransport(built.reflection_corpus,
                                 candidate=large_valid_candidate(built.reflection_corpus))
        document = _experiment(built, transport, dry_run=True, started=started)
        if document["budget"]["network_calls"] != 0:
            _reject("BUDGET4096_DRY_CONTROL_FAILED")
    else:
        marker = pathlib.Path(root) / doc["attempt_marker"]
        if marker.exists():
            _reject("BUDGET4096_ALREADY_ATTEMPTED")
        dry_path = pathlib.Path(root) / doc["artifacts"]["dry"]
        if not dry_path.exists():
            _reject("BUDGET4096_DRY_CONTROL_REQUIRED")
        proof = json.loads(dry_path.read_text(encoding="utf-8"))
        shape.validate(proof, ARTIFACT_SCHEMA)
        if (not proof["dry_run"] or proof["registration_id"] != "sha256:" + REGISTRATION_SHA256
                or proof["implementation"] != implementation()
                or proof["input"]["corpus_id"] != built.corpus_id
                or proof["input"]["build_id"] != built.build_id
                or proof["budget"]["network_calls"] != 0):
            _reject("BUDGET4096_DRY_CONTROL_REQUIRED")
        try:
            credential = resolve()
            api_key = credential.secret
        except (CredentialNotProvisioned, CredentialError):
            _reject("BUDGET4096_CREDENTIAL_UNAVAILABLE")
        _reserve(marker, hashlib.sha256(dry_path.read_bytes()).hexdigest())
        document = _experiment(built, eph.EphemeralTransport(api_key),
                               dry_run=False, started=started)
    paths = _write(root, doc, document, api_key)
    return {"status": document["status"], "dry_run": dry_run,
            "budget": document["budget"], "artifacts": paths}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--run", action="store_true")
    args = parser.parse_args()
    try:
        result = run(dry_run=args.dry_run)
    except SailangError as exc:
        print(json.dumps({"status": "REFUSED", "code": exc.code}))
        return 1
    except Exception:  # noqa: BLE001 - exception text must never reach the console
        print(json.dumps({"status": "REFUSED", "code": "BUDGET4096_HARNESS_ERROR"}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
