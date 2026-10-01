"""spec/35 GUI regression: the mailbox view must not learn to shout.

The operator-interruption gate landed in the transport and receiver layers, and
this file is the check that the presentation layer stayed out of the argument.
Two things must hold:

* the mailbox adapter keeps working exactly as before -- five letters from one
  Work are five rows, not five interruptions, and there is no badge, popup or
  "opened this visit" bucket that could turn into a dumping ground;
* the one thing that may be shown as an operator interruption is decided by
  admission state, so two envelopes whose prose shout at different volumes are
  treated identically when their admission state matches.

No prose is ever read to classify. That is asserted by behaviour, not by
reading the module: two opposite-prose fixtures with equal admission state
must produce equal operator surfaces.
"""

from __future__ import annotations

import pytest

from saimail import gui_adapter as adapter
from saimail import operator_interrupt as oi
from saimail import workspace

QUIET = "Ticket T-154 finished; 218 tests pass."
LOUD = "URGENT!!! CRITICAL!!! HARD STOP!!! READ NOW!!!"

HARD_STOP = "SAIMASTER hard stopped.\nNeeded: resolve the SAIT-001 blocker."
# `--claim` is single-line by contract, so the undeclared-mail case uses the same
# hard stop flattened. The gate is the declaration, never the wording.
ONE_LINE_STOP = "SAIMASTER hard stopped; resolve the SAIT-001 blocker."


@pytest.fixture
def pair(tmp_path):
    a_root, b_root = tmp_path / "ws-a", tmp_path / "ws-b"
    workspace.init_workspace(a_root, seat="SAIMAIL-A")
    workspace.init_workspace(b_root, seat="SAIMAIL-B")
    a = workspace.load_workspace(a_root)
    b = workspace.load_workspace(b_root)
    workspace.add_recipient(a, "bob", workspace.identity_card(b), b_root)
    workspace.add_recipient(b, "alice", workspace.identity_card(a), a_root)
    return {"a": a, "b": b, "a_root": a_root, "b_root": b_root}


def _send(site, claim, **kwargs):
    return workspace.send_message(site["a"], "bob", claim=claim, topic="T-154", **kwargs)


def _declare(site, claim, **kwargs):
    record = oi.declaration_record(seat=site["a"].seat,
                                   class_name=oi.OPERATOR_ACTION_REQUIRED,
                                   decision_id=kwargs.pop("decision_id", "sait-001"),
                                   work="T-154", body=claim, **kwargs)
    path = site["a_root"].parent / f"{record.content_id.split(':')[1][:12]}.sail"
    path.write_bytes(record.canonical_bytes())
    return workspace.send_message(site["a"], "bob", record_path=path,
                                  subject="T-154", topic="T-154")


# --------------------------------------------------------------------------
# the mailbox view is unchanged
# --------------------------------------------------------------------------

def test_five_letters_are_five_rows_and_one_interruption_slot(pair, tmp_path):
    """The live incident, seen from the presentation layer.

    Every letter is durable mail and shows up in the mailbox. Only the admitted
    one may consume operator attention, and it may consume exactly one slot.
    """
    for body in ("retirement command refused; try quarantine",
                 "style_contract appears unfixable",
                 "correction: write ded-71fc58de",
                 "retract correction: do not write ded-71fc58de"):
        _declare(pair, body, settled=False)
    final = _declare(pair, HARD_STOP)

    surface = adapter.GuiAdapter()
    opened = surface.open_workspace(pair["b_root"])
    assert opened["ok"] is True
    surface.refresh()
    assert len(surface.page.items) == 5
    assert surface.state == adapter.WORKSPACE_LOADED

    recv = oi.Receiver(pair["b_root"],
                       to_human=oi.human_id(workspace.load_workspace_headers(pair["b_root"])))
    for row in surface.page.items:
        opened_message = workspace.open_message(
            workspace.load_workspace(pair["b_root"]), row["envelope_id"])
        declared = oi.parse_declaration(opened_message["record"])
        if declared is not None:
            recv.admit(row["envelope_id"], declared)

    state = recv.status()
    assert state["operator_unread"] == 0
    assert len(state["pending"]) == 1
    assert state["pending"][0]["envelope_id"] == final["message"]["envelope_id"]

    reserved = recv.reserve()
    assert reserved["status"] == "RESERVED"
    assert recv.acknowledge(reserved["reservation_id"])["status"] == oi.PRESENTED
    assert recv.status()["operator_unread"] == 1


def test_the_mailbox_view_grows_no_operator_specific_state(pair):
    """No badge, no popup bucket, no visit-local pile: the view is the mailbox."""
    for body in (QUIET, LOUD):
        _send(pair, body)
    surface = adapter.GuiAdapter()
    surface.open_workspace(pair["b_root"])
    surface.refresh()

    # Every unread message is ordinary correspondence, listed once, in order.
    assert [item["envelope_id"] for item in surface.page.items] == \
        [item["envelope_id"] for item in sorted(surface.page.items,
                                               key=lambda i: i["received_at"])]
    assert sum(1 for i in surface.page.items if i["state"] == "UNREAD") == 2
    # No attribute anywhere on the surface for an operator-interruption count;
    # adding one is the change this spec has to justify, not a default.
    assert not [name for name in dir(surface)
                if "interrupt" in name.lower() or "badge" in name.lower()]


