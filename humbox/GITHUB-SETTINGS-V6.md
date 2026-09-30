# GitHub repository settings (V6-01)

Prepared values for the SAIMAIL repository presentation sync. Apply through
GitHub Settings only when authenticated repository settings access is
available. Uploading the social preview or editing description/topics is a
presentation action; it is not a release, tag, push or publication.

## Status

- Description: **applied** to `vacterro/saimail` on 2026-09-22 (UTC) through an
  authenticated `gh` session (`vacterro`, `repo` scope); re-read back from the
  repository API and equal to the value below.
- Topics: **applied** (the prepared topics; the pre-existing factual topics
  were retained); re-read back from the repository API.
- Social preview image: `pics/SAIMAIL_SOCIAL_PREVIEW.png` (1280x640 PNG,
  under 1 MB) — **MANUAL_GITHUB_SETTINGS_REQUIRED**: GitHub exposes no API or
  CLI upload for the social preview image, so that one Settings click is
  operator-owned.

`MANUAL_GITHUB_SETTINGS_REQUIRED` for the social preview does **not** block
V6-01 closure. The asset and the exact values are the deliverable; the verified
description/topics are already live.

## Description

```
Local-first agent post office and desktop messenger with sealed messages, explicit provenance and bounded inbox triage.
```

## Topics (factual)

```
python
local-first
messaging
agents
cryptography
provenance
pyside6
offline-first
```

## Do not claim

- cloud messaging
- autonomous agents
- AI replies
- semantic-review reliability

## Social preview upload path

GitHub -> Repository -> Settings -> General -> Social preview -> Edit ->
Upload an image -> choose `pics/SAIMAIL_SOCIAL_PREVIEW.png` -> Commit changes.

## Explicit non-actions

Do **not** create as part of this presentation task:

- GitHub Release
- tag
- package upload
- PyPI publication

Do **not** push the current checkout merely to make the README current.
Before any broad public source synchronization, evaluate version/candidate
alignment first (distribution finding below).

## Distribution finding

```
CURRENT SOURCE IS MATERIALLY AHEAD OF FROZEN 0.0.2a2.
```

The frozen externally proven artifact remains `0.0.2a2`. The current checkout
is ahead by `P1 + V4-01 + V5-01`. That finding is the input for a later D3
decision (post-GUI release candidate / source identity alignment). Do not bump
VERSION, do not build `0.0.2a3`, and do not publish inside V6-01.
