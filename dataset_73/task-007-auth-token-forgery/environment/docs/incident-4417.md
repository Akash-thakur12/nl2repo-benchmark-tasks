# INC-4417 -- accepted forged request tag

Severity 1. Opened 2023-06-02. Closed 2023-08-01.

## Summary

An external party submitted a `POST /v1/transfer` frame whose tag field was
accepted by the audit pipeline and rejected by tokend itself. Reconciliation
found the discrepancy 40 hours later. The frame is preserved as the first line
of `capture/verify-03-forgeries.jsonl`.

## Root cause (initial)

*Recorded 2023-06-03, superseded -- kept for the record.*

The audit worker had a stale pinned key. tokend-2021h had been reissued and the
worker's cached copy of the export predated the reissue, so the worker computed
MACs under the wrong secret and its verdicts drifted from tokend's. Remediation:
shorten the export cache TTL, alarm on export age, rotate on schedule.

We spent three weeks on key-rotation lag. It was not key-rotation lag. Every
verdict in the disputed window was computed under the correct secret; we
re-ran them against a hand-pinned export and got the same verdicts.

## Root cause (addendum, 2023-07-19)

The audit worker compared each captured frame at the tag width the key has
*now*, taken from the export's top-level `mac_bytes`, instead of the width that
was in force when the frame was captured.

The tell was the December 2022 rollback week. tokend-2021h went 4 octets at
rollout, 8 octets at the SEC-118 hardening, back to 4 for six days during
CHG-9032 (the meter fleet could not parse the wider field), then 8 again at
CHG-9048. Widths do not only ever grow. Every capture line from a 4-octet epoch
came out of the worker as `bad-tag`, which we had been writing off as
collector noise for two years, and every line inside the rollback week did too
even though it sat between two 8-octet epochs.

The forged frame slipped through the other side of the same mistake. The
attacker guessed three octets of a 4-octet-era tag and zero-filled the rest of
the field. A worker that trims trailing zeros before comparing compares three
octets, and three octets is 24 bits. Trimming is not conservative: a genuine
4-octet tag ends in `0x00` about once in 256 (see the `acct=365` line in the
same file), so the trimmer cannot tell a short tag from a padded one. Only the
epoch width can.

## Recovery jobs

The 2019 key-recovery job is a separate lesson recorded here because the fix
shipped in the same release.

That job named `tokend-2019m` as the leaked meter key. We revoked it, took the
meter fleet down for a day, and the leak continued -- because the actual
leaked key was a different one. The meter fleet's tag is **2 octets**. Two
octets is 16 bits of evidence per sample, and the job had four samples over two
distinct preimages. Two unrelated secrets in the candidate list reproduced
every one of those tags; the tool returned the first one it hit and reported it
as the answer. It had no basis for choosing between them. The replayable
record is the first entry of `capture/recovery-01-jobs.jsonl`.

Audit tool 2.4 changed this: a search that ends with more than one distinct key
material still fitting the evidence is **not an identification** and the job
reports no answer. The operator's next move is to collect more samples, not to
revoke something.

The same release stopped reporting an ambiguity when the *only* thing that
matched more than once was the same secret listed twice. A key registered in
two regions appears under two `kid`s with identical material; the audit tool
now compares material, not listings, and answers with the key. See the
`2023-02-regional` entry in the same file.

Also from 2.4: a recorded sample whose width cannot be resolved -- unknown
`kid`, an instant with no epoch, a frame that is not a valid tag field --
carries no evidence and is dropped from the set. Counting it as a mismatch used
to make every mixed-source job return nothing. If nothing usable is left there
is no evidence and no answer.

## Actions

* [done] audit tool resolves tag width per event from `width_history`
* [done] non-unique recovery reports no answer
* [done] `tools/tag_doctor.py` marked unsupported (its trimming model is the
  bug above, and it names the key as the root cause for every mismatch)
* [done] `docs/RETIRED-tag-width-note.md` retired, not deleted -- it is cited
  from old tickets
* [open] rewrite the offline audit engine against the capture corpus
