# T-148: concurrent public recipient registration

Two simultaneous successful additions could retain only one alias. Competing
identities for the same alias could both report success and silently replace
one another. A retained product-fixture reproduction aligned both writes;
ordinary sequential additions were separately confirmed to preserve both.
These isolated fixtures are not real-use participants or study observations.

Registration now reuses the existing OS file lock to cover one fresh registry
read, conflict admission and atomic replacement. Public/card/peer validation
still precedes mutation. Distinct aliases survive, different identities compete
for one authoritative mapping, and identical additions remain idempotent.
Listing creates no lock file and remains read-only. Sending, receiver decisions,
participant admission and provider execution have no new path here.

Lock contention and persistence refusal use explicit command codes. A failed
registry lock acquisition closes its descriptor because Python does not call
__exit__ when __enter__ raises. A local subtype owns that cleanup, while the
underlying OS lock and shared Post Office source remain unchanged.

The final pinned 14-test oracle fails 11 controls against byte-identical
pre-change subjects and passes on the repaired implementation. Its original
subject replay stages public packages and the same test/config bytes under a
temporary root with that root on PYTHONPATH, so child Python also executes the
original subject. An earlier parent-only replay is retained but does not claim
original-subject coverage for child processes. Thread controls force the old
lost-update ordering; additional native child processes exercise the shared
registry across independent process identities. No model or independent study
receiver is inferred from those product controls.

The initial shared lock-cleanup candidate correctly failed the full suite's
frozen selector experiment admission (3 failures and 8 setup errors): changing
postoffice.py altered its preregistered implementation hash. That candidate and
its failed run are retained. Post Office was restored byte-for-byte to its
pre-Work hash; no historical manifest, registration, expected result or test
admission was changed. Cleanup moved to the actual recipient lock subtype.
The descriptor oracle now chooses the actual registry subtype when present,
otherwise the original primitive; its requirement to close a refused lock
descriptor is unchanged. Both oracle versions and hash pins remain retained.

The former 22 public-recipient controls also pass. The rejected Post Office
candidate had 51 inherited Ruff findings and zero new findings; final Post
Office is byte-identical to the original. No inherited finding was changed;
workspace, new tests and verification helper pass their scoped Ruff checks.

T142_REAL_USE_1 remains four EMPTY observations and four qualifying boundaries.
There are zero eligible receiver opportunities, independent assessments,
independently chosen revisions and fresh successor executions. Peer-dependent
behavior remains unavailable / NOT_RUN and field_improvement UNPROVEN.
The separate native SAIFREN product reviewer from T-147 timed out; it supplies
no completed assessment and was not retried or converted into a study peer.
