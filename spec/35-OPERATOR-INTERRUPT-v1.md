# 35. Operator interruption (SAIMAIL_OPERATOR_INTERRUPT_1)

Status: normative. Version 1. Depends on spec/07 (human attention),
spec/17 (local workspace).

## The defect this spec exists to prevent

A live operator session received five SAIMAIL letters from one active Work in
forty-one minutes: a tentative repair, a correction, a correction of the
correction, a retraction, and finally a real hard stop. The README and
`saimail-local send --help` already forbade exactly this. The rule was prose and
the prose did not hold.

The failure had one cause: **sending a message and interrupting a human are two
different acts, and only the first one existed.** `_cmd_send()` called
`send_message()` directly. `correspondence.dispatch()` validated schema,
evidence, Work ownership and expiry, and none of those properties say anything
about whether a person should be interrupted. `notify.py` bounded a recipient to
20 messages per hour, which is a transport flood budget, not an attention
policy. The `human_attention` queue with its one-presentation-per-24-hours
default existed and was never on this path.

So this spec draws the line the code was missing:

> **A message existing does NOT imply the operator should be interrupted. A
> sender cannot declare its own prose important enough to bypass the receiver's
> attention policy.**

## 1. Two transport contracts, not one

| | Agent/Work transport | Human operator interruption |
|---|---|---|
| Gate | the existing SENV2 dispatch rules | this spec |
| Budget | `notify.py` flood budgets (20/hr per recipient, 5/hr per recipient+Work) | receiver-owned `human_attention.AttentionQueue`, 1 presentation per 24h by default |
| Effect | a durable, readable message | one operator-attention slot |
| Auditable outcome | `ACCEPTED` | `ADMITTED` then `PRESENTED` |

A durable message with no operator interruption is a **successful** outcome, not
a dropped one. `MESSAGE_DURABLY_EXISTS` and `OPERATOR_INTERRUPTION_PRESENTED`
are separate facts and are never conflated.

## 2. Eligibility: a closed class set, mechanically enforced

Exactly three classes may ever reach the operator's attention:

* `OPERATOR_ACTION_REQUIRED` — a hard stop only a human can lift;
* `DATA_OR_MONEY_RISK` — risk of losing data or money;
* `CROSS_PROJECT_CRITICAL_DISCOVERY` — a discovery that changes other projects.

Everything else is ordinary durable correspondence, and stays that way:
progress, ticket completion, test pass/fail when autonomous work can continue,
audit summaries, ordinary local findings, implementation detail, speculative
hypotheses, intermediate debugging conclusions, retractions and corrections while
an investigation is live, unproven commands, anything already said in the active
chat, "FYI", routine manual checks, reminders, and next-step suggestions the
agent can carry out itself.

Eligibility is decided from **declared metadata**, never from the text. A
surface that wants to know whether a message is an operator interruption reads
the receiver's admission state; it never reads prose and classifies.

## 3. The stability gate

An interruption must represent a **stable decision boundary**. A declaration
carries `settled: bool`:

* `settled=false` → result `UNSETTLED`. Never admitted, never presented. The
  message is durable mail and the investigation continues.
* `settled=true` → the sender asserts the diagnosis has stabilized.

A later correction for the same decision does not become a second interruption.
If a pending request becomes invalid, it is superseded rather than presented
alongside its own contradiction.

**If the investigation has not stabilized enough to identify one final operator
action, send zero operator interruptions.** Zero is the designed answer, not a
failure.

## 4. One decision = one interruption

Decision identity is a digest over `(receiver, work, decision_id)`:

```
decision_identity = "decision:" || sha256(DOMAIN ‖ to_human ‖ 0x00 ‖ work ‖ 0x00 ‖ decision_id)
```

`work` and `decision_id` are supplied by the sender; the receiver and the class
are not. `work` must match `T-[0-9]+` **in full** — a prefix match would let
`T-154-attempt-2` share an identity with `T-154`, so the check is
`fullmatch`, not `match`. `decision_id` is 1–96 characters of
`[A-Za-z0-9._-]` starting alphanumeric, and neither field may smuggle a
separator through it.

Therefore none of the following can buy a second interruption:

* changing the wording or the subject;
* changing the trigger;
* creating a new envelope for the same decision;
* retracting and resending;
* splitting one decision into several issues with different ids.

A changed diagnostic explanation **without** a changed required human decision
is the same decision. Exact retries are `DUPLICATE_DECISION` (idempotent, no new
unread letter); a newer envelope for a still-pending decision is `SUPERSEDED`
(the ledger pointer moves to the latest stable state); after presentation,
`ALREADY_PRESENTED` — and the remaining correspondence stays readable in the
mailbox.

The module's own ledger key is the attention queue's own
`attention_candidate_id(to_human, EXTERNAL_REFERENCE, decision_identity)`. The
two dedups are literally the same dedup, by construction rather than by
coincidence.

