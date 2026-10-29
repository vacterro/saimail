# Selector coverage replay after storage repairs

The original V202 registration, manifest, input copies and historical results
remain frozen. Current `saimail/postoffice.py` differs from that implementation,
so the original manifest correctly reports `CURRENT_IMPLEMENTATION_DRIFT` and
the default experiment invocation refuses `V202_INPUT_DRIFT`.

An explicit offline replay registration binds the repaired implementation:

```powershell
python tools/selector_coverage_experiment.py --manifest lab/selector_coverage_replay_20261029_r2_manifest.json --out lab/results/selector-coverage-replay-20261029-r2
```

Choose a new output directory on each execution. The replay has its own
experiment identity and frozen registration copy. It reuses the original public
fixtures, policies, grading criteria and friction model without changing their
meaning. Its manifest also binds the journal cache imported by the repaired
Post Office. Input, historical-copy and implementation drift still refuse.

`HISTORICAL_ONLY` remains the authority of both manifests. A successful offline
run grants no live-service authority, production promotion or publication.
The regression suite exercises the explicit replay against current code and
separately verifies that the original registration remains unchanged and refuses
the changed implementation.

The first 20261029 replay remains preserved. Revision R2 registers the later
storage-evidence and Windows metadata fixes against the same frozen fixtures
and criteria. It also binds the runtime dependency declaration. A previous
replay is historical evidence, not an authority to run changed implementation.
