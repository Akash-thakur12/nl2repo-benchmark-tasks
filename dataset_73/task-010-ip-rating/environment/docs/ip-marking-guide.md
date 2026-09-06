# Reading IP markings (internal guide)

Compliance engineering, rev 7. This is the house guide to IEC 60529 degrees of
protection as we use them in incoming inspection. It states the principles; the
tables live in the register export and the worked decisions live in the sample
exports. Where this guide and those files disagree, the files win - they are
what the certification database actually did.

  * `/app/docs/iec60529-editions.json` - the standards register
  * `/app/samples/nameplate_marks.csv`  - marks the database decoded, and marks it refused
  * `/app/samples/acceptance_log.csv`   - incoming-inspection accept/reject decisions

## 1. What is on the nameplate

A marking is made of *elements*, and clause 4.1 fixes the order they appear in:

    IP  <first characteristic>  <second characteristic>  [additional letter]  [supplementary letter]

The `IP` prefix is conventional and is often left off in our own paperwork. The
two characteristic positions are always both present - a marking that carries
only one of them is not a marking, it is a typo. Where a characteristic has not
been tested, or the manufacturer simply does not state it, the position is
filled with the placeholder letter `X` rather than left empty.

Case is not significant. Neither are separators: fitters write `IP 65`, the
purchasing system writes `IP-65`, the label says `IP65`, and all three are the
same marking.

A part may carry more than one code, separated by `/`, when it has been tested
under more than one method - `IP65/IP68` is the classic wash-down-plus-immersion
enclosure. A dual marking is read as the union of what its codes establish,
position by position; it is *not* a list of alternatives to be considered one at
a time.

### Additional letter

The additional letter (A-D) describes protection against *access to hazardous
parts*: which probe cannot reach live or moving parts inside. Access protection
and the ingress of solid foreign objects are two different tests, and the first
characteristic numeral reports the second one. They are related - passing a
given object test necessarily means a probe of that size cannot get in either,
so every first numeral already implies a degree of access protection, and that
implied degree is what we record when no letter is given.

That is exactly why the letter exists: clause 4.2 allows it *only* where the
actual protection against access is higher than the first numeral by itself
implies. A letter that ranks below the access implied by the numeral in front of
it is a contradiction, not extra information, and the database refuses such a
marking outright. (The letters rank A < B < C < D.)

### Supplementary letter

The supplementary letter (H, M, S, W) records the condition the sample was in
when it was tested - live, running, stationary, weather-exposed. It qualifies
the test, not the degree of protection, and it plays no part in deciding whether
a part meets a requirement.

## 2. Two words that are not the same

Our tooling is careful to keep apart

  * a characteristic that was *not stated or not tested* - the `X` case, and
  * a characteristic that *is* stated but has no meaning in the edition the mark
    is read against.

They are different words in the decode, and they must not be swapped. The
`solid`, `liquid` and `access` columns of `samples/nameplate_marks.csv` show
both in use.

## 3. Editions and the date of test

A mark is read against the edition in force on the date of test, not against
whatever is current today; the register is `/app/docs/iec60529-editions.json`.
Each register entry gives the date it came into force and, for an amendment, the
entry it extends. An amendment entry lists only what it changes: everything it
does not mention it inherits along the `extends` chain. Not every amendment
changes the tables - one of them is in the register purely because it is in
force, and changes nothing.

The register is exported in record order. It is not sorted by date, so pick the
governing entry by comparing dates, not by position in the file.

With no test date given, read the mark against the current edition.

> **Note.** `/app/tools/ip_lint.py` still carries its own copy of the tables. It
> has not been touched since before A2:2013 was published, and it predates our
> support for the `X` placeholder, so it rejects marks that are perfectly valid
> and blames the wrong thing when it does. It is scheduled for removal. Do not
> treat its diagnostics as normative.

## 4. Does the part meet the spec

This is the question inspection actually asks: a purchasing requirement is
itself written as a marking, and we ask whether a part's nameplate meets it.
Three things are compared independently - the object numeral, the liquid
numeral, and access protection - and all three must be met.

The general principle is the cumulative one stated in clause 6.1: a
characteristic numeral implies compliance with the requirements for all lower
numerals. A part marked IP5x satisfies a requirement for IP3x without further
testing.

The principle is *not* universal on the liquid side, and this is where most of
our rejections come from. Clause 6.2 note 1: an enclosure designated with second
characteristic numeral 7 or 8 is not thereby suitable for exposure to water jets
and need only be so designated if it also complies with the corresponding jet
requirement - which is what a dual code is for. The high-pressure test added by
A2 is likewise a separate apparatus, not the top of the jet ladder. The
enumerated consequences are in `samples/acceptance_log.csv`; read them before
implementing the comparison, because there is no way to derive the exact
exclusions from this paragraph alone.

An `X` on either side means something different:

  * `X` in a **requirement** position means we are not asking for anything there.
  * `X` on a **nameplate** means nothing was established there, so it satisfies
    no requirement in that position - not even the lowest one.

## 5. Local conventions

`dust-tight` is the only first-numeral value that lets a part into the
particulate-controlled areas, and the flag we carry on the decode is exactly
that: whether the enclosure is dust-tight. An enclosure whose first
characteristic is not stated is not dust-tight, however good its liquid rating.
