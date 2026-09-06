# Changelog

## v2 (in progress) - the validator this repository is being rebuilt around

- **DROP-118** Quarantine line numbers no longer agree with `tools/triage.py`
  on drops containing quoted line breaks. The report is right and the script is
  not; see `incidents/2026-05-12-partner-dispute.md`.
- **DROP-131** Column checking order corrected. `tools/triage.py` has not been
  updated and now names a different column than the report does whenever a
  partner reorders their header.
- **DROP-142** Range limits are now resolved from `docs/partner-limits.md`
  rather than from the cached copy in the drop. Capture agents still write the
  cached copy and we still keep it, but it is no longer what a decision is
  based on.
- **DROP-107** `partner` and `captured_at` added to the capture format; every
  drop in the archive has been backfilled.

## v1 - retired

The original single-file validator, plus `tools/triage.py`, which was carved
out of it so the support desk could explain one drop at a time. Its behaviour
is described in `legacy/dropcheck-v1-notes.md`. Both are kept because the desk
still runs the script daily and because the notes explain reports we sent
partners before v2 - not because they describe what we do now.
