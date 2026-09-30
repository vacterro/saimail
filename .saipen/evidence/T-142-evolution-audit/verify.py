"""Validate retained T142 study evidence; never score field utility.

Historical audit receipts/sources remain immutable. This command checks the
observation sequence, not the freshness of the older audit's product sources.
Without --out it is read-only. Reports are also created exclusively.
"""

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent
REGISTRATION_SHA256 = "fec8b9908129b2dcbf5b86d92214ce5ab17cf6a71392c769c272c39cd0a4dc4f"
ENTRY_ONE_SHA256 = "451d1960f397e4789dff611602376ed4395ba69f0db0531007fb9576140d147e"
MEMORY = ("STATE.md", "IDENTITY.md", "BOARD.md", "LOG.md")
HASH = re.compile(r"[0-9a-f]{64}")
CONTEXT = re.compile(r"sha256:[0-9a-f]{64}")
PHASES = {"SCOUT", "BUILD", "VERIFY", "REVIEW", "SHIP"}


class StudyError(ValueError):
    """Evidence or authorization is insufficient; preserve it and refuse."""


def require(condition, message):
    if not condition:
        raise StudyError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def pairs(items):
    value = {}
    for key, item in items:
        require(key not in value, "duplicate JSON field: " + key)
        value[key] = item
    return value


def invalid_constant(value):
    raise StudyError("invalid JSON constant: " + value)


def read(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "retained evidence must be a regular file")
    require(path.stat().st_size <= 2_000_000, "unbounded retained observation")
    try:
        result = json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudyError("malformed retained observation: " + path.name) from exc
    require(isinstance(result, dict), "malformed retained observation object")
    return result


def registration(directory):
    path = Path(directory) / "registration.json"
    value = read(path)
    require(sha(path) == REGISTRATION_SHA256, "immutable registration hash mismatch")
    require(value.get("state") == "REGISTERED", "study is not REGISTERED")
    require(isinstance(value.get("study"), str) and value["study"], "registration study missing")
    limit, minimum = value.get("entry_limit"), value.get("minimum_work_context_boundaries")
    require(type(limit) is int and limit > 0, "registration entry_limit invalid")
    require(type(minimum) is int and 1 <= minimum <= limit, "registration boundary minimum invalid")
    return value


def frontmatter(text):
    lines = text.splitlines()
    require(lines and lines[0].strip() == "---", "canonical context frontmatter missing")
    fields = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        match = re.fullmatch(r"([a-z_]+):\s*(.*)", line)
        require(match is not None, "malformed canonical context field")
        key, value = match.groups()
        require(key not in fields, "duplicate canonical context field")
        fields[key] = value.strip().strip('"')
    raise StudyError("canonical context frontmatter not closed")


def canonical_identity(snapshot, seat):
    """Read retained/current canonical bytes, never caller-provided Work ids."""
    state = frontmatter(snapshot["STATE.md"])
    identity = frontmatter(snapshot["IDENTITY.md"])
    work, phase = state.get("task", ""), state.get("phase")
    require(re.fullmatch(r"T-[0-9]+", work) is not None and phase in PHASES,
            "no current authorized Work/phase")
    require(state.get("agent") == seat and not state.get("blocker"), "no current authorized seat")
    require(state.get("last_event", "").isdigit(), "canonical context last_event invalid")
    lineage = identity.get("project_lineage", "")
    require(re.fullmatch(r"lineage-[0-9a-f]{32}", lineage) is not None,
            "canonical context project lineage invalid")
    doing, active = False, []
    for line in snapshot["BOARD.md"].splitlines():
        if line.startswith("## "):
            doing = line == "## DOING"
        elif doing and line.startswith("- [/] "):
            active.append(line)
    require(len(active) == 1 and active[0].startswith("- [/] " + work + " ")
            and re.search(r"\| owner: " + re.escape(seat) + r"(?:\s*\||\s*$)", active[0]),
            "canonical BOARD does not prove the current authorized Work owner")
    return {"lineage": lineage, "work": work, "phase": phase, "seat": seat,
            "last_event": state["last_event"]}


