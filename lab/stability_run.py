"""Bounded live stability run over the pre-registered repeat sample (D-025).

The defect class this runner eliminates: **a repeat count chosen after the
answers came in.** It refuses to make a single call unless the plan in
``stability.py`` is byte-for-byte the plan in ``stability_registration.json``,
and it records that registration's digest in the artifact it writes.

Everything else is the ordinary lab contract, reused rather than restated:
the credential handle and its source (D-019), participant discovery and the
declared replacement policy (D-020), the call budget refused before the first
call, observable outputs only, reasoning dropped, transport failure kept apart
from semantics, and the artifact labelled as experiment data (D-018) and by
its experiment class (D-024).

    python lab/stability_run.py --out lab/out --dry-run   # renders the plan, no calls
    python lab/stability_run.py --out lab/out             # the bounded live run
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sailang.frame import Profile  # noqa: E402

from lab import experiment_class as ec  # noqa: E402
from lab import saifren_population as pop  # noqa: E402
from lab import saifren_run as live  # noqa: E402
from lab import stability as st  # noqa: E402
from saimail.credentials import (  # noqa: E402
    DEFAULT_HANDLE, SOURCE_STORE, SOURCES, CredentialError, CredentialNotProvisioned, resolve)
from saimail.publish import publish_immutable  # noqa: E402
from sailang.errors import SailangError  # noqa: E402

REGISTRATION = pathlib.Path(__file__).resolve().parent / st.REGISTRATION_FILE
#: A dry run cannot know who role B will be, and says so instead of naming anyone.
UNRESOLVED_B = "UNRESOLVED_EXTERNAL_COMPARATOR"


class RegistrationMismatch(SystemExit):
    """The plan in code is not the plan that was registered. Nothing was called."""


def declared_registration(profile: Profile) -> dict:
    return st.registration(profile, live.PROTOCOL_VERSION, live.MAX_TOKENS)


def check_registration(profile: Profile, path: pathlib.Path = REGISTRATION) -> dict:
    declared = declared_registration(profile)
    if not path.is_file():
        raise RegistrationMismatch(f"REGISTRATION_MISSING: {path.name} does not exist; a repeat "
                                   "sample is registered before it runs")
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        # An interrupted commit is investigated, never silently replaced (W2-005)
        raise RegistrationMismatch(
            f"REGISTRATION_UNREADABLE: {path.name} is not a readable registration "
            f"({type(exc).__name__}); an interrupted registration is re-created by an "
            "explicit operator decision, not by a rerun") from None
    if not isinstance(stored, dict):
        raise RegistrationMismatch(f"REGISTRATION_UNREADABLE: {path.name} is not a registration "
                                   "object")
    if stored.get("registration") != declared or stored.get("digest") != st.digest(declared):
        raise RegistrationMismatch(
            f"REGISTRATION_MISMATCH: the plan in code differs from {path.name}; a changed "
            "repeat count, case, prompt or rule is a new registration, not an edit")
    return {"digest": stored["digest"], "file": path.name,
            "registered_under": stored.get("registered_under")}


def register(profile: Profile, path: pathlib.Path = REGISTRATION,
             registered_under: Optional[dict] = None) -> dict:
    """Write the registration once, through immutable publication (W2-005).

    The complete bytes are staged and fsynced beside the target first, then
    the name appears through a no-overwrite link (T-42/C2), so competing
    registrants produce exactly one winner, identical bytes converge
    idempotently, and every loser with a different plan receives
    ``REGISTRATION_EXISTS`` without touching the winner's attribution. A
    check-then-overwrite sequence would let two writers each believe they
    registered first.
    """
    declared = declared_registration(profile)
    record = {"registration": declared, "digest": st.digest(declared),
              "registered_under": registered_under or {}}
    payload = (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    try:
        publish_immutable(path, payload, conflict_code="REGISTRATION_EXISTS")
    except SailangError as exc:
        raise RegistrationMismatch(f"{exc.code}: {exc.detail}") from None
    return record


def run(out_dir: pathlib.Path, dry_run: bool, api_key: str = "",
        transport: Optional[object] = None, population=None, discover: Optional[bool] = None,
        credential_source: str = SOURCE_STORE, handle: str = DEFAULT_HANDLE,
        registration_path: pathlib.Path = REGISTRATION) -> dict:
    profile = Profile.load("1")
    registered = check_registration(profile, registration_path)
    declared = st.cases(profile)
    units = {unit.unit_id: unit for _, unit in declared}

    # A caller that hands in a transport hands in the world too (as saifren_run does).
    discovering = (transport is None and not dry_run) if discover is None else (
        bool(discover) and not dry_run)
    credential_backend = None
    if not dry_run and transport is None:
        if not api_key:
            try:
                resolved = resolve(handle=handle, source=credential_source)
            except (CredentialNotProvisioned, CredentialError) as exc:
                raise SystemExit(str(exc)) from None
            api_key, credential_backend = resolved.secret, resolved.backend
        transport = live.HttpTransport(api_key)
    steps_max = st.EXPERIMENT_CALLS + (pop.DISCOVERY_RESERVE if discovering else 0)
    if steps_max > st.MAX_CALLS:
        raise SystemExit(f"the registered plan needs up to {steps_max} calls, over the cap of "
                         f"{st.MAX_CALLS}")
    budget = live.CallBudget(st.MAX_CALLS)
    auth_refused_note = None
    if population is None:
        if discovering:
            try:
                population = live.resolve_population(transport, budget)
            except live.AuthRefused as exc:
                auth_refused_note = str(exc)
                population = pop.offline_population(
                    live.COMBO, live._now(), f"authentication refused: {auth_refused_note}")
        else:
            population = pop.offline_population(live.COMBO, live._now(),
                                                "a dry run makes no call" if dry_run
                                                else "discovery was not requested")
    discovery_calls = budget.used
    participants = st.participants_of(population, live.COMBO)
    if dry_run:
        participants = (("A", live.COMBO), ("B", UNRESOLVED_B))

    runner = live.Runner(None if dry_run else transport.send, budget, alias=live.COMBO)
    if auth_refused_note:
        runner.stopped = f"AUTH_REFUSED: {auth_refused_note}"
    observations: List[dict] = []
    for step in st.plan(participants, declared):
        call = runner.call(step.unit.unit_id, step.role, step.unit.prompt(), model=step.requested)
        observations.append(st.observe(step, call))

    started = runner.calls[0]["timestamp"] if runner.calls else live._now()
    population_record = population.as_record()
    artifact = {
        "authority": live.AUTHORITY,
        "is_not": list(live.IS_NOT),
        "note": live.NOTE,
        "experiment_class": ec.classify_calls(population.combo, runner.calls,
                                              population_record),
        "registration": registered,
        "dry_run": dry_run,
        "harness": {"gateway": "9router", "base_url": live.BASE_URL, "model_alias": live.COMBO,
                    "protocol_version": live.PROTOCOL_VERSION, "max_tokens": live.MAX_TOKENS,
                    "timeout_s": live.TIMEOUT_SECONDS, "repeats": st.REPEATS,
                    "cases": [{"case": label, "unit_id": unit.unit_id}
                              for label, unit in declared],
                    "participants": [{"role": r, "requested": q} for r, q in participants]},
        "credential": {"handle": handle, "source": credential_source,
                       "backend": credential_backend},
        "population": population_record,
        "started": started,
        "max_calls": st.MAX_CALLS,
        "planned_experiment_calls": len(participants) * len(declared) * st.REPEATS,
        "live_calls": budget.used,
        "discovery_calls": discovery_calls,
        "experiment_calls": budget.used - discovery_calls,
        "stopped": runner.stopped,
        "distributions": st.distributions(observations, units, live.PROTOCOL_VERSION),
        "fragility": st.fragility(observations, units),
        "opaque_context": st.opaque_context(runner.calls, live.estimate_tokens),
        "observations": observations,
        "calls": runner.calls,
    }
    serialized = json.dumps(artifact, indent=2, ensure_ascii=False)
    live.assert_no_secret(serialized, api_key)
    report_text = None if dry_run else render(artifact)
    if report_text is not None:
        live.assert_no_secret(report_text, api_key)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = started.replace("-", "").replace(":", "")
    run_id = live.uuid.uuid4().hex[:16]
    name = "stability_dry_run.json" if dry_run else f"stability_live_{stamp}_{run_id}.json"
    path = out_dir / name
    live._write_immutable(path, serialized + "\n")
    written = {"artifact": str(path)}
    if report_text is not None:
        report = out_dir / f"STABILITY_REPORT_{stamp}_{run_id}.md"
        live._write_immutable(report, f"Source artifact: `{name}`\n\n{report_text}")
        written["report"] = str(report)
    return {**artifact, **written}


def _counts(mapping: dict) -> str:
    shown = ", ".join(f"{k} {v}" for k, v in mapping.items() if v)
    return shown or "none"


def render(artifact: dict) -> str:
    """Counts and listings over one stability artifact. No score, no ranking, no merge."""
    klass = artifact["experiment_class"]
    out = [
        "# SAIFREN stability report",
        "",
        f"Authority: `{artifact['authority']}`, which is not "
        + ", ".join(f"`{x}`" for x in artifact["is_not"]) + ".",
        artifact["note"],
        "",
        f"Registration `{artifact['registration']['digest']}`; N={artifact['harness']['repeats']} "
        f"per participant per case; {artifact['live_calls']} live calls "
        f"({artifact['discovery_calls']} discovery, {artifact['experiment_calls']} experiment) "
        f"of cap {artifact['max_calls']}; stopped: {artifact['stopped'] or 'no'}.",
        "Three repeats is a distribution, not a population estimate. A sample remains a sample.",
        "",
        "## EXPERIMENT_CLASS",
        "",
        f"- EXPERIMENT_CLASS: `{klass['experiment_class']}`",
        f"- COMBO: `{klass['combo']}`",
        "- OBSERVED_COMBO_MEMBERS: " + (", ".join(f"`{m}`" for m in
                                                 klass["observed_combo_members"]) or "none"),
        "- EXTERNAL_COMPARATORS: " + (", ".join(f"`{m}`" for m in klass["external_comparators"])
                                      or "none"),
        "- DISTINCT_REPORTED_MODELS: " + (", ".join(f"`{m}`" for m in
                                                    klass["distinct_reported_models"]) or "none"),
        f"- ROSTER_STATUS: `{klass['roster_status']}` (basis `{klass['roster_status_basis']}`)",
        "",
        klass["note"],
        "",
        "## STABILITY_RUNS",
        "",
    ]
    cases = {c["unit_id"]: c["case"] for c in artifact["harness"]["cases"]}
    for row in artifact["distributions"]:
        role = ("no model reported" if row["model"] == st.NO_MODEL
                else ec.describe(row["model"], klass))
        out.append(f"### `{row['model']}` via `{row['route']}` — {cases[row['scenario']]} "
                   f"(`{row['scenario']}`, {row['protocol_version']})")
        out.append(f"- {role}; repeats {row['repeats']}; verdicts {_counts(row['verdicts'])}")
        for boundary, answers in row["answers"].items():
            out.append(f"- {boundary}: {_counts(answers)}")
        for item, classes in row.get("attention", {}).items():
            out.append(f"- {item} attention: {_counts(classes)}")
        out.append("")
    labels = {st.MODEL_VARIANCE: "same participant, same stimulus, different answers",
              st.CROSS_MODEL_DISAGREEMENT: "participants each stable, stably different",
              st.PROTOCOL_HOTSPOT: "independent participants repeatedly failing one boundary",
              st.STIMULUS_CHANGED: "repeats that did not share one prompt digest"}
    for finding, meaning in labels.items():
        rows = artifact["fragility"][finding]
        out += [f"## {finding}", "", f"{meaning}: {len(rows)}"]
        for row in rows:
            detail = {k: v for k, v in row.items() if k != "finding"}
            out.append(f"- {json.dumps(detail, ensure_ascii=False)}")
        out.append("")
    out += ["## OPAQUE_CONTEXT", "",
            "Gateway-reported input minus the locally estimated prompt. What fills the "
            "difference is not visible here and is not guessed at.", ""]
    for model, summary in artifact["opaque_context"]["per_model"].items():
        out.append(f"- `{model}`: {summary['calls']} call(s), {summary['measured']} measured; "
                   f"delta {summary['delta_min']}..{summary['delta_max']} tokens")
    out += ["", "## ERRORS", ""]
    errors = [c for c in artifact["calls"] if c["status"] == "ERROR"]
    if not errors:
        out.append("- none")
    for call in errors:
        out.append(f"- {call['unit_id']}:{call['role']} via `{call.get('requested_model')}` "
                   f"{call.get('error_class')}: {call.get('error')}")
    out.append("")
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pre-registered SAIFREN repeat sample. The credential is resolved from the "
                    "named handle through the local credential store.")
    parser.add_argument("--out", default="lab/out")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--handle", default=DEFAULT_HANDLE)
    parser.add_argument("--credential-source", choices=list(SOURCES), default=SOURCE_STORE)
    parser.add_argument("--register", action="store_true",
                        help="write the registration file once, before any live run")
    parser.add_argument("--ticket")
    parser.add_argument("--source-receipt")
    parser.add_argument("--decision")
    args = parser.parse_args(argv)
    if args.register:
        record = register(Profile.load("1"), registered_under={
            "ticket": args.ticket, "source_receipt": args.source_receipt,
            "decision": args.decision})
        print(json.dumps({"registered": REGISTRATION.name, "digest": record["digest"]}, indent=2))
        return 0
    result = run(pathlib.Path(args.out), args.dry_run, credential_source=args.credential_source,
                 handle=args.handle)
    shown = {k: result[k] for k in ("artifact", "authority", "dry_run", "registration",
                                    "planned_experiment_calls", "live_calls", "discovery_calls",
                                    "experiment_calls", "max_calls", "stopped", "credential")}
    shown["experiment_class"] = {k: result["experiment_class"][k] for k in
                                 ("experiment_class", "observed_combo_members",
                                  "external_comparators", "roster_status")}
    shown["findings"] = {k: len(v) for k, v in result["fragility"].items()}
    printed = json.dumps(shown, indent=2)
    live.assert_no_secret(printed, "")
    print(printed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
