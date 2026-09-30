# T-147: public recipient management with locked custody

SRC-112 prioritizes useful product work over enrolling real-use participants.
SRC-113 permits genuine SAIFREN participation only with separate execution /
context and independent work on real evidence. T-146 was canonically changed
from a goal-scoped blocker to an optional ticket-scoped unavailable study.
Historical registration and all four EMPTY observations remain unchanged.
Independent receiver assessment, revision and successor execution remain NOT_RUN;
field improvement remains UNPROVEN. No extra study entry was appended.

The selected product defect is reproducible without any real peer: public
`recipient list` loaded private identity keys and failed on a locked credential
store even for an empty mapping. Public `recipient add` had the same unnecessary
key dependency. Missing, unreadable, non-UTF-8 and malformed JSON card files
could also escape the structured command-error boundary.

Both commands now reuse the validated WorkspaceHeaders view. The existing
workspace JSON reader maps card read/parse failures to RECIPIENT_MALFORMED;
existing card shape, fingerprint, peer-marker and alias-conflict checks still
own admission. Add changes only the explicitly requested public mapping. List
is read-only. Sending still performs the full private-key load and refuses
locked custody. No provider, message, lifecycle or independent-actor operation
was added.

The same corrected 22-test oracle failed 20 controls against the retained
pre-fix CLI and passes on the current CLI. Tests cover a locked empty listing,
no full-key load or credential reads during add/list, idempotent add, malformed
and unreadable cards with locked/unlocked custody, unchanged public identity
refusals, alias conflict and unchanged refusal of sending without keys. Their
isolated workspaces are product fixtures, not enrolled independent participants.
The first valid alias-conflict fixture attempted to export a new card over an
existing card; CARD_CONFLICT correctly refused that setup. The corrected fixture
uses its own card file. Both failed evidence rounds remain retained; the final
oracle hashes and its old/current runs are separately bound.

The laboratory transport in lab/saifren_run.py provides opaque chat routing;
its T-145 aliases alone establish no independently executing peer. Further
inspection found an actual OpenCode host and sairoute/SAIFREN model route.
That route was exercised in a fresh native workspace/session for useful product
review, without copying root chat or supplying earlier review verdicts/test
outcomes. Native session ses_f0d499707ffe15naRiJ1EvcJuR first declared a review
scope, effort boundary and criteria before source exposure. A subsequent
invocation in that reviewer's own session independently read the frozen public
source packet. Both native process identities, timestamps and public tool events
are retained. The source manifest binds the actual T-147 files by SHA256.

The source-review invocation exceeded its 180-second deadline and was stopped.
Several source reads completed, one read failed, and no final assessment was
returned. The six-iteration setting is an agent configuration, not a proven cap
on underlying provider retries; repeated step-start events remain preserved.
The actual timeout bounds execution. No completed peer verdict, independently
selected revision or successor execution is invented from this partial result.
No study letter was sent and no new real-use entry was appended. Existing study
counts remain four EMPTY observations and zero independent behaviors.

Thus separate native execution/context is observed, while eligible-letter
study behavior is still UNAVAILABLE / NOT_RUN. Underlying provider context and
model weights remain OPAQUE; the route name is not provider provenance. There
is no further model retry to force a positive result. Product review concludes
from the unchanged pinned tests and source inspection, independently of this
optional incomplete reviewer. The originally executed review helper is retained
as saifren_native_review_observed.py; its only later change removes an extra
blank line flagged by Ruff.

Configuration follows the official [OpenCode agent documentation](https://opencode.ai/docs/agents/)
and [permission documentation](https://opencode.ai/docs/permissions/): the native
reviewer has a finite iteration setting and read-only tool permissions.
