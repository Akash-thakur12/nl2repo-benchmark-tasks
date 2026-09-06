# BIN1 wire format (revision of 2021-03)

## Container

A blob opens with the four ASCII bytes `BIN1`, followed by a `count` field.
Everything after the header is a run of records. Every multi-byte integer in
the format is little-endian; there is no alignment or padding anywhere.

A record carries a tag, a name and a value:

* `tag` is one byte. Tags `0x00`–`0x0F` are reserved for transport control and
  carry no metric meaning; `0x10` and above are data tags and are described by
  the registry (see `registry.md`).
* the name is a UTF-8 string, introduced by a `name_len` field;
* the value field is four bytes wide and holds an unsigned quantity. Whether
  that quantity is the record's value or something derived from it depends on
  the tag — again, see `registry.md`.

`count` and `name_len` are both two bytes wide.

## Reserved values

**The all-ones value of an unsigned field is a sentinel in this format, never a
magnitude.** Both two-byte fields follow that rule, and each does something
different with it:

* `name_len == 0xFFFF` does **not** introduce a 65535-byte name. It is the
  reserved marker; what follows it is not name text. See "Name interning"
  below. Any blob in `samples/` whose name recurs uses it.
* `count == 0xFFFF` does **not** mean "65535 records follow". It marks a
  *streamed* blob: one whose length was not known when the header was written.
  A streamed blob's record run ends at a terminator record instead of at a
  count. `samples/streamed-fleet-01.bin` is one, and `samples/manifest.json`
  lists exactly the records it must decode to — note what is and is not in that
  list. The terminator is an ordinary record slot carrying the reserved tag
  `0x0F`, an empty name and an all-ones value; it is part of the byte stream
  and must be consumed, but it is not data.

Our writer never emits the streamed form — that was the collector's job, and
the collector is already retired — but archived blobs still use it and the
reader must accept them.

Consequence to think through: a field that has spent its all-ones encoding on a
sentinel cannot also use it as a number. Work out what that does to the largest
name and the largest record run this format can represent, and enforce it in
the writer rather than emitting something no reader can read back.

## Name interning

Names repeat heavily in real captures — the same metric name appears on every
sample — so BIN1 does not store a name more than once per blob. The first
appearance of a name in a blob is written out literally. Every later record
carrying the same name refers back to that first appearance instead of
repeating the bytes, using the reserved `name_len` value above. Interning is
unconditional: a repeated name is *always* referred back to, even when doing so
costs more bytes than repeating it would.

The exact shape of the reference — its width and, more importantly, what the
number in it is counted against — is not written down here. The C++ reader that
implemented it is not in this repository. The `samples/` blobs that repeat
names, read against `manifest.json`, pin it exactly;
`intern-firstref-02.bin` and `intern-ordinal-03.bin` were kept specifically
because they discriminate between the readings that otherwise look alike.

The interning table lives for the duration of one blob. It is built while that
blob is written and thrown away afterwards, so encoding the same records twice
always gives the same bytes.

## Canonical form

A writer MUST emit canonical form: for any record list there is exactly one
legal byte string. That is what makes "re-encode a golden sample and compare
the bytes" a valid conformance test, and it is how the samples in this tree are
meant to be used.

## Errors

A reader rejects, with an error rather than a partial result:

* a blob that does not start with `BIN1`, or that is too short to hold a
  header;
* a record run that ends before the count (or before the terminator, for a
  streamed blob) is satisfied;
* a name reference that does not point at an earlier record of the same blob.