def test_opening_one_letter_exposes_the_record_and_nothing_else(pair):
    """Open stays explicit: no content before the operator asks for it."""
    sent = _send(pair, LOUD)
    surface = adapter.GuiAdapter()
    surface.open_workspace(pair["b_root"])
    surface.refresh()
    target = next(i for i in surface.page.items
                  if i["envelope_id"] == sent["message"]["envelope_id"])
    surface.select(target["envelope_id"])
    assert surface.content_visible is False
    assert surface.state in (adapter.MESSAGE_SELECTED_UNREAD, adapter.MESSAGE_SELECTED_READ)

    surface.open_selected()
    assert surface.content_visible is True
    assert surface.content()["claim"] == LOUD
    assert surface.state == adapter.MESSAGE_OPENED_CURRENT_SESSION

    # The reopened body is the record's, not a rewritten operator summary.
    recv = oi.Receiver(pair["b_root"],
                       to_human=oi.human_id(workspace.load_workspace_headers(pair["b_root"])))
    assert recv.status()["operator_unread"] == 0
    assert recv.status()["pending"] == []


# --------------------------------------------------------------------------
# classification comes from admission state, never from prose
# --------------------------------------------------------------------------

def test_shrill_prose_without_admission_is_not_an_interruption(pair):
    """The loudest letter in the mailbox, admitted by nobody, interrupts nobody."""
    loud = _declare(pair, LOUD)
    recv = oi.Receiver(pair["b_root"],
                       to_human=oi.human_id(workspace.load_workspace_headers(pair["b_root"])))
    opened = workspace.open_message(workspace.load_workspace(pair["b_root"]),
                                    loud["message"]["envelope_id"])
    declared = oi.parse_declaration(opened["record"])
    assert declared is not None, "the loud letter did carry a declaration"
    assert recv.admit(loud["message"]["envelope_id"], declared)["status"] == oi.ADMITTED

    quiet = _declare(pair, QUIET, decision_id="sait-002")
    opened_quiet = workspace.open_message(workspace.load_workspace(pair["b_root"]),
                                          quiet["message"]["envelope_id"])
    recv.admit(quiet["message"]["envelope_id"],
               oi.parse_declaration(opened_quiet["record"]))

    # Both are admitted candidates; the budget, not the volume, decides.
    assert len(recv.status()["pending"]) == 2
    presented = recv.reserve()
    assert presented["status"] == "RESERVED"
    recv.acknowledge(presented["reservation_id"])
    assert recv.status()["operator_unread"] == 1


def test_equal_admission_state_gives_equal_operator_surfaces(pair, tmp_path):
    """Two envelopes, opposite prose, identical admission state, one outcome."""
    outcomes = []
    for index, body in enumerate((QUIET, LOUD)):
        root = tmp_path / f"pair-{index}"
        root.mkdir()
        local = {
            "a": workspace.init_workspace(root / "ws-a", seat="SAIMAIL-A") and
                  workspace.load_workspace(root / "ws-a"),
            "b": workspace.init_workspace(root / "ws-b", seat="SAIMAIL-B") and
                  workspace.load_workspace(root / "ws-b"),
            "a_root": root / "ws-a", "b_root": root / "ws-b",
        }
        workspace.add_recipient(local["a"], "bob",
                                workspace.identity_card(local["b"]), local["b_root"])
        workspace.add_recipient(local["b"], "alice",
                                workspace.identity_card(local["a"]), local["a_root"])
        sent = _declare(local, body)
        recv = oi.Receiver(local["b_root"],
                           to_human=oi.human_id(
                               workspace.load_workspace_headers(local["b_root"])))
        opened = workspace.open_message(workspace.load_workspace(local["b_root"]),
                                        sent["message"]["envelope_id"])
        admit = recv.admit(sent["message"]["envelope_id"],
                           oi.parse_declaration(opened["record"]))
        reserved = recv.reserve()
        shown = recv.acknowledge(reserved["reservation_id"])
        outcomes.append((admit["status"], shown["status"], shown["body"]))

    assert outcomes[0][0] == outcomes[1][0] == oi.ADMITTED
    assert outcomes[0][1] == outcomes[1][1] == oi.PRESENTED
    # The body each carries is its own, verbatim and never silently merged,
    # swapped or shortened: the surface shows what the sender asked to show.
    assert [o[2] for o in outcomes] == [QUIET, LOUD]


def test_a_letter_never_admitted_never_reaches_the_operator_surface(pair):
    """The GUI has no path that promotes mail on its own authority."""
    _send(pair, ONE_LINE_STOP)
    surface = adapter.GuiAdapter()
    surface.open_workspace(pair["b_root"])
    surface.refresh()
    recv = oi.Receiver(pair["b_root"],
                       to_human=oi.human_id(workspace.load_workspace_headers(pair["b_root"])))
    assert recv.status()["pending"] == []
    assert recv.status()["presented"] == []
    assert recv.status()["operator_unread"] == 0
    # The mailbox still has it: undiscoverable mail would be a bug, not safety.
    assert sum(1 for i in surface.page.items if i["state"] == "UNREAD") == 1
