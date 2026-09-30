"""saitranslate producer publish for the SAIMAIL project.

Adapted from the adopted saiwiki producer's kitchen/_publish_package.py (same
engine API). Reads the canonical sources the translations were made from
(README.md + VERSION for the digest normalization), binds the package to the
current source identity and the current charter role revision, stages the two
full README locale translations (ja, uk), and publishes one READY package
with a complete (32-language) coverage statement per phases/translate.md.

Touches only .saipen/saitranslate/kitchen/. Never the main tree, no
integration, commit, tag, push or remote write.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, r"V:\___VAC\__K\__CODE\_AI_STUFF_AGENTIC\_SAIPEN\tools")

from freshness import compute_role_revision, compute_source_identity  # noqa: E402
from saipen_engine import producer as producer_api  # noqa: E402


def main() -> None:
    namespace = ROOT / ".saipen" / "saitranslate"
    kitchen = namespace / "kitchen"
    charter = ROOT / ".saipen" / "extensions" / "subs" / "saitranslate.md"
    identity = compute_source_identity(ROOT)
    role_revision = compute_role_revision(charter)

    page_names = [
        "README.ja.md",
        "README.uk.md",
    ]
    write_paths = [
        (kitchen / name).relative_to(ROOT).as_posix() for name in page_names
    ]
    read_paths = [
        "README.md",
        "VERSION",
    ]
    absent = [path for path in read_paths if not (ROOT / path).is_file()]
    if absent:
        raise RuntimeError(f"missing read dependencies: {absent}")

    epoch = producer_api.ProducerEpoch.claim(namespace)
    package = producer_api.build_package(
        producer="saitranslate",
        role_revision=role_revision,
        base_source_head=identity.source_head,
        base_source_tree_fingerprint=identity.source_tree_fingerprint,
        base_discovery_model=identity.discovery_model,
        scope=(
            "saitranslate-v0.0.1-readme-mirrors-ja-uk: complete README "
            "translations for the two producer-owned locales (ja, uk) against "
            "the current tree; Core-owned EN/RU/EE/DED untouched; no real "
            "UI-string surface exists in this project (phases/translate.md)"
        ),
        read_set=producer_api.read_set_from(ROOT, read_paths),
        write_set=producer_api.write_set_before(ROOT, write_paths),
        epoch=epoch,
        status="ready",
    )
    generation = producer_api.StagingGeneration(namespace, "saitranslate").begin()
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
