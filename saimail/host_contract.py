"""Dependency-free version negotiation for hosts maintained independently."""

SCHEMA = "SAIMAIL_HOST_CONTRACT_1"


def contract():
    """Static protocol description; available without a mailbox or crypto extra."""
    return {
        "schema": SCHEMA,
        "version": 1,
        "command_schema": "LOCAL_WORKSPACE_COMMAND_1",
        "letter_schema": "SAIMAIL_LETTER_1",
        "capabilities_schema": "SAIMAIL_CAPABILITIES_1",
        "features": {"correspondence": 1, "receiver_decisions": 1, "successor_reserve": 1,
                     "durable_outbox": 1, "keyless_desk": 1, "receiver_feedback": 1, "reason_metrics": 1,
                     "agent_cycle": 1, "feedback_signal_age": 1, "cli_focus": 1, "feedback_origin": 1},
        "commands": {
            "health": ["saipen", "capabilities"],
            "awareness": ["saipen", "letter", "desk"],
            "dispatch": ["saipen", "letter", "dispatch"],
            "review": ["saipen", "letter", "review"],
            "decision": ["saipen", "letter", "decide"],
            "retain": ["saipen", "letter", "retain"],
            "report": ["saipen", "letter", "report"],
            "metrics": ["saipen", "letter", "metrics"],
            "cycle": ["saipen", "letter", "cycle"],
            "focus": ["saipen", "letter", "focus"],
        },
        "common_arguments": ["--workspace", "--project-root", "--seat", "--json"],
        "compatibility": {"unknown_fields": "IGNORE", "unknown_major_schema": "DEGRADED",
                          "unknown_status": "DEGRADED", "missing_feature": "DEGRADED",
                          "legacy_commands": "PRESERVED", "shell_execution": False},
        # The block above is a FROZEN intent map: `health` names what a host is
        # trying to do, not which verb does it, so it cannot be derived from the
        # parser and must not try to be. The live inventory is a separate,
        # generated document and lives behind this pointer -- additive, so a host
        # written against the frozen map keeps working and simply ignores it.
        "live_surface": {
            "schema": "SAIMAIL_CLI_MAP_1",
            "generated_by": "saimail.surface.cli_map",
            "authority": "INFORMATION_ONLY",
            "note": "walked from the registered argparse tree; adding or removing a "
                    "verb changes this document with no second edit",
        },
        "authority": "INFORMATION_ONLY",
        "attention": "RECEIVER_OWNED",
        "execution": "EXPLICIT_HOST_DECISION",
    }


__all__ = ["SCHEMA", "contract"]
