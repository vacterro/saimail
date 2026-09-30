"""Run the unchanged provenance oracle against current or restored modules."""

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", choices=("before", "current"), required=True)
    parser.add_argument("--out", choices=("restored-before", "restored-after"), required=True)
    args = parser.parse_args()
    target = OUT / args.out
    if target.with_suffix(".json").exists():
        raise SystemExit("Existing control retained; do not overwrite it.")
    oracle = json.loads((OUT / "oracle.json").read_text(encoding="utf-8"))
    for field, name in (("verifier_sha256", "tests/test_feedback_origin.py"),
                        ("fixture_sha256", "tests/test_correspondence.py"),
                        ("projection_fixture_sha256", "tests/test_host_focus.py"),
                        ("config_sha256", "pyproject.toml")):
        assert sha(ROOT / name) == oracle[field], "Pinned verifier input changed: " + name
    sys.path.insert(0, str(ROOT))
    selected = OUT / "before-subject" if args.subject == "before" else ROOT
    import saimail

    subjects = {}
    for name, relative in (("saimail.host_contract", "saimail/host_contract.py"),
                           ("saimail.correspondence", "saimail/correspondence.py"),
                           ("saimail_host", "saimail_host.py")):
        path = selected / relative
        subjects[relative] = sha(path)
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        if name.startswith("saimail."):
            setattr(saimail, name.split(".")[1], module)
    import pytest

    transcript = io.StringIO()
    with contextlib.redirect_stdout(transcript), contextlib.redirect_stderr(transcript):
        exit_code = int(pytest.main(["-q", "--tb=short", str(ROOT / "tests/test_feedback_origin.py"),
                                    "--junitxml=" + str(target.with_suffix(".xml"))]))
    target.with_suffix(".txt").write_text(transcript.getvalue(), encoding="utf-8")
    root = ET.parse(target.with_suffix(".xml")).getroot()
    counts = {key: sum(int(suite.attrib[key]) for suite in root.iter("testsuite"))
              for key in ("tests", "failures", "errors", "skipped")}
    expected = counts == {"tests": 31, "failures": 31 if args.subject == "before" else 0,
                          "errors": 0, "skipped": 0}
    result = {"schema": "SAIMAIL_FEEDBACK_ORIGIN_CONTROL_1", "subject": args.subject,
              "exit_code": exit_code, "counts": counts, "criterion_met": expected,
              "verifier_sha256": oracle["verifier_sha256"], "control_sha256": sha(Path(__file__)),
              "subjects": subjects, "claim_boundary": "Isolated protocol semantics; scripted seats are not independent field actors"}
    target.with_suffix(".json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    raise SystemExit(not expected)


if __name__ == "__main__":
    main()