**Reclassification is a new decision, not a louder one.** If a decision already
in the ledger comes back carrying a different class, admission is refused with
`INTERRUPT_BAD_CLASS` *before* anything is written. Accepting it would either
leave the ledger and the queue disagreeing about the same candidate, or let a
sender escalate a decision in place and re-enter the ranking.

**A repeated JSON key is a refusal, not a last-wins merge.** The declaration is
parsed with an `object_pairs_hook` that raises `INTERRUPT_MALFORMED` on a
duplicate key, so a hand-built claim cannot present one value to the reader and
another to the validator.

## 4a. The pending set is bounded by a door, not a ranking

`MAX_PENDING_DECISIONS` is 8. At the cap the next arrival of **any** class is
refused with `PENDING_FULL`; the letter remains ordinary durable mail.

Nothing is ever evicted to make room, and that is deliberate. An admitted
decision owns a durable `human_attention` candidate, and the queue has no
retirement API — a candidate, once written, is served until it is presented. An
evicted decision would therefore leave the queue holding a candidate the
receiver no longer owns, and every later presentation would have to release the
slot and answer `NOTHING_PENDING` instead of showing anything. A bound that
strands the queue is worse than a full mailbox.

The refusal is checked **before** the enqueue, so a refused decision never
leaves a candidate behind.

## 4b. Crash ordering

Admission enqueues the queue candidate **first**, then writes the ledger entry.
The only residue a crash can leave is therefore a candidate with no ledger
entry, and `reserve()` already self-heals that case: it releases the slot and
answers `NOTHING_PENDING` rather than inventing a message. The reverse order
would leave a pending ledger entry that can never be presented and never clears.

## 5. The budget stays receiver-owned

The receiver reuses `saimail/human_attention.AttentionQueue`. **No second,
competing attention scheduler exists in this product.** Defaults: one presented
interruption per 86400 seconds, 300-second lease.

Presentation is two-phase, and only the second phase spends:

1. `reserve_next()` → a lease over the single slot;
2. `ack_presented(reservation_id)` → the slot is spent and the ledger entry
   becomes `PRESENTED`.

Reserving without acknowledging spends nothing; `release()` returns the lease
and the decision stays pending. Two concurrent presenters cannot both spend the
one slot: the second gets the queue's fail-closed answer.

Class → allocation/deferral mapping (the existing closed vocabularies):

| class | allocation | deferral policy |
|---|---|---|
| `DATA_OR_MONEY_RISK` | `CRITICAL_RECOVERY` | `ESCALATE_AND_HALT` |
| `OPERATOR_ACTION_REQUIRED` | `DECISION_REQUEST` | `BLOCK_UNTIL_HUMAN` |
| `CROSS_PROJECT_CRITICAL_DISCOVERY` | `AMBIGUITY_RESOLUTION` | `QUEUE_AND_CONTINUE` |

**Critical exception.** A new `DATA_OR_MONEY_RISK` may remain *pending* after
the budget is spent, and never arbitrarily sender-declared severity is allowed
to bypass receiver authority: the class set is closed, the allocation comes from
the class, and the queue's existing fail-closed semantics decide what happens
next. Pending is not presented.

`max_presentations=0` is a valid receiver policy: everything is admitted,
nothing is ever presented, every result is still successful.

## 6. Active chat and presence

The receiver supplies presence from **its own authenticated context**, never
from sender prose. Exactly two states exist:

* `ACTIVE_CHAT` — the host has a trustworthy signal that the operator is in the
  chat. An ordinary `OPERATOR_ACTION_REQUIRED` then stays in the chat:
  result `PRESENCE_CHAT_SUFFICIENT`, no presentation. `DATA_OR_MONEY_RISK` and
  `CROSS_PROJECT_CRITICAL_DISCOVERY` are still admitted.
* `UNKNOWN` — no trustworthy signal. **Absence of a signal is not evidence of
  absence.** The receiver attention queue applies, with its budget.

There is no `ABSENT` state and no invented detection. `PRESENCE_STATES` is
`{ACTIVE_CHAT, UNKNOWN}`, and any other value is `INTERRUPT_BAD_PRESENCE`.

The core API works with no ZAICODE and no GUI: `saimail.operator_interrupt` has
no dependency on any host.

## 7. Origin: transport context, never prose

`origin` is **not a declaration field**. There is nothing for a sender to fill,
because `operator_interrupt.declaration()` returns exactly:

```
{schema, class, decision_id, work, settled, body}
```

The receiver passes origin as an argument, from declared/authenticated transport
context. `ORIGIN_HUMAN` returns `NOT_AN_INTERRUPT` immediately: a hand-written
letter between people is ordinary correspondence and is never an automated
operator interruption.

**Generic `saimail-local send` is therefore not globally crippled.** Human
authored mail keeps its existing behavior end to end.

## 8. The visible body contract

