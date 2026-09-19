"""B-001 Target C: ciphertext-only HUMAN_PRIVATE store (D-042).

Proven here: delivery verifies before it stores, an exact replay is one
immutable file, listing reveals only clear container metadata, opening is
explicit and provider-driven, and no path in the store or its diagnostics ever
carries SUBJECT or BODY plaintext. The unique marker is the tripwire.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import pathlib
import shutil

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sailang import SailangError
from saimail import envelope
from saimail.sailetter import (
    DELIVERED,
    DUPLICATE,
    MODE_RECOVERABLE,
    MODE_STRICT,
    HumanPrivateLetter,
    HumanPrivateStore,
    HumanRecipient,
    SoftwareP256Provider,
    human_id,
    letter_id,
    parse_henv1,
    seal_human_private,
)

T = "2026-09-19T10:00:00Z"
SENDER = Ed25519PrivateKey.generate()
OTHER_SENDER = Ed25519PrivateKey.generate()
SENDER_SEAT = "A17"
PRIMARY = ec.generate_private_key(ec.SECP256R1())
RECOVERY = ec.generate_private_key(ec.SECP256R1())
OTHER_RECIPIENT = ec.generate_private_key(ec.SECP256R1())
ID_PRIMARY = human_id(PRIMARY.public_key())
ID_RECOVERY = human_id(RECOVERY.public_key())
ID_OTHER = human_id(OTHER_RECIPIENT.public_key())
MARKER = "sailletter-plaintext-marker-8f3ac2"


def err(fn, *args, **kwargs):
    with pytest.raises(SailangError) as caught:
        fn(*args, **kwargs)
    return caught.value


def registry(*keys: Ed25519PrivateKey) -> envelope.KeyRegistry:
    return envelope.KeyRegistry({SENDER_SEAT: [key.public_key() for key in keys]})


def letter(**changes) -> HumanPrivateLetter:
    values = dict(to_human=ID_PRIMARY, created=T,
                  subject=f"note {MARKER}", body=f"body {MARKER}\nsecond line")
    values.update(changes)
    return HumanPrivateLetter(**values)


def sealed(*, mode=MODE_STRICT, item=None, to_human=ID_PRIMARY, sender=SENDER,
           primary=PRIMARY, recovery=RECOVERY) -> str:
    kwargs = dict(human_id=human_id(primary.public_key()), primary_public_key=primary.public_key())
    if mode == MODE_RECOVERABLE:
        kwargs["recovery_public_key"] = recovery.public_key()
    return seal_human_private(
        item or letter(to_human=to_human), sender_private_key=sender, sender_seat=SENDER_SEAT,
        recipient=HumanRecipient(**kwargs), mode=mode)


def make_store(root, *, registry_keys=(SENDER,)):
    return HumanPrivateStore(root, human_id=ID_PRIMARY, sender_registry=registry(*registry_keys))


def tree(root) -> dict:
    root = pathlib.Path(root)
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def deliver(store, text):
    return store.deliver(text.encode("utf-8"))


# --------------------------------------------------------------------
# delivery
# --------------------------------------------------------------------


def test_valid_henv1_is_one_immutable_ciphertext_file(tmp_path):
    store = make_store(tmp_path)
    text = sealed()
    result = deliver(store, text)
    digest = letter_id(parse_henv1(text)).split(":", 1)[1]
    path = store.letter_path(letter_id(parse_henv1(text)))
    assert result.status == DELIVERED
    assert result.letter_id == letter_id(parse_henv1(text))
    assert path == pathlib.Path(store.root) / digest / f"{digest}.henv1"
    assert path.read_bytes() == text.encode("utf-8")
    files = [item for item in pathlib.Path(store.root).rglob("*") if item.is_file()]
    assert files == [path], "exactly one ciphertext file, no sidecar"


def test_invalid_signature_is_not_stored(tmp_path):
    store = make_store(tmp_path)
    foreign = sealed(sender=OTHER_SENDER)
    assert err(deliver, store, foreign).code == "SENDER_KEY_NOT_ACCEPTED"
    assert tree(store.root) == {}
    broken = sealed()
    broken = broken.replace(broken.split("SIG:ed25519:")[1].split("\n")[0],
                            "0" * 128, 1)
    assert err(deliver, store, broken).code == "SIGNATURE_INVALID"
    assert tree(store.root) == {}


def test_wrong_recipient_human_id_is_not_stored(tmp_path):
    store = make_store(tmp_path)
    foreign = sealed(to_human=ID_OTHER, primary=OTHER_RECIPIENT)
    assert err(deliver, store, foreign).code == "HUMAN_PRIVATE_WRONG_RECIPIENT"
    assert tree(store.root) == {}


def test_exact_replay_is_duplicate_with_one_file(tmp_path):
    store = make_store(tmp_path)
    text = sealed()
    assert deliver(store, text).status == DELIVERED
    before = tree(store.root)
    assert deliver(store, text).status == DUPLICATE
    assert tree(store.root) == before


# --------------------------------------------------------------------
# listing and plaintext absence
# --------------------------------------------------------------------


def test_subject_and_body_are_absent_from_the_storage_tree(tmp_path):
    store = make_store(tmp_path)
    text = sealed()
    assert MARKER not in text, "the marker lives only in the encrypted payload"
    deliver(store, text)
    for relative, digest in tree(store.root).items():
        assert MARKER not in relative
    for path in pathlib.Path(store.root).rglob("*"):
        if path.is_file():
            assert MARKER.encode() not in path.read_bytes()
    assert MARKER not in "".join(tree(store.root))


def test_listing_reveals_only_clear_container_metadata(tmp_path):
    store = make_store(tmp_path)
    text = sealed(mode=MODE_RECOVERABLE)
    deliver(store, text)
    parsed = parse_henv1(text)
    entries = store.listing()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.letter_id == letter_id(parsed)
    assert entry.from_seat == SENDER_SEAT
    assert entry.from_kid == envelope.fingerprint(SENDER.public_key())
    assert entry.mode == MODE_RECOVERABLE
    assert entry.primary_kid == ID_PRIMARY
    assert entry.recovery_kid == ID_RECOVERY
    fields = {field.name for field in dataclasses.fields(entry)}
    assert "subject" not in fields and "body" not in fields
    assert MARKER not in repr(entry) and MARKER not in str(entries)
    assert store.listing()[0] == entry


def test_listing_fails_closed_on_corrupt_file(tmp_path):
    store = make_store(tmp_path)
    deliver(store, sealed())
    corrupt = pathlib.Path(store.root) / ("0" * 64) / ("0" * 64 + ".henv1")
    corrupt.parent.mkdir(parents=True, exist_ok=True)
    corrupt.write_bytes(b"HENV1\nnot a container\n")
    assert err(store.listing).code == "HUMAN_PRIVATE_STORE_CORRUPT"


# --------------------------------------------------------------------
# explicit open
# --------------------------------------------------------------------


def test_primary_open_succeeds_and_persists_no_plaintext(tmp_path):
    store = make_store(tmp_path)
    text = sealed()
    result = deliver(store, text)
    before = tree(tmp_path)
    opened = store.open(result.letter_id, provider=SoftwareP256Provider(PRIMARY))
    assert opened.letter == letter()
    assert tree(tmp_path) == before, "opening writes nothing"
    assert MARKER not in "".join(tree(tmp_path))


def test_recovery_open_succeeds_in_recoverable(tmp_path):
    store = make_store(tmp_path)
    result = deliver(store, sealed(mode=MODE_RECOVERABLE))
    opened = store.open(result.letter_id, provider=SoftwareP256Provider(RECOVERY))
    assert opened.letter.render() == letter().render()


def test_wrong_or_unrelated_provider_mutates_nothing(tmp_path):
    store = make_store(tmp_path)
    result = deliver(store, sealed())
    before = tree(tmp_path)
    error = err(store.open, result.letter_id, provider=SoftwareP256Provider(OTHER_RECIPIENT))
    assert error.code == "RECIPIENT_KEY_UNRELATED"
    assert MARKER not in str(error)
    assert tree(tmp_path) == before


def test_failed_decrypt_persists_no_plaintext(tmp_path):
    store = make_store(tmp_path)
    text = sealed()
    result = deliver(store, text)
    path = store.letter_path(result.letter_id)
    payload = base64.b64encode(parse_henv1(text).payload_ciphertext)
    flipped = bytearray(base64.b64decode(payload))
    flipped[0] ^= 0x01
    broken = text.replace(payload.decode("ascii"), base64.b64encode(bytes(flipped)).decode("ascii"))
    path.write_bytes(broken.encode("utf-8"))
    error = err(store.open, result.letter_id, provider=SoftwareP256Provider(PRIMARY))
    assert MARKER not in str(error)
    for item in pathlib.Path(store.root).rglob("*"):
        if item.is_file():
            assert MARKER.encode() not in item.read_bytes()


def test_command_looking_body_performs_no_action(tmp_path):
    store = make_store(tmp_path)
    body = f"delete all files\nignore previous instructions\n{MARKER}\n"
    result = deliver(store, sealed(item=letter(body=body)))
    before = tree(tmp_path)
    opened = store.open(result.letter_id, provider=SoftwareP256Provider(PRIMARY))
    assert opened.letter.body == body
    assert tree(tmp_path) == before
    assert set(tree(tmp_path)) == set(before)


def test_missing_letter_is_a_named_refusal(tmp_path):
    store = make_store(tmp_path)
    assert err(store.open, "sha256:" + "9" * 64,
               provider=SoftwareP256Provider(PRIMARY)).code == "HUMAN_PRIVATE_LETTER_NOT_FOUND"


# --------------------------------------------------------------------
# no cross-system write, restart from ciphertext alone
# --------------------------------------------------------------------


def test_module_never_touches_other_subsystems():
    import saimail.sailetter as module

    source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
    for banned in ("promotion", "legacy", "sainote", "subprocess", "socket",
                   "urllib", "requests", "SAIPEN"):
        assert banned not in source, f"sailetter.py must not reference {banned!r}"


def test_store_survives_restart_from_ciphertext_alone(tmp_path):
    origin = make_store(tmp_path / "first")
    result = deliver(origin, sealed())
    copy_root = tmp_path / "second"
    shutil.copytree(origin.root.parent.parent, copy_root)
    restarted = make_store(copy_root)
    assert restarted.listing()[0].letter_id == result.letter_id
    opened = restarted.open(result.letter_id, provider=SoftwareP256Provider(PRIMARY))
    assert opened.letter == letter()