def boundary_key(identity):
    # Conservative: checkpoints, phase changes, restarts and pagination within
    # one Work never create another qualifying boundary, even for a new seat.
    return "sha256:" + hashlib.sha256(encoded(
        {"lineage": identity["lineage"], "work": identity["work"]}).encode()).hexdigest()


def timestamp(value):
    require(isinstance(value, str), "observation timestamp missing")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise StudyError("observation timestamp malformed") from exc
    require(parsed.tzinfo is not None, "observation timestamp has no timezone")
    return parsed


def observation_kind(focus):
    if not focus["coverage"]["complete_from_start"]:
        return "PARTIAL"
    return "EMPTY" if not focus["reading"] and focus["reviewed"] == 0 else "INSPECT_RECORDED_RESULT"


def opportunities(focus):
    return {row["envelope_id"] for row in focus["reading"]
            if row["reason"] in {"CURRENT_MAIL", "CURRENT_WORK"}}


def validate_record(record, registered, entry):
    try:
        require(type(record["entry"]) is int and record["entry"] == entry,
                "retained entry number differs from filename or duplicates a prior entry")
        require(record["study"] == registered["study"], "wrong study identity")
        require(record["registration_sha256"] == REGISTRATION_SHA256, "registration binding mismatch")
        require(record["actor"] == registered["observer"]["seat"]
                and record["role"] == registered["observer"]["role"], "observer identity mismatch")
        require(record["memory_before"] == record["memory_after"], "project memory changed during observation")
        require(set(record["memory_before"]) == set(MEMORY)
                and all(isinstance(v, str) and HASH.fullmatch(v) for v in record["memory_before"].values()),
                "malformed project memory hashes")
        require(isinstance(record["foreign_state_sha256"], str)
                and HASH.fullmatch(record["foreign_state_sha256"]), "foreign state hash malformed")
        old = record["schema"] == "SAIMAIL_EVOLUTION_AUDIT_OBSERVATION_1"
        require(old if entry == 1 else record["schema"] == "SAIMAIL_REAL_USE_OBSERVATION_2",
                "observation schema/entry mismatch")
        commands = ("contract", "canonical_entry", "explicit_focus") if old else ("contract", "explicit_focus")
        ended = None
        for name in commands:
            command = record[name]
            require(type(command["exit_code"]) is int and command["exit_code"] == 0,
                    "recorded observation command did not succeed")
            start, end = timestamp(command["started"]), timestamp(command["ended"])
            require(end >= start and (ended is None or start >= ended), "command timestamp chronology mismatch")
            ended = end
        answer = record["explicit_focus"]["answer"]
        focus = answer["focus"]
        require(answer["ok"] is True and answer["network_attempts"] == 0,
                "focus observation introduced network activity or failed")
        require(focus["state"] == "OK" and focus["schema"] == "SAIMAIL_HOST_FOCUS_1"
                and focus["authority"] == "INFORMATION_ONLY" and focus["automatic_execution"] is False
                and focus["model_improvement_proven"] is False, "invalid focus observational authority")
        host = focus["host"]
        require(re.fullmatch(r"T-[0-9]+", record["work"]) is not None
                and record["work"] == focus["work"] == host["task"], "observation is not actual recorded Work")
        require(host["seat"] == record["actor"] and host["phase"] in PHASES
                and isinstance(host["lineage"], str) and re.fullmatch(r"lineage-[0-9a-f]{32}", host["lineage"])
                and str(host["last_event"]).isdigit(), "actual Work/context identity malformed")
        require(isinstance(focus["context"], str) and CONTEXT.fullmatch(focus["context"]),
                "focus context hash malformed")
        require(type(focus["reviewed"]) is int and focus["reviewed"] >= 0, "malformed reviewed count")
        coverage = focus["coverage"]
        require(all(type(coverage[k]) is bool for k in ("complete", "complete_from_start"))
                and (not coverage["complete_from_start"] or coverage["complete"]), "malformed coverage")
        require(isinstance(focus["reading"], list) and len(focus["reading"]) <= 200, "malformed reading metadata")
        seen = set()
        for row in focus["reading"]:
            require(row["reason"] in {"CURRENT_MAIL", "CURRENT_WORK", "SUCCESSOR_RESERVE"}
                    and CONTEXT.fullmatch(row["envelope_id"]) and row["envelope_id"] not in seen,
                    "malformed/duplicate reading reference")
            seen.add(row["envelope_id"])
        require(record["observation"] == observation_kind(focus), "EMPTY/partial observation mismatch")
        require(record["independent_receiver"] is False and record["independent_successor"] is False
                and record["field_improvement"] == "UNPROVEN"
                and record["independent_revision"] == record["successor_execution"] == "NOT_RUN",
                "unavailable independent behavior claimed as established")
        require(record["receiver_effort"] == ("UNKNOWN_NO_RECEIVER_OPPORTUNITY"
                if record["observation"] == "EMPTY" else "UNKNOWN_NOT_MEASURED"), "EMPTY/effort evidence mismatch")
        identity = {"lineage": host["lineage"], "work": record["work"], "phase": host["phase"],
                    "seat": host["seat"], "last_event": str(host["last_event"])}
        if old:
            route = record["canonical_entry"]["answer"]
            require(route["ticket"] == record["work"] and route["cold_route"]["phase"] == host["phase"],
                    "historical canonical Work/context differs from focus")
        else:
            argv = record["explicit_focus"]["argv"]
            require(record["contract"]["argv"][1:] == ["--contract"]
                    and argv[1:] == ["--json", "saipen", "letter", "focus", "--workspace", record["workspace"],
                                     "--project-root", record["canonical_context"]["project_root"],
                                     "--seat", record["actor"], "--work", record["work"], "--budget", "20"],
                    "recorded command exceeds observational authority")
            require(record["foreign_state_after_sha256"] == record["foreign_state_sha256"],
                    "foreign SAIPEN state changed during observation")
            retained = record["canonical_memory"]
            require(set(retained) == {"STATE.md", "IDENTITY.md", "BOARD.md"}, "canonical context snapshot missing")
            require(all(hashlib.sha256(text.encode("utf-8")).hexdigest() == record["memory_before"][name]
                        for name, text in retained.items()), "canonical context bytes/hash mismatch")
            require(canonical_identity(retained, record["actor"]) == identity, "canonical context identity mismatch")
            context = record["canonical_context"]
            require(all(context[k] == v for k, v in identity.items()), "canonical context identity mismatch")
            require(context["focus_context"] == focus["context"]
                    and context["continuation"] == focus["continuation"], "canonical focus context mismatch")
            require(re.match(r"^- \d{2}\.\d{2}\.\d{2} \d{2}:\d{2} \[E-" + identity["last_event"] + r"\]",
                             context["log_tail"]), "canonical context LOG event mismatch")
            witness = context["focus_witness"]
            binding = witness["saipen"]
            require(all(binding[k] == host[k] for k in ("lineage", "seat", "phase", "task", "last_event"))
                    and binding["state_agent"] == record["actor"] and binding["seat_source"] == "explicit"
                    and not binding["blocker"] and binding["state"] == witness["state_path"],
                    "canonical focus context witness mismatch")
            root = context["project_root"].replace("\\", "/").rstrip("/")
            require(witness["state_path"].replace("\\", "/") == root + "/.saipen/STATE.md"
                    and witness["identity_path"].replace("\\", "/") == root + "/.saipen/IDENTITY.md"
                    and witness["workspace"] == record["workspace"] and witness["work"] == record["work"]
                    and witness["scope"] == sorted(set(focus["scope"]))
                    and witness["schema"] == "SAIMAIL_AGENT_CYCLE_1", "canonical focus context path mismatch")
            require("sha256:" + hashlib.sha256(encoded(witness).encode()).hexdigest() == focus["context"],
                    "canonical focus context digest mismatch")
            require(record["boundary_key"] == boundary_key(identity)
                    and record["qualifies_context_boundary"] is True, "context boundary claim invalid")
            require(type(record["eligible_receiver_opportunities"]) is int
                    and record["eligible_receiver_opportunities"] == len(opportunities(focus)),
                    "eligible opportunity count differs from retained metadata")
            require(timestamp(record["timestamp"]) >= ended, "observation timestamp precedes focus")
            ended = timestamp(record["timestamp"])
        return identity, ended, opportunities(focus)
    except (KeyError, TypeError, AttributeError, OverflowError) as exc:
        raise StudyError("malformed retained observation fields") from exc