An operator interruption is a popup. The contract is strict and compact:

* what stopped or changed;
* why an action is required;
* **one** exact action;
* optionally one short consequence line.

Hard budget: **≤ 600 UTF-8 bytes**, preferably **≤ 4 logical lines**
(`MAX_OPERATOR_BODY_BYTES`, `MAX_OPERATOR_BODY_LINES`). Violations are
**refused** with `OPERATOR_BODY_TOO_LARGE` — at the sender helper *and again at
admission*, because a hand-built declaration is not a way around the contract.

**Nothing is ever truncated.** Truncation would produce a summary the sender
never wrote, which is a different claim than the one the sender made. The
sender is required to produce a compact request instead.

Structured evidence lives outside the visible summary, in the sealed record.

## 9. Presentation surface obligations

* No burst. The live incident must be mechanically impossible to reproduce.
* Any operator unread count is computed **only** from the admitted presentation
  layer. Machine/agent mail must never inflate an operator unread badge.
* Opening one interruption may expose its compact body; detailed evidence is an
  explicit secondary inspection, not part of the popup.
* There is no "opened this visit" dumping ground for operator interruptions.
* Normal correspondence stays discoverable elsewhere — never admitted means
  still durable and still findable.

## 10. Result vocabulary

Successful outcomes (exit 0 — none of them is an error):

| result | meaning |
|---|---|
| `NOT_AN_INTERRUPT` | human origin, or the record declares no interruption |
| `UNSETTLED` | declared but not settled; stays durable mail |
| `INELIGIBLE_CLASS` | the class is outside the closed set |
| `PRESENCE_CHAT_SUFFICIENT` | the operator is in the chat; chat is the better channel |
| `ADMITTED` | a candidate exists; the budget still decides presentation |
| `DUPLICATE_DECISION` | exact retry of one decision; idempotent |
| `SUPERSEDED` | a newer letter replaced a pending one |
| `ALREADY_PRESENTED` | one decision already interrupted; the rest stays mail |
| `PRESENTED` | the operator surface showed it |
| `NOTHING_PENDING` | an attention candidate names no admitted decision |

Refusals (non-zero exit):

`INTERRUPT_MALFORMED`, `INTERRUPT_BAD_CLASS`, `INTERRUPT_BAD_DECISION_ID`,
`INTERRUPT_BAD_WORK`, `INTERRUPT_BAD_ORIGIN`, `INTERRUPT_BAD_PRESENCE`,
`OPERATOR_BODY_TOO_LARGE`, `INTERRUPT_LEDGER_CORRUPT`,
`INTERRUPT_BAD_ENVELOPE`, `PENDING_FULL`.

`PENDING_FULL` is a refusal of the *candidate*, never of the message: the
letter is already sealed and delivered, and the operator still reads it in the
mailbox. `INTERRUPT_BAD_CLASS` covers both a class outside the closed set and
a reclassification of an admitted decision (§4).

`PRESENTED` records a *surfacing*, never that the operator read or acted.

## 11. The live incident as the acceptance fixture

Five letters from one Work, replayed (`tests/test_operator_interrupt.py`):

```
1  "retirement command refused; try quarantine"     settled=false
2  "style_contract appears unfixable"                settled=false
3  "correction: write ded-71fc58de"                  settled=false
4  "retract correction: do not write ded-71fc58de"   settled=false
5  "SAIMASTER hard stopped"                          settled=true
```

`EXPECTED_OPERATOR_PRESENTATIONS <= 1`. The first four produce **0**. The final
hard stop produces **0** when active-chat policy says chat suffices, or **1**
when the receiver's own attention policy admits it. **Never 5.**

## 12. Verification

* `tests/test_operator_interrupt.py` — the deterministic regression set,
  including the replay above, exact retry, reworded same decision, a split
  decision, `max_presentations=0`, pending ≠ presented, oversized refusal,
  active chat, `UNKNOWN` presence, restart, and two concurrent presenters.
* `tests/test_gui_operator_interrupt.py` — the presentation layer stayed out of
  the argument, and classification comes from admission state.
* Existing `human_attention` tests are unchanged and still pass.

## 13. Known limits

Stated rather than hidden:

* **The budget is per receiver workspace, not per person.** The queue is keyed
  by `to_human` inside one workspace root. One person who runs two workspaces
  gets two budgets. Making the budget per person across workspaces is a
  change to `human_attention`, which is a frozen input here.
* **`operator_unread` is not monotonic.** A presented interruption that is
  later re-admitted under a new decision id counts again. Dedup is per
  decision, not per message, so a genuinely new decision legitimately
  re-notifies.
* **`acknowledge()` can raise after the receipt is already durable.** The
  queue publishes the receipt before removing the lease; a crash in that
  window leaves the slot spent. Re-acking is safe (`ALREADY_ACKED`) but the
  receiver's ledger update is a separate step.
