"""Run the preregistered U1 watched-coverage experiment without network or overwrite."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lab.watched_coverage import render_report, run_experiment  # noqa: E402
from saimail_local import no_network  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error("output path already exists; preserve prior evidence and choose a new path")
    probe = {"blocked": 0}
    with tempfile.TemporaryDirectory(prefix="saimail-u1-") as temp:
        with no_network(probe):
            result = run_experiment(Path(temp), probe=probe)
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                                          encoding="utf-8")
    (args.out / "report.md").write_text(render_report(result), encoding="utf-8")
    print(json.dumps({"status": result["status"], "outcome": result["outcome"],
                      "runtime": result["runtime"], "out": str(args.out)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