def boundaries(record, registered):
    """Compatibility for historical negative controls; never alter evidence."""
    try:
        validate_record(record, registered, record.get("entry"))
    except StudyError as exc:
        return [str(exc)]
    return []


def sequence(directory=OUT):
    directory = Path(directory)
    registered = registration(directory)
    paths = {}
    for path in directory.glob("runtime*.json"):
        match = re.fullmatch(r"runtime-([0-9]{3})\.json", path.name)
        entry = 1 if path.name == "runtime.json" else int(match[1]) if match else None
        require(entry is not None and (entry >= 2 or path.name == "runtime.json"),
                "noncanonical or duplicate observation filename: " + path.name)
        require(entry not in paths, "duplicate retained entry filename")
        require(entry <= registered["entry_limit"], "registration entry_limit exceeded")
        paths[entry] = path
    require(paths and sorted(paths) == list(range(1, len(paths) + 1)), "retained chronology gap")
    require(sha(paths[1]) == ENTRY_ONE_SHA256, "immutable entry 1 hash mismatch")
    seen, opportunities_seen, previous_end, lineage = set(), set(), None, None
    for entry, path in sorted(paths.items()):
        record = read(path)
        identity, ended, eligible = validate_record(record, registered, entry)
        if entry > 1:
            require(record.get("previous_observation_sha256") == sha(paths[entry - 1]),
                    "previous observation hash binding mismatch")
        require(lineage is None or lineage == identity["lineage"], "foreign project lineage in study")
        lineage = identity["lineage"]
        key = boundary_key(identity)
        require(key not in seen, "same Work/context boundary counted more than once")
        require(previous_end is None or ended >= previous_end, "retained timestamp chronology mismatch")
        seen.add(key)
        opportunities_seen.update((lineage, reference) for reference in eligible)
        previous_end = ended
    return {"study": registered["study"], "registration_sha256": REGISTRATION_SHA256,
            "entry_one_sha256": ENTRY_ONE_SHA256, "retained_observations": len(paths),
            "qualifying_work_context_boundaries": len(seen),
            "minimum_work_context_boundaries": registered["minimum_work_context_boundaries"],
            "entry_limit": registered["entry_limit"], "eligible_receiver_opportunities": len(opportunities_seen),
            "independent_receiver_assessments": 0, "independently_chosen_revisions": 0,
            "fresh_successor_executions": 0, "field_improvement": "UNPROVEN",
            "next_entry": len(paths) + 1 if len(paths) < registered["entry_limit"] else None,
            "last_observation_sha256": sha(paths[len(paths)]), "last_observed_at": previous_end.isoformat(),
            "boundary_keys": sorted(seen), "project_lineage": lineage,
            "claim_boundary": "Retained metadata/identity consistency; independent behavior is not enrolled or measured"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", help="optional new report basename (existing reports are never replaced)")
    args = parser.parse_args()
    try:
        result = {"schema": "SAIMAIL_REAL_USE_SEQUENCE_CHECK_1", "state": "PASS", **sequence()}
        if args.out:
            require(re.fullmatch(r"[a-z][a-z0-9_-]*\.json", args.out)
                    and not args.out.startswith(("runtime", "registration", "sources")), "invalid report filename")
            with (OUT / args.out).open("x", encoding="utf-8", newline="\n") as target:
                target.write(json.dumps(result, indent=2) + "\n")
    except (StudyError, OSError) as exc:
        print(json.dumps({"state": "FAIL", "reason": str(exc), "field_improvement": "UNPROVEN"}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
