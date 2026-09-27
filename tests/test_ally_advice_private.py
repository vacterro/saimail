"""ALLY1 -> HLET1 -> HENV1 and explicit receiver-attention integration."""

import hashlib
import inspect
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sailang.errors import SailangError
from saimail import ally_advice as aa
from saimail import envelope
from saimail import human_attention as ha
from saimail.sailetter import (
    MODE_STRICT,
    HumanPrivateLetter,
    HumanPrivateStore,
    HumanRecipient,
    SoftwareP256Provider,
    human_id,
    seal_human_private,
)

CREATED = "2026-09-19T19:00:00Z"
SENDER_SEAT = "ALLY_AGENT"
SENDER = Ed25519PrivateKey.generate()
PRIMARY = ec.generate_private_key(ec.SECP256R1())
HUMAN = human_id(PRIMARY.public_key())
MARKERS = {
    "observed": "observed-private-marker-2d2214",
    "inferred": "inferred-private-marker-8fd22d",
    "counter": "counter-private-marker-a18b91",
}


def ref(tag):
    return "sha256:" + hashlib.sha256(tag.encode()).hexdigest()


def refs(*tags):
    return tuple(sorted(ref(tag) for tag in tags))


def advice(**changes):
    values = {
        "created": CREATED,
        "work_context": "Private architecture work.",
        "observed_scope": "Three explicit receiver decisions.",
        "observed": (
            aa.AdviceObservation(MARKERS["observed"] + " first", refs("o1", "o2")),
            aa.AdviceObservation("CRITICAL_RECOVERY appears only as sender prose", refs("o3")),
        ),
        "inferred": MARKERS["inferred"] + " may describe premature convergence.",
        "guidance_mode": aa.CONSIDER_CHANGE,
        "suggested": "Consider one reversible falsification pass.",
        "counterevidence": (
            aa.AdviceCounterevidence(MARKERS["counter"] + " later work self-corrected.",
                                     refs("c1")),
        ),
        "uncertainty": "This small sample may be deadline-specific.",
    }
    values.update(changes)
    return aa.AllyAdvice(**values)


class Resolver:
    def __init__(self, existing):
        self.existing = set(existing)

    def resolve(self, evidence_ref):
        return aa.EXISTS if evidence_ref in self.existing else aa.MISSING


class MutableClock:
    def __init__(self, value=CREATED):
        self.value = value

    def __call__(self):
        return self.value


def all_refs(item):
    return {
        ref for part in (*item.observed, *item.counterevidence)
        for ref in part.evidence_refs
    }


def resolved(item=None):
    item = item or advice()
    return aa.resolve_ally_evidence(item, Resolver(all_refs(item)))


def registry():
    return envelope.KeyRegistry({SENDER_SEAT: [SENDER.public_key()]})


def recipient():
    return HumanRecipient(human_id=HUMAN, primary_public_key=PRIMARY.public_key())


def error(fn, *args, **kwargs):
    with pytest.raises(SailangError) as caught:
        fn(*args, **kwargs)
    return caught.value


def tree(root):
    root = Path(root)
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def test_official_adapter_requires_resolved_type_and_uses_exact_ally1_body():
    raw = advice()
    assert error(aa.ally_to_human_private, raw,
                 recipient_human_id=HUMAN).code == aa.ALLY_EVIDENCE_RESOLUTION_REQUIRED
    letter = aa.ally_to_human_private(resolved(raw), recipient_human_id=HUMAN)
    assert letter.to_human == HUMAN
    assert letter.created == raw.created
    assert letter.subject == aa.ALLY_ADVICE_SUBJECT
    assert letter.body.encode() == raw.render()


def test_sealed_henv1_exposes_no_advice_type_or_private_prose():
    item = advice()
    letter = aa.ally_to_human_private(resolved(item), recipient_human_id=HUMAN)
    sealed = seal_human_private(
        letter, sender_private_key=SENDER, sender_seat=SENDER_SEAT,
        recipient=recipient(), mode=MODE_STRICT)
    for marker in (*MARKERS.values(), aa.ALLY_ADVICE_SUBJECT, "ALLY1"):
        assert marker not in sealed


