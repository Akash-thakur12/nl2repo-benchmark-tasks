# The tag registry

`registry/tags.csv` is the authority for how a record's four-byte value field is
interpreted. It is a *versioned* table, not a lookup: several rows may exist for
one tag.

Columns:

| column | meaning |
| --- | --- |
| `tag` | the record tag, hex |
| `from_rev` | the registry revision at which this row took effect |
| `encoding` | `absolute` or `delta` |
| `name_hint` | documentation only; not used by the codec |
| `notes` | free text |

## Which row applies

The row in force for a record is the one with the **greatest `from_rev` that is
not greater than the registry revision in force for that record**. A tag with no
applicable row — either because it is not registered at all, or because every
row for it is newer than the revision in force — is `absolute`. That covers the
reserved `0x00`–`0x0F` transport range without a special case.

## Which revision is in force

Two sources, in this order of precedence:

1. **In-band.** A record with the reserved tag `0x0E` (the `__rev` marker) sets
   the registry revision for every record that follows it in the same blob. A blob
   may carry more than one marker; `samples/rev-switch-09.bin` changes the
   revision half way through while one series spans the change, so what that
   does to the series is checkable rather than a matter of taste. Its
   `value` is the revision number. It is an ordinary record in every other
   respect: it occupies a record slot, it is counted, and a reader returns it
   like any other record.
2. **Out-of-band.** The codec option `registry_revision`, supplied through the
   engine's constructor config or through `configure()`, sets the revision in
   force at the start of a blob.

When neither is present, the newest revision in the registry applies — i.e. the
greatest `from_rev` in `tags.csv`. That is the right default for live traffic
and the wrong one for archives, which is why archives carry the marker.

## `delta` encoding

For a tag whose row in force says `delta`, the value field of the **first**
record of a series holds the value itself. Every subsequent record of the same
series holds the difference from the previous value of that series, ZigZag
encoded — the same mapping protobuf uses for `sint32`: non-negative `n` maps to
`2n`, negative `n` maps to `-2n - 1`.

The value field is four bytes wide and the underlying counters are 32-bit, so
the difference is computed in 32-bit modular arithmetic and then interpreted as
a signed 32-bit quantity before it is ZigZagged. A counter that rolls over past
its 32-bit range therefore yields a small step, not a huge negative one — see
`samples/series-wrap-05.bin`, whose manifest entry records a rollover.

What counts as one "series" — that is, which records chain together — is not
spelled out here; `samples/series-twoname-04.bin` puts more than one name under
a single delta tag precisely so that the question has a checkable answer.  A second
blob, `samples/series-crosstag-08.bin`, carries one name under two different
delta tags for the same reason: between them the two blobs settle what a chain
is keyed by, and the manifest gives the exact records each was written from.

Delta coding applies **only** where a registry row in force says so. Tags with
no applicable row, including every reserved transport tag, always carry their
value directly.
