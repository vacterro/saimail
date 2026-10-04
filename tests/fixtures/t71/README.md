# T-71 frozen inputs

`quarantine.py.txt` is the exact source registered by the historical T-71
experiment, before T-65 fixed assignment matching across blank lines.

- SHA-256: `0960dd992839ca149a81be3bdf80746fb6cd7397023ef2998d429cf03428b985`
- Source: `saimail/quarantine.py` in Git commit `3fa8f22`.
- Authority: `lab/project_corpus_reachability_registration.json`.

`legacy.py.txt` and `postoffice.py.txt` are the registered sources for those two
paths at the same registration.

`envelope.py.txt` is the registered `saimail/envelope.py` immediately before
T-161 added the `FUTURE_LETTER` transport kind to the closed SENV2 kind set.

- SHA-256: `025b435274ac6e28c149723d41e6ba770cc51120b15cf5669a984d1bf087eef2`
- Authority: `lab/project_corpus_reachability_registration.json`.

The historical experiment must keep running against the exact inputs it ran
on. A later additive change to the live source does not retroactively change
what T-71 measured, so the frozen bytes live here and the registration test
builds its temporary tree from them.

This is inert test data, never imported or executed. Registration tests use a
temporary tree whose files match the original registered hashes. The production
registration and its source-drift refusal remain unchanged; this fixture does
not authorize running the old live registration against modified code.