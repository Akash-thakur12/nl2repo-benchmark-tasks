# Capture corpus

Collector captures replayed by the offline audit tool. Schema and verdict
vocabulary are in `../docs/token-format.md`. Every secret needed to replay
these lines ships in `../reference/keyring.json` (revoked keys included), so the
whole corpus is reproducible offline.

Where any tool, comment, or document disagrees with a capture line, **the
capture is authoritative**: it is what tokend did, and it is what an
implementation must reproduce.

| file | what it exercises | tokend / collectord |
|------|-------------------|---------------------|
| `verify-01-eras.jsonl` | one `ok`/`bad-tag` line from each key and era, both changeover boundaries, a pre-epoch line (`no-epoch`), an unknown kid, the duplicated regional listing, and two check-precedence lines | tokend 3.x, collectord 2.x |
| `verify-02-rollback.jsonl` | the Dec-2022 CHG-9032 rollback week: the exact rollback instant, mid-week lines, the exact revert instant, and an un-downgraded client that wrote 8 octets into a 4-octet epoch (`malformed`) | tokend 3.x, collectord 2.x |
| `verify-03-forgeries.jsonl` | the INC-4417 padded forgery (`bad-tag`), a genuine 4-octet tag that really ends in `0x00` (`ok`), several `malformed` shapes (filled pad, wrong frame length, non-hex) | tokend 3.x, collectord 2.x |
| `recovery-01-jobs.jsonl` | key-recovery jobs: the 2-octet ambiguous job (`null`), the duplicated-material job (answers the key), and a mixed-era job with unresolvable samples dropped | audit tool 2.1 and 2.4 |

The `note` field on each line is a human annotation. It is not part of the
input and an implementation must not read it.
