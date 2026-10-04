"""saiwiki producer publish for the SAIMAIL project.

Adapted from the SAIPEN home producer's kitchen/_publish_package.py. Reads
the project's own canonical sources into the declared read set, binds the
package to the current source identity and the current charter role
revision, stages the 9 wiki pages, and publishes one strict READY package.

Touches only .saipen/extensions/subs/saiwiki/kitchen/. Never the main tree,
no integration, commit, tag, push or remote write.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, r"V:\___VAC\__K\__CODE\_AI_STUFF_AGENTIC\_SAIPEN\tools")

from freshness import compute_role_revision, compute_source_identity  # noqa: E402
from saipen_engine import producer as producer_api  # noqa: E402


def main() -> None:
    namespace = ROOT / ".saipen" / "extensions" / "subs" / "saiwiki"
    wiki = namespace / "kitchen" / "wiki"
    charter = ROOT / ".saipen" / "extensions" / "subs" / "saiwiki.md"
    identity = compute_source_identity(ROOT)
    role_revision = compute_role_revision(charter)

    page_names = [
        "Architecture.md",
        "Benchmarks.md",
        "Decisions.md",
        "Getting-Started.md",
        "Home.md",
        "Lab.md",
        "Modules.md",
        "Protocols.md",
        "Use-Cases.md",
        "_Footer.md",
        "_Sidebar.md",
    ]
    write_paths = [
        (wiki / name).relative_to(ROOT).as_posix() for name in page_names
    ]
    read_paths = [
        "README.md",
        "CHANGELOG.md",
        "LICENSE",
        "VERSION",
        "pyproject.toml",
        "spec/BACKLOG.md",
        "spec/DECISIONS.md",
        "spec/DECISIONS-D056.md",
        "spec/DECISIONS-D057.md",
        "spec/DECISIONS-D058.md",
        "spec/DECISIONS-D059.md",
        "spec/DECISIONS-D060.md",
        "spec/DECISIONS-D061.md",
        "spec/DECISIONS-D062.md",
        "spec/DECISIONS-D063.md",
        "spec/DECISIONS-D064.md",
        "spec/DECISIONS-D065.md",
        "spec/DECISIONS-D066.md",
        "spec/00-PRINCIPLES.md",
        "spec/01-SAILANG-v0.md",
        "spec/02-SAIENVELOPE-v0.md",
        "spec/03-POST-OFFICE.md",
        "spec/04-LEGACY-v0.md",
        "spec/04-SAIPEN-SEAM.md",
        "spec/05-SAILETTER-v0.md",
        "spec/06-HUMAN-HARDWARE-v0.md",
        "spec/07-HUMAN-ATTENTION-v0.md",
        "spec/08-ALLY-ADVICE-v0.md",
        "spec/22-LOCAL-INBOX-QUERY-v0.md",
        "spec/24-LOCAL-CORRESPONDENCE-CONTINUATION-v0.md",
        "spec/25-DESKTOP-LOCAL-MESSENGER-v0.md",
        "spec/26-SAITELEMES-v0.md",
        "spec/27-SAIPEN-WORK-DESK-v0.md",
        "spec/28-DURABLE-OUTBOX-v0.md",
        "spec/29-PARTICIPANT-REGISTRY-v0.md",
        "spec/30-SAIPEN-CAPABILITIES-v0.md",
        "spec/31-SAITELEMES-NOTIFY-v0.md",
        "spec/32-INTER-AGENT-WORKSHOP-POLICY-v0.md",
        "spec/33-USEFUL-CORRESPONDENCE-v1.md",
        "spec/34-MASTER-KEY-VAULT-v1.md",
        "saimail/ally_advice.py",
        "saimail/acceptance.py",
        "saimail/agent_cycle.py",
        "saimail/capabilities.py",
        "saimail/correspondence.py",
        "saimail/credentials.py",
        "saimail/custody.py",
        "saimail/envelope.py",
        "saimail/hardware_piv.py",
        "saimail/host_contract.py",
        "saimail/human_attention.py",
        "saimail/inbox_query.py",
        "saimail/keyvault.py",
        "saimail/legacy.py",
        "saimail/letters.py",
        "saimail/notify.py",
        "saimail/outbox.py",
        "saimail/participants.py",
        "saimail/postoffice.py",
        "saimail/promotion.py",
        "saimail/provenance.py",
        "saimail/publish.py",
        "saimail/quarantine.py",
        "saimail/sailetter.py",
        "saimail/sainote.py",
        "saimail/saipen_bridge.py",
        "saimail/selector.py",
        "saimail/workspace.py",
        "saimail_local.py",
        "saimail_host.py",
        "saimail_project.py",
        "UI.md",
        "humbox/INSTITUTION.md",
        "humbox/EVOLUTION.md",
        "humbox/SAIPEN-WORK-DESK.md",
        "lab/analysis/institution_20260930.md",
        "lab/analysis/saifren_sample_T145.md",
        "lab/LATEST.md",
        "lab/stability_registration.json",
        "bench/ANALYSIS.md",
        "provenance/RECEIPT_KIND_SCOPE.json",
        "provenance/quarantine/SRC-007.json",
        "spec/PROPOSAL-SAIPEN-RECEIPT-QUARANTINE.md",
    ]
    absent = [path for path in read_paths if not (ROOT / path).is_file()]
    if absent:
        raise RuntimeError(f"missing read dependencies: {absent}")

    epoch = producer_api.ProducerEpoch.claim(namespace)
    package = producer_api.build_package(
        producer="saiwiki",
        role_revision=role_revision,
        base_source_head=identity.source_head,
        base_source_tree_fingerprint=identity.source_tree_fingerprint,
        base_discovery_model=identity.discovery_model,
        scope=(
            "wiki-0.0.2a3-checkout-D066: SAIMAIL wiki rebuilt from the current "
            "tree (README, spec D-001..D-066, modules B-001..B-019 plus the "
            "S2/SAITELEME/outbox/participants/capabilities/notify checkout "
            "surface and the D-066 correspondence, keyvault, host-contract and "
            "agent-cycle surface) by the adopted saiwiki producer"
        ),
        read_set=producer_api.read_set_from(ROOT, read_paths),
        write_set=producer_api.write_set_before(ROOT, write_paths),
        epoch=epoch,
        status="ready",
    )
    generation = producer_api.StagingGeneration(namespace, "saiwiki").begin()
    for rel_path in write_paths:
        generation.add_payload(rel_path, (ROOT / rel_path).read_bytes())
    generation.set_package(package)
    result = generation.publish()
    if not result.get("ok"):
        raise RuntimeError(json.dumps(result, sort_keys=True))
    print(
        json.dumps(
            {
                "epoch": epoch,
                "package_identity": package.package_identity,
                "payload_count": len(write_paths),
                "publish": result,
                "read_count": len(read_paths),
                "role_revision": role_revision,
                "source_head": identity.source_head,
                "source_tree_fingerprint": identity.source_tree_fingerprint,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
