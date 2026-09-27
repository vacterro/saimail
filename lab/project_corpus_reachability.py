"""One registered LAB reachability experiment; unchanged B-016 acceptance gates.

Use --dry-run, then --run once. CLI prints metadata paths and counts only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lab import ally_generation_live as strict
from lab import ally_generation_scenarios as sc
from lab import parse_shape as shape
from lab import project_corpus_generation_pilot as pilot
from lab import saifren_population as pop
from lab import saifren_run as live
from sailang.errors import SailangError
from saimail import ally_advice as aa
from saimail import ally_generation as ag
from saimail.credentials import CredentialError, CredentialNotProvisioned, resolve
from saimail.publish import PUBLISHED, publish_immutable

ROOT = Path(__file__).resolve().parent.parent
REGISTRATION_PATH = ROOT / "lab/project_corpus_reachability_registration.json"
REGISTRATION_SHA256 = "825c0853dc1a5cd73939bbf91201fb1e4f8a8b40a62e0d69a87d0fcd6be7dc16"
VERSION = "PROJECT-CORPUS-REACHABILITY-1"
ROUTES = {"A": "SAIFREN", "B": "goat/MiniMaxAI/MiniMax-M3"}
KNOWN_MODELS = frozenset({*ROUTES.values(), "deepseek/deepseek-v4-flash", "MiniMaxAI/MiniMax-M3"})
ERRORS = frozenset({"OTHER", "HTTPError", "EmptyOutput", "TimeoutError", "URLError",
                    "ConnectionError", "OSError", "BudgetExceeded", "HARNESS_ERROR",
                    "MalformedResponse", "ResponseTooLarge", "GatewayError"})
CODES = frozenset({"OTHER", *(
    value for module in (strict, ag, aa, pilot) for name, value in vars(module).items()
    if name.isupper() and type(value) is str and value.startswith(("ALLY_", "PILOT_")))})
PARSE = frozenset({sc.STAGE_NOT_ATTEMPTED, sc.STAGE_OK, sc.STAGE_SCHEMA_ERROR})
STAGE_VALUES = frozenset({sc.STAGE_NOT_REACHED, sc.STAGE_NOT_ATTEMPTED, sc.STAGE_OK,
    sc.STAGE_ERROR, sc.STAGE_SCHEMA_ERROR, sc.STAGE_NO_ADVICE, sc.STAGE_SKIPPED,
    sc.STAGE_CANDIDATE, sc.STAGE_FAIL, sc.STAGE_PASS,
    ag.APPROVED, ag.NO_ADVICE, ag.REJECTED, ag.ERROR})
LABEL_SCHEMA = {**shape.TEXT_METADATA_SCHEMA, "known": shape.nullable(KNOWN_MODELS | {"OTHER"})}
CALL_SCHEMA = {
    "call_id": ("regex", r"[0-9a-f]{12}"),
    "replicate": frozenset({0, 1, 2}), "role": frozenset({"A", "B"}),
    "function": frozenset({"PROBE", "GENERATOR", "REVIEWER"}),
    "requested_model": frozenset(ROUTES.values()), "reported_model": LABEL_SCHEMA,
    "provider": shape.TEXT_METADATA_SCHEMA,
    "provider_basis": frozenset({"RESPONSE_FIELD", "RESPONSE_HEADER", "NOT_EXPOSED", "OTHER"}),
    "sent": bool, "status": frozenset({"OK", "ERROR", "NOT_RUN"}),
    "error_class": shape.nullable(ERRORS), "error_body": shape.TEXT_METADATA_SCHEMA,
    "http_status": shape.nullable(int), "latency_s": shape.nullable(float),
    "finish_reason": shape.nullable(frozenset({"stop", "length", "content_filter", "tool_calls", "OTHER"})),
    "output_truncated": shape.nullable(bool), "inline_trace_removed": shape.nullable(bool),
    "prompt_sha256": shape.HASH, "visible_output": shape.TEXT_METADATA_SCHEMA,
    "usage": {key: shape.nullable(int) for key in live._KEPT_USAGE},
    "local_estimated_input_tokens": int,
    "parse_shape": shape.nullable(shape.SHAPE_SCHEMA),
    "parser_status": PARSE, "parser_error_code": shape.nullable(CODES),
}
REPLICATE_SCHEMA = {
    "replicate": frozenset({1, 2}), "generator_role": frozenset({"A", "B"}),
    "reviewer_role": frozenset({"A", "B"}),
    "stages": {name: STAGE_VALUES for name in sc.STAGES},
    "outcome": frozenset({ag.NO_ADVICE, ag.APPROVED, ag.REJECTED, ag.ERROR}),
    "outcome_code": shape.nullable(CODES), "reviewer_calls": int,
    "candidate_id": shape.nullable(shape.IDENTITY), "candidate_emitted": bool,
    "observed_scope_exact": shape.nullable(bool), "observed_item_count": int,
    "counterevidence_item_count": int, "observed_event_count": int,
    "outside_ref_count": int,
    "review_verdicts": ("list", {"dimension": frozenset(ag.DIMENSIONS),
        "verdict": frozenset({ag.PASS, ag.FAIL, ag.UNKNOWN}),
        "evidence_refs": ("list", shape.IDENTITY, 128)}, 8),
    "same_reported_model_pair": shape.nullable(bool), "reviewed_state_minted": bool,
}
ARTIFACT_SCHEMA = {
    "version": frozenset({VERSION}), "registration_id": shape.IDENTITY,
    "implementation": {"observer_sha256": shape.HASH, "harness_sha256": shape.HASH},
    "started": ("regex", r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"), "dry_run": bool,
    "status": frozenset({"COMPLETED", "NO_GO_POPULATION", "CREDENTIAL_UNAVAILABLE", "STOPPED"}),
    "input": {"registration_id": shape.IDENTITY, "build_id": shape.IDENTITY,
              "corpus_id": shape.IDENTITY, "artifact_count": int, "event_count": int},
    "routes": {key: frozenset({value}) for key, value in ROUTES.items()},
    "population_projection": frozenset({pilot.POPULATION_PROJECTION_VERSION}),
    "participant_count": int,
    "budget": {key: int for key in ("max_calls", "spent_total", "spent_probe",
        "spent_generation", "spent_review", "retries", "repair_calls", "network_calls")},
    "calls": ("list", CALL_SCHEMA, 6), "replicates": ("list", REPLICATE_SCHEMA, 2),
    "privacy": {key: frozenset({False}) for key in ("prompt_persisted", "output_persisted",
        "candidate_prose_persisted", "reviewer_rationale_persisted", "error_body_persisted")},
    "side_effects": {key: frozenset({0}) for key in ("mail", "seal", "store", "attention", "advice_presentation")},
    "provider_retention": frozenset({"NOT_VERIFIED_BY_SAIMAIL"}),
    "historical_t69_shape": frozenset({"UNKNOWN_BYTES_DISCARDED"}),
    "stop_reason": shape.nullable(frozenset({"AUTH_REFUSED", "GATEWAY_UNREACHABLE", "OTHER"})),
}


def _reject(code):
    raise SailangError(code, "registered reachability boundary refused")


def _enum(value, allowed):
    return value if type(value) is str and value in allowed else "OTHER"


def _number(value):
    return value if type(value) is int and 0 <= value < 2**63 else None


def _model(value):
    return {**shape.text_metadata(value),
            "known": _enum(value, KNOWN_MODELS) if type(value) is str else None}


def implementation():
    return {"observer_sha256": hashlib.sha256(Path(shape.__file__).read_bytes()).hexdigest(),
            "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def registration(root=ROOT, path=REGISTRATION_PATH):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != REGISTRATION_SHA256:
        _reject("REACHABILITY_REGISTRATION_MISMATCH")
    doc = json.loads(raw)
    for row in [doc["contract"], *doc["protected_files"]]:
        if hashlib.sha256((Path(root) / row["path"]).read_bytes()).hexdigest() != row["sha256"]:
            _reject("REACHABILITY_PROTECTED_INPUT_DRIFT")
    if (shape.digest(pilot.GENERATOR_TEMPLATE) != doc["prompts"]["generator_template_sha256"]
            or shape.digest(pilot.REVIEWER_TEMPLATE) != doc["prompts"]["reviewer_template_sha256"]
            or live.MAX_TOKENS != doc["prompts"]["max_tokens"]
            or live.MAX_OUTPUT_CHARS != doc["prompts"]["max_output_chars"]):
        _reject("REACHABILITY_PROMPT_DRIFT")
    return doc


class ObservingDispatch:
    """Project metadata explicitly and erase the Runner carrier, even on failure."""

    def __init__(self, runner):
        self.runner = runner
        self.calls = []

    def __call__(self, prompt, model, *, unit_id, replicate, role, function):
        before = self.runner.budget.used
        call = self.runner.call(unit_id, role, prompt, model=model)
        raw = call.get("output")
        try:
            usage = call.get("usage") if type(call.get("usage")) is dict else {}
            provider_basis = call.get("provider_basis")
            basis = ("RESPONSE_HEADER" if type(provider_basis) is str and
                     provider_basis.startswith("RESPONSE_HEADER:") else
                     _enum(provider_basis or "NOT_EXPOSED", CALL_SCHEMA["provider_basis"]))
            latency = call.get("latency_s")
            if type(latency) not in (float, int) or not 0 <= latency < 86400:
                latency = None
            record = {
                "call_id": call["call_id"], "replicate": replicate, "role": role,
                "function": function, "requested_model": model,
                "reported_model": _model(call.get("reported_model")),
                "provider": shape.text_metadata(call.get("provider")), "provider_basis": basis,
                "sent": self.runner.budget.used > before,
                "status": call["status"],
                "error_class": _enum(call["error_class"], ERRORS) if call.get("error_class") else None,
                "error_body": shape.text_metadata(call.get("error")),
                "http_status": _number(call.get("http_status")), "latency_s": latency,
                "finish_reason": _enum(call["finish_reason"], CALL_SCHEMA["finish_reason"][1])
                    if call.get("finish_reason") is not None else None,
                "output_truncated": call.get("output_truncated") if type(call.get("output_truncated")) is bool else None,
                "inline_trace_removed": call.get("inline_trace_removed") if type(call.get("inline_trace_removed")) is bool else None,
                "prompt_sha256": shape.digest(prompt), "visible_output": shape.text_metadata(raw),
                "usage": {key: _number(usage.get(key)) for key in live._KEPT_USAGE},
                "local_estimated_input_tokens": live.estimate_tokens(prompt),
                "parse_shape": shape.safe_observe(raw, function) if function != "PROBE" else None,
                "parser_status": sc.STAGE_NOT_ATTEMPTED, "parser_error_code": None,
            }
            shape.validate(record, CALL_SCHEMA)
            self.calls.append(record)
            return {"output": raw, "status": record["status"],
                    "error_class": record["error_class"],
                    "reported_model": record["reported_model"]["sha256"],
                    "metadata": record}
        finally:
            # Runner records can contain unanticipated nested transport metadata.
            # No generic raw carrier survives this boundary.
            call.clear()


def _finish_stage(adapter):
    if adapter.record is not None:
        record = adapter.record["metadata"]
        record["parser_status"] = adapter.parse_status
        record["parser_error_code"] = (
            _enum(adapter.last_error, CODES) if adapter.last_error else None)
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
            "stages": strict._stages(generator, reviewer, outcome),
            "outcome": outcome.status,
            "outcome_code": _enum(outcome.code, CODES) if outcome.code else None,
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
        shape.validate(result, REPLICATE_SCHEMA)
        return result
    finally:
        generator.candidate = None
        reviewer.report = None


def artifact(built, dispatch, budget, replicates, started, *, dry_run, status, participants):
    stop = dispatch.runner.stopped
    result = {
        "version": VERSION, "registration_id": "sha256:" + REGISTRATION_SHA256,
        "implementation": implementation(),
        "started": started, "dry_run": dry_run, "status": status,
        "input": {"registration_id": pilot.B018_REGISTRATION_ID,
                  "build_id": built.build_id, "corpus_id": built.corpus_id,
                  "artifact_count": built.artifact_count, "event_count": built.event_count},
        "routes": dict(ROUTES), "population_projection": pilot.POPULATION_PROJECTION_VERSION,
        "participant_count": participants,
        "budget": {"max_calls": 6, "spent_total": budget.used,
            **{"spent_" + fn.lower(): sum(c["sent"] for c in dispatch.calls if c["function"] == fn)
               for fn in ("PROBE", "GENERATOR", "REVIEWER")},
            "retries": 0, "repair_calls": 0, "network_calls": 0 if dry_run else budget.used},
        "calls": dispatch.calls, "replicates": replicates,
        "privacy": {key: False for key in ARTIFACT_SCHEMA["privacy"]},
        "side_effects": {key: 0 for key in ARTIFACT_SCHEMA["side_effects"]},
        "provider_retention": "NOT_VERIFIED_BY_SAIMAIL",
        "historical_t69_shape": "UNKNOWN_BYTES_DISCARDED",
        "stop_reason": "AUTH_REFUSED" if stop and stop.startswith("AUTH_REFUSED") else stop,
    }
    # The public name is review; the transport function is REVIEWER.
    result["budget"]["spent_generation"] = result["budget"].pop("spent_generator")
    result["budget"]["spent_review"] = result["budget"].pop("spent_reviewer")
    shape.validate(result, ARTIFACT_SCHEMA)
    return result


class DryTransport:
    """Deterministic wire outputs through the same adapters and strict parsers."""

    def __init__(self, corpus):
        self.corpus = corpus
        self.candidate = pilot.two_event_candidate(corpus)

    def probe(self, model):
        return self._ok("OK", model)

    @staticmethod
    def _ok(output, model):
        return {"output": output, "reported_model": model, "http_status": 200,
                "finish_reason": "stop", "output_truncated": False,
                "inline_trace_removed": False, "latency_s": 0.0, "usage": {}}

    def send(self, prompt, model=None):
        if prompt == pilot.generator_prompt(self.corpus):
            output = (pilot.wire_candidate_text(self.candidate) if model == ROUTES["A"]
                      else '{"result":"NO_ADVICE"}')
        else:
            output = pilot.wire_review_text(self.candidate, self.corpus)
        return self._ok(output, model)


def _experiment(built, transport, *, dry_run, started):
    def send(prompt, model=None):
        return transport.probe(model) if prompt == pop.PROBE_PROMPT else transport.send(prompt, model=model)

    budget = live.CallBudget(6)
    runner = live.Runner(send, budget, alias=ROUTES["A"])
    dispatch = ObservingDispatch(runner)
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
    return artifact(built, dispatch, budget, replicates, started,
                    dry_run=dry_run, status=status, participants=len(participants))


def render(document):
    """Validate before rendering any metadata into Markdown."""
    shape.validate(document, ARTIFACT_SCHEMA)
    lines = ["# Real-project strict-schema reachability", "",
             f"Registration: `{document['registration_id']}`.",
             f"Status: `{document['status']}`; dry run: {document['dry_run']}.",
             f"Exact B-018 corpus: `{document['input']['corpus_id']}`; 8 artifacts / 5 declared events.",
             (f"Calls: {document['budget']['spent_total']}/6; probes {document['budget']['spent_probe']}, "
              f"generation {document['budget']['spent_generation']}, review {document['budget']['spent_review']}; retries 0; repairs 0."), ""]
    for row in document["replicates"]:
        lines.extend([f"## R{row['replicate']}", "",
            f"Generator {row['generator_role']} / reviewer {row['reviewer_role']}: `{row['outcome']}`.",
            (f"Candidate parsed: {row['candidate_emitted']}; reviewer calls: {row['reviewer_calls']}; "
             f"reviewed state minted: {row['reviewed_state_minted']}."),
            "Stages: " + ", ".join(f"{k}={v}" for k, v in row["stages"].items()) + ".", ""])
    for call in document["calls"]:
        if call["parse_shape"] is not None:
            lines.extend([f"### R{call['replicate']} {call['function']}", "",
                (f"Requested `{call['requested_model']}`; reported known label `{call['reported_model']['known']}` "
                 f"(SHA256 `{call['reported_model']['sha256']}`)."),
                (f"Parser `{call['parser_status']}` / `{call['parser_error_code']}`; "
                 f"input bytes {call['visible_output']['bytes']}; finish `{call['finish_reason']}`; "
                 f"transport cap applied {call['output_truncated']}."),
                "Shape: " + json.dumps(call["parse_shape"], sort_keys=True) + ".", ""])
    lines.extend(["## Interpretation limits", "",
        "Observability is not acceptance. Only unchanged strict parsers and B-016 gates decide outcomes.",
        "T-69 R1 shape remains UNKNOWN: its 3218 bytes were discarded; hashes cannot reconstruct them.",
        "Prompts, parser-input transport cap, corpus and requested routes match T-69. Two fixed-route probes replace catalog selection.",
        "Reported models can change behind a requested route. One sample per role assignment is not a model ranking.",
        "NO_ADVICE is successful; a reviewer PASS is not truth; corpus completeness remains NOT_PROVEN.",
        "No generated advice, prompt, corpus content, reviewer rationale or error body is persisted or presented.",
        "No mail, sealing, storage or attention operation is invoked. Provider retention/training use is NOT_VERIFIED_BY_SAIMAIL.",
        "This single live attempt is terminal: no retry, repair, replacement or additional sample.", ""])
    return "\n".join(lines)


def _reserve(path, dry_sha256=None):
    payload = json.dumps({"registration_id": "sha256:" + REGISTRATION_SHA256,
                          "implementation": implementation(), "dry_sha256": dry_sha256,
                          "attempt_id": uuid.uuid4().hex, "started": live._now()})
    result = publish_immutable(Path(path), (payload + "\n").encode(),
                               conflict_code="REACHABILITY_ALREADY_ATTEMPTED")
    if result != PUBLISHED:
        _reject("REACHABILITY_ALREADY_ATTEMPTED")


def _write(root, doc, document, api_key):
    shape.validate(document, ARTIFACT_SCHEMA)
    text = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    report = render(document)
    live.assert_no_secret(text, api_key)
    live.assert_no_secret(report, api_key)
    key = "dry" if document["dry_run"] else "live"
    paths = {key: Path(root) / doc["artifacts"][key]}
    if not document["dry_run"]:
        paths.update({key: Path(root) / doc["artifacts"][key] for key in ("report", "interpretation")})
    for key, path in paths.items():
        publish_immutable(path, (text if key in ("dry", "live") else report).encode("utf-8"),
                           conflict_code="REACHABILITY_ARTIFACT_EXISTS")
    return {key: str(path) for key, path in paths.items()}


def run(*, dry_run=False, root=ROOT, registration_path=REGISTRATION_PATH):
    doc = registration(root, registration_path)
    built = pilot.prepare_input(root)
    started = live._now()
    api_key = ""
    if dry_run:
        document = _experiment(built, DryTransport(built.reflection_corpus),
                               dry_run=True, started=started)
        if ([row["outcome"] for row in document["replicates"]] != [ag.APPROVED, ag.NO_ADVICE]
                or document["budget"]["network_calls"] != 0):
            _reject("REACHABILITY_DRY_CONTROL_FAILED")
    else:
        marker = Path(root) / doc["attempt_marker"]
        if marker.exists():
            _reject("REACHABILITY_ALREADY_ATTEMPTED")
        dry_bytes = (Path(root) / doc["artifacts"]["dry"]).read_bytes()
        proof = json.loads(dry_bytes)
        shape.validate(proof, ARTIFACT_SCHEMA)
        if (not proof["dry_run"] or proof["registration_id"] != "sha256:" + REGISTRATION_SHA256
                or proof["implementation"] != implementation()
                or proof["input"]["corpus_id"] != built.corpus_id
                or proof["input"]["build_id"] != built.build_id
                or [r["outcome"] for r in proof["replicates"]] != [ag.APPROVED, ag.NO_ADVICE]
                or proof["budget"]["network_calls"] != 0):
            _reject("REACHABILITY_DRY_CONTROL_REQUIRED")
        historical = json.loads((Path(root) / "lab/out/project_corpus_generation_live_20260919T220641Z.json").read_text(encoding="utf-8"))
        if live.BASE_URL != historical["harness"]["base_url"]:
            _reject("REACHABILITY_GATEWAY_DRIFT")
        try:
            credential = resolve()
            api_key = credential.secret
        except (CredentialNotProvisioned, CredentialError):
            # No credential messages or provider content reach the console.
            _reject("REACHABILITY_CREDENTIAL_UNAVAILABLE")
        _reserve(marker, hashlib.sha256(dry_bytes).hexdigest())
        document = _experiment(built, live.HttpTransport(api_key), dry_run=False, started=started)
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
        print(json.dumps({"status": "REFUSED", "code": "REACHABILITY_HARNESS_ERROR"}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
