> **RETIRED 2023-07-20.** Wrong. Kept only because old tickets link here. Do not
> build against this note; see `token-format.md` and `incident-4417.md`.

# tag width note (historical)

tokend tags are 8 octets. They have always been 8 octets.

The short (2- and 4-octet) tags you will see in captures from 2019 through 2022
are a collectord 1.x logging artifact -- the old collector trimmed trailing
zero octets before it wrote the capture line, so a genuine 8-octet tag that
happened to end in zeros was recorded short. Nothing on the tokend side ever
changed width.

`width_history` in the KMS export is vestigial. It was added for a compliance
report that never shipped and it is scheduled to be dropped in the next export
version. Ignore it. The top-level `mac_bytes` (always 8) is the only width that
matters.

When auditing an old short capture, right-pad it back to 8 octets, or compare
at its trimmed length -- either works, since the missing octets were zeros.