def test_human_private_store_persists_one_ciphertext_and_no_ally_plaintext(tmp_path):
    item = advice()
    letter = aa.ally_to_human_private(resolved(item), recipient_human_id=HUMAN)
    sealed = seal_human_private(
        letter, sender_private_key=SENDER, sender_seat=SENDER_SEAT,
        recipient=recipient(), mode=MODE_STRICT)
    store = HumanPrivateStore(tmp_path, human_id=HUMAN, sender_registry=registry())
    delivery = store.deliver(sealed.encode())
    files = tree(tmp_path)
    assert list(files) == [
        str(store.letter_path(delivery.letter_id).relative_to(tmp_path))]
    for data in files.values():
        for marker in MARKERS.values():
            assert marker.encode() not in data
        assert b"ALLY1" not in data
    assert not hasattr(aa, "AllyAdviceStore")


def test_construct_resolve_seal_and_store_never_auto_admit_attention(tmp_path):
    attention_root = tmp_path / "attention"
    queue = ha.AttentionQueue(attention_root, human_id=HUMAN, clock=MutableClock())
    item = advice()
    proof = resolved(item)
    letter = aa.ally_to_human_private(proof, recipient_human_id=HUMAN)
    sealed = seal_human_private(
        letter, sender_private_key=SENDER, sender_seat=SENDER_SEAT,
        recipient=recipient(), mode=MODE_STRICT)
    store = HumanPrivateStore(tmp_path / "mail", human_id=HUMAN, sender_registry=registry())
    store.deliver(sealed)
    state = queue.budget_state()
    assert state.pending_candidates == 0
    assert state.consumed == 0
    assert queue.reserve_next().status == ha.NO_MESSAGE


def test_zero_personal_letter_is_complete_no_output(tmp_path):
    item = advice()
    missing = Resolver(all_refs(item) - {ref("c1")})
    assert error(aa.resolve_ally_evidence, item, missing).code == aa.ALLY_EVIDENCE_MISSING
    assert tree(tmp_path) == {}
    queue = ha.AttentionQueue(tmp_path / "attention", human_id=HUMAN, clock=MutableClock())
    assert queue.reserve_next().status == ha.NO_MESSAGE
    assert queue.budget_state().consumed == 0


def test_explicit_open_requires_expected_subject_and_recipient(tmp_path):
    item = advice()
    store = HumanPrivateStore(tmp_path, human_id=HUMAN, sender_registry=registry())
    letter = aa.ally_to_human_private(resolved(item), recipient_human_id=HUMAN)
    sealed = seal_human_private(
        letter, sender_private_key=SENDER, sender_seat=SENDER_SEAT,
        recipient=recipient(), mode=MODE_STRICT)
    delivery = store.deliver(sealed)
    opened = store.open(delivery.letter_id, provider=SoftwareP256Provider(PRIMARY))
    assert aa.open_ally_advice(opened, recipient_human_id=HUMAN) == item
    other = "human-id:sha256:" + "f" * 64
    assert error(aa.open_ally_advice, opened,
                 recipient_human_id=other).code == aa.ALLY_WRONG_RECIPIENT

    generic = HumanPrivateLetter(
        to_human=HUMAN, created=CREATED, subject="OTHER", body=item.render().decode())
    generic_sealed = seal_human_private(
        generic, sender_private_key=SENDER, sender_seat=SENDER_SEAT,
        recipient=recipient(), mode=MODE_STRICT)
    generic_delivery = store.deliver(generic_sealed)
    generic_opened = store.open(
        generic_delivery.letter_id, provider=SoftwareP256Provider(PRIMARY))
    assert error(aa.open_ally_advice, generic_opened,
                 recipient_human_id=HUMAN).code == aa.ALLY_WRONG_SUBJECT


def test_private_open_helper_refuses_unopened_plaintext():
    letter = aa.ally_to_human_private(resolved(), recipient_human_id=HUMAN)
    assert error(aa.open_ally_advice, letter,
                 recipient_human_id=HUMAN).code == aa.ALLY_PRIVATE_OPEN_REQUIRED


