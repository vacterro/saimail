# T-122 REVIEW

- Independent python -m pytest -q with SAIPEN_AGENT exported: 2631 passed / 0 failed (review-full-with-carrier.xml); state hash unchanged.
- Verifier changes: new tests/test_notify.py; test_capabilities.py expects the new notify entry (additive expectation); oracle additive.
- Final bytes: notify resolves recipient and kind only through the registry; the budget gate runs under the outbox lock for new intents only; suppression returns before any write; outbox change is additive (content_identity, gate) plus keyless PENDING recording that no longer raises after a durable write.
- No P0/P1. Verdict: DEC: SHIP.
