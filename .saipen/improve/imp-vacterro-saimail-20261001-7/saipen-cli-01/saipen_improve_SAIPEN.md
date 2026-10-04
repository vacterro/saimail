agent: saipen-cli-01
role: core
model_or_runtime: unknown
project: vacterro-saimail
saipen_version: 8.0.1
protocol_fingerprint: sha256:0ff34c183c5f4ff5a11809c99b7055e22a89a71b140ff7f5d30e5c9e303ab5fd
source_head: d6a7351ddc42df4af92962b1ac7a047174807f38
source_tree_fingerprint: git-delta-v1:a924dcce45cb1e0146be0ba4eb4edd2b8fca74167f2091b9b78d2890b4cecdf9
discovery_model: git-delta-v1
context_scope: SAIPEN audit, phase DONE
context_available: partial
report_status: complete

## RUN 1

Cycle -7 audit, seat saipen-cli-01, role core, against the committed tree d6a7351ddc42df4af92962b1ac7a047174807f38 (previous seat audited 12e30059). The delta is the T-154 operator-interruption gate as it now exists in git history, plus the T-156 closure. Re-reading the code is not the method here: T-154's whole thesis is that a rule stated in prose fails, so this pass attacked the gate through its public API on the committed bytes and recorded what actually happened.

Baseline first, so the attacks below mean something: python -m pytest -q exits 0 across the suite on this commit; lab/red_control_t154 replaces the module with its pre-fix shape and reports exactly 47 distinct FAILED, unchanged from before the commit, so landing the work in history did not weaken the proof; ruff --select E4,E7,E9,F is clean over all six files this commit touches (the 84 findings the whole-tree run reports are pre-existing and sit in files no ticket here has modified).

Sender bypass vectors, each run against a fresh receiver on a temporary workspace:
-- SPLIT ONE DECISION INTO TWO IDENTITIES. Admitting sait-001 and then sait-002, same Work, same class, same underlying problem. Both return ADMITTED and BOTH return presented=False; budget reads consumed 0, available 1, pending_candidates 2. The second letter does not buy a second interruption; it becomes a second candidate competing for the receiver's one slot, and the admission record says so in its own detail field: 'admitted as a candidate; presenting it still costs the receiver's one attention slot'. The budget stays receiver-owned and unspendable by a sender. (Rewording the same decision_id returns SUPERSEDED, as a correction must.)
-- REWORD THE SAME DECISION. Same decision_id, different body: SUPERSEDED, presented=False. The correction supersedes rather than adds.
-- INVENT A HEAVIER CLASS. 'URGENT' is refused before anything is written: INTERRUPT_BAD_CLASS. After sait-001 exists, re-declaring it as DATA_OR_MONEY_RISK is refused with INTERRUPT_BAD_CLASS -- a decision cannot be reclassified upward after the fact.
-- TRAILING WHITESPACE IN THE IDENTITY. decision_id 'sait-001
' is refused with INTERRUPT_BAD_DECISION_ID, so a trailing newline cannot mint a second decision for one Work.
-- SMUGGLE A FIELD THE SENDER SHOULD NOT OWN. Adding presence:'active-chat' to an otherwise valid declaration is refused with INTERRUPT_MALFORMED -- a declaration cannot carry presence or priority because no such field exists to fill.
-- DECLARE A NON-AGENT ORIGIN. admit(origin=ORIGIN_NOT_AUTOMATION) is refused with INTERRUPT_BAD_ORIGIN. And the CLI confirms the boundary from the other side: --origin and --presence exist only on `interrupt admit`, the receiver's own command, never on `send`; a sender has no flag through which to claim to be human or to claim presence.
-- DECLARE AN UNSETTLED DIAGNOSIS. status UNSETTLED -- durable mail, no presentation path.
-- OVERSIZE THE OPERATOR BODY. One byte past MAX_OPERATOR_BODY_BYTES is refused with OPERATOR_BODY_TOO_LARGE. Nothing is truncated; the request is refused.

NO_FINDINGS -- no bypass of any invariant T-154 claims was reachable from the sender side. Every stated bypass in the ticket -- rewording, a new subject or trigger, a new envelope, retraction and resend, splitting one decision into several -- was either superseded, refused, or converted into a candidate that still costs the receiver's own slot.

One observed ceiling, recorded rather than filed, with its reproduction. The decision identity is (to_human, work, decision_id), so the SAME decision_id re-declared under a DIFFERENT Work is a different decision and is admitted as a fresh candidate. Eight such candidates fill MAX_PENDING_DECISIONS, and a ninth genuine hard stop is then refused with PENDING_FULL until the receiver frees room via `interrupt status` / `interrupt release`. This is not a bypass of the attention budget -- the sender gains no presentation by doing it -- it is the opposite direction, suppressing a later real interruption, and it requires eight sealed messages from inside the sender's own trust domain. The receiver keeps every tool needed to see it (the pending set and PENDING_FULL are both surfaced) and to act. Whether a sender should be able to exhaust the receiver's pending set is receiver policy, which is exactly the ownership T-154 moved to the receiver; deciding it is not this seat's call and no ticket is opened for it.

VERDICT: the committed gate behaves as specified on the bytes that are now in history. Nothing on the board is workable; T-146 remains parked with zero independent peers enrolled, which no agent here can supply.