def test_full_explicit_private_advice_attention_path(tmp_path):
    item = advice()

    # Construct -> resolve -> HLET1 -> HENV1 -> ciphertext store.
    proof = resolved(item)
    letter = aa.ally_to_human_private(proof, recipient_human_id=HUMAN)
    sealed = seal_human_private(
        letter, sender_private_key=SENDER, sender_seat=SENDER_SEAT,
        recipient=recipient(), mode=MODE_STRICT)
    store = HumanPrivateStore(tmp_path / "mail", human_id=HUMAN, sender_registry=registry())
    delivery = store.deliver(sealed)

    # Nothing above touched receiver attention. Admission is a separate act.
    clock = MutableClock()
    queue = ha.AttentionQueue(
        tmp_path / "attention", human_id=HUMAN, clock=clock,
        budget=ha.AttentionBudget(max_presentations=1, period_seconds=86_400))
    assert queue.reserve_next().status == ha.NO_MESSAGE
    admitted = queue.admit_receiver_candidate(
        source_kind=ha.HUMAN_PRIVATE,
        source_ref=delivery.letter_id,
        allocation="IDLE_REPORT",
        deferral_policy="QUEUE_AND_CONTINUE",
    )
    assert admitted.candidate.source_kind == ha.HUMAN_PRIVATE
    assert admitted.candidate.source_ref == delivery.letter_id
    assert admitted.candidate.allocation == "IDLE_REPORT"
    assert "CRITICAL_RECOVERY" not in admitted.candidate.render().decode()
    reservation = queue.reserve_next().reservation
    clock.value = "2026-09-19T19:00:10Z"
    queue.ack_presented(reservation.reservation_id)

    # Presentation is not open or acceptance. Recipient decrypt/open is explicit.
    before_open = tree(tmp_path)
    opened_letter = store.open(
        delivery.letter_id, provider=SoftwareP256Provider(PRIMARY))
    opened_advice = aa.open_ally_advice(opened_letter, recipient_human_id=HUMAN)
    assert tree(tmp_path) == before_open
    assert opened_advice == item
    assert opened_advice.observed == item.observed
    assert opened_advice.counterevidence == item.counterevidence
    assert opened_advice.inference_status == aa.INFERENCE_STATUS
    assert opened_advice.guidance_status == aa.GUIDANCE_STATUS
    assert opened_advice.agency == aa.AGENCY
    assert queue.budget_state().consumed == 1


def test_scheduler_boundary_has_no_decrypt_provider_or_advice_dependency(tmp_path):
    queue = ha.AttentionQueue(tmp_path, human_id=HUMAN, clock=MutableClock())
    queue.admit_receiver_candidate(
        source_kind=ha.HUMAN_PRIVATE,
        source_ref=ref("letter"),
        allocation="ROUTINE_AUDIT",
        deferral_policy="QUEUE_AND_CONTINUE",
    )
    selected = queue.reserve_next()
    assert selected.status == ha.RESERVED
    source = inspect.getsource(ha)
    for forbidden in ("ally_advice", "decrypt", "SoftwareP256Provider", "PivP256Provider", "PIN"):
        assert forbidden not in source


def test_ally_module_has_no_store_attention_model_network_or_mutation_hooks():
    source = inspect.getsource(aa)
    for forbidden in (
        "AttentionQueue(", ".admit_receiver_candidate(", "class AllyAdviceStore",
        "import requests", "import urllib", "import socket", "import subprocess",
        "from .legacy", "import legacy", "from .promotion", "import promotion",
        "followed_advice =", "ignored_advice =", "helpfulness_score =",
        "open_rate =", "read_time =", "emotional_reaction =",
    ):
        assert forbidden not in source
    assert "HumanPrivateLetter" in source
    assert "OpenedHumanPrivateLetter" in source


def test_ally1_cannot_carry_receiver_allocation_or_deferral_fields():
    obj = json.loads(advice().render())
    assert set(obj).isdisjoint({"ALLOCATION", "DEFERRAL_POLICY", "PRIORITY"})
    obj["ALLOCATION"] = "CRITICAL_RECOVERY"
    wire = (json.dumps(obj, separators=(",", ":")) + "\n").encode()
    assert error(aa.AllyAdvice.parse, wire).code == aa.ALLY_UNKNOWN_FIELD
