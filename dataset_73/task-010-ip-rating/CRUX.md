# Why this task is hard

A hard task is only worth buying if it is hard for a legitimate reason.
This note names the reason, so a reviewer can check the claim rather than
take it on trust.

Every mechanism below hides the *path* to the answer. None of them hides
the *existence* of a single correct answer: for each one, the evidence
that makes the right behaviour recoverable ships inside `environment/`,
and is named here. A task with two defensible readings would be a defect,
not a difficulty.

## What a model has to work out

### B - The liquid ladder is not monotonic: IPX7/IPX8 do not cover IPX5/IPX6

**Mechanism.** Add the method the tool actually exists for: `satisfies(self, mark: str, requirement: str) -> bool` ("does this part's nameplate meet our purchasing spec?"), plus `covers` as its documented alias. Solid numerals are a cumulative ladder (n covers every r <= n, 0..6). Liquid numerals are cumulative only up to 6: the jet tests (5, 6) and the immersion tests (7, 8) are different test methods, so the coverage relation is LIQUID_COVERS = {0:{0}, 1:{0,1}, 2:{0,1,2}, 3:{0..3}, 4:{0..4}, 5:{0..5}, 6:{0..6}, 7:{0,1,2,3,4,7}, 8:{0,1,2,3,4,7,8}} - 7 and 8 skip 5 and 6, and 8 covers 7. Dual marks ("IP65/IP68", "IP65/IPX7") are unioned DIMENSION-WISE, not evaluated per-code: mark "IP65/IPX7" satisfies requirement "IP67" (solid 6 from the first code, liquid 7 from the second) even though neither code satisfies it alone. instruction.md documents only the signature and the boolean return; it never states a comparison rule.

**The wrong answer it punishes.** `int(mark[1]) >= int(req[1])` - a single numeric ordering over both digits. That returns True for satisfies("IPX7", "IPX5") and satisfies("IP68", "IP66"), which is the single most common real-world IP mistake (buying an IP67 part for a wash-down spec that needs IP65). The second wrong default is per-code evaluation of dual marks (`any(code satisfies req for code in codes)`), which returns False for satisfies("IP65/IPX7", "IP67").

**How it is recoverable.** environment/docs/ip-marking-guide.md states the general principle in prose - "a characteristic numeral implies compliance with the requirements for all lower numerals" - and then quotes the IEC 60529 clause-6 note that an enclosure designated with second numeral 7 or 8 is not thereby suitable for exposure to water jets, WITHOUT enumerating which pairs that excludes. environment/samples/acceptance_log.csv (an export of incoming-inspection decisions: requirement, part_mark, decision, reviewer_note) closes it to exactly one relation: rows rejecting IPX7-vs-IP*5, IPX7-vs-IP*6, IP68-vs-IP65, IP68-vs-IP66 with the note "immersion rating, not jet-tested - needs dual code"; rows accepting IP68-vs-IPX7, IP65/IP68-vs-IP65, and IP65/IPX7-vs-IP67 ("dual coded, both tests on file"); and rows accepting the ordinary cumulative cases 6-vs-4, 5-vs-3. Default cumulative + the four enumerated exceptions is fully determined - there is no second consistent reading.

### D - The X placeholder and the letter suffixes: real marks are not two digits

**Mechanism.** Delete from instruction.md §3 the sentence "`code` is two digits, optionally preceded by a case-insensitive \"IP\" prefix (e.g. `\"65\"`, `\"IP68\"`, `\"ip20\"`)" and the sentence "Raises `ValueError` if `code` is not a string, has fewer than two significant characters, or either of the first two significant characters is not a digit." Replace both with: "`code` is a marking as it appears on a nameplate. `environment/samples/nameplate_marks.csv` is an export of marks the certification database has already decoded, and of marks it refused; it is normative for what is accepted and what raises ValueError." The real grammar (IEC 60529 clause 4.1) is: optional case-insensitive IP prefix, first numeral or `X`, second numeral or `X`, optional additional letter A-D, optional supplementary letter H/M/S/W, in that order; separators (space, hyphen) are insignificant; `/` separates dual codes. So `describe` must accept "IPX7", "IP2X", "IPXXB", "IP65CS", "IP44M", "IP 65", "ip-65", "IP65/IP68", and return `"unspecified"` (not `"unknown"`, not an exception) for a numeral replaced by X, while still raising ValueError for "IP6", "6Q", "IPZ4", "IP654" and - the ordering rule - "IP65SC" (supplementary letter before additional letter). `"unknown"` is reserved for a numeral that is present but undefined in the governing edition; this two-word distinction (unspecified = not tested/not stated, unknown = out of table) is what the corpus teaches. Returned dict gains keys `access`, `supplementary`, `codes`, `edition`.

**The wrong answer it punishes.** Exactly what the current spec commands and what the current test suite enforces: any non-digit in a numeral position is malformed, so "IPX7" and "IP2X" raise ValueError (test_bad_code_raises currently asserts precisely this for "X4" and "6X"). Secondary defaults: stripping all letters and decoding the digits (loses the additional-letter meaning and accepts the illegal "IP65SC" order), and reusing `"unknown"` for an X placeholder.

**How it is recoverable.** environment/samples/nameplate_marks.csv ships ~45 rows - `mark,tested_on,solid,liquid,access,dust_tight,supplementary,status,note` - covering every shape above with its recorded decode, and rejected rows carrying the refusal reason ("third numeral", "supplementary letter precedes additional letter", "character not a numeral or X"). environment/docs/ip-marking-guide.md gives the clause-4.1 element order and the letter meanings in prose. The tests use held-out marks (different numeral/letter combinations), so the corpus teaches the grammar and cannot be memorised into an answer table.

### I - Decode against the edition in force on the test date, not the current one

**Mechanism.** Delete both numeral tables from instruction.md §2 and the line "Any numeral outside its table maps to the string `unknown`", and delete the SOLID/LIQ dicts from the environment stub. Ship the tables instead as environment/docs/iec60529-editions.json, an export of the standards register: a list of edition objects `{id, effective, extends, first_numeral, second_numeral, additional_letter, supplementary_letter}`. `IEC 60529:1989` (effective 1989-11-15) carries the full tables; `IEC 60529:1989+A1:1999` (effective 1999-11-01, extends the 1989 entry) carries an empty delta; `IEC 60529:1989+A2:2013` (effective 2013-08-01, extends A1) carries the single delta `second_numeral: {"9": "high-pressure-jet"}` - the amendment that actually introduced numeral 9. `describe(code, tested_on=None)` gains an optional test date (ISO string or datetime.date); the governing edition is the one with the latest `effective` that is <= tested_on, and its table is the merge along the whole `extends` chain. With no date, the newest edition governs. So describe("IP69") -> liquid "high-pressure-jet", describe("IP69", tested_on="2011-04-02") -> liquid "unknown", describe("79", tested_on="2005-01-01") -> both "unknown". Three traps in one file: the entries are deliberately NOT in effective-date order (so "take the last entry" and "take the first entry" are both wrong), the amendment entries are deltas not full tables (so treating A2's table as complete makes every numeral except 9 "unknown" on modern dates), and the inert A1 entry sits between the two dates so the as-of pick has to be a real comparison rather than a two-way if.

**The wrong answer it punishes.** One frozen table, current edition always - i.e. numeral 9 either always decodes as high-pressure-jet or always as "unknown", and `tested_on` is accepted and ignored. This is exactly what the environment tells you to do: the misdirection is environment/tools/ip_lint.py, a real internal linter shipped in the environment whose embedded table stops at 8 and whose diagnostic names the wrong root cause - `IP69: second characteristic numeral out of range (0-8); likely a typo for IP68` - with a docstring asserting "the second numeral is always 0-8". Its table is the 1989 edition and it was never updated after A2:2013. A model that trusts the linter (or the existing task.toml text "Liquid 0-8 per IEC 60529", which gets scrubbed) hardcodes 0-8 and fails every date-sensitive test.

**How it is recoverable.** environment/docs/iec60529-editions.json is the ground truth: `effective` dates, the explicit `extends` chain, and the 9-only delta are all right there in the file the instruction points at. environment/docs/ip-marking-guide.md states the register rule in one line ("a mark is read against the edition in force on the date of test; the register is /app/docs/iec60529-editions.json") and flags the linter as pending an update. environment/samples/nameplate_marks.csv contains a 2011-dated IP69 row decoded as liquid "unknown" and a 2016-dated IP69 row decoded as "high-pressure-jet", which pins the as-of direction beyond argument.

### H - Access protection and object protection are coupled but not interchangeable

**Mechanism.** Two separate rules that only make sense together. (1) DECODE: the result gains an `access` field over {none, back-of-hand, finger, tool, wire, unspecified}. When an additional letter A-D is present it gives the access value; when it is absent, access is DERIVED from the first numeral (0->none, 1->back-of-hand, 2->finger, 3->tool, 4/5/6->wire); when the first numeral is X and no letter is present, access is "unspecified". Per IEC 60529 the additional letter may only be used when actual access protection is HIGHER than the first numeral implies, so a mark whose letter ranks below its numeral's implied access ("IP65C") is invalid and raises ValueError - a validity rule that couples the two positions. (2) SATISFACTION: `satisfies` scores three independent dimensions (object numeral, liquid numeral, access rank A<B<C<D), each with X in the REQUIREMENT meaning don't-care and X in the MARK meaning covers nothing numeric. The coupling produces a deliberate asymmetry: satisfies("IP2X", "IPXXB") is True (numeral 2 implies access B) while satisfies("IPXXB", "IP2X") is False (access B says nothing about the 12.5 mm object test). Also delete instruction.md's `# dust_tight == (first numeral == 6)` - dust_tight is now False for any mark whose first numeral is X, including "IPX8".

**The wrong answer it punishes.** Treat access as cosmetic - parse the letter, store it, never derive it from the numeral - so satisfies("IP2X", "IPXXB") returns False. Or treat the two dimensions as one ordering, so satisfies("IPXXB", "IP2X") returns True by symmetry. Or accept "IP65C" and let the letter override downward, giving access "tool" on a dust-tight enclosure. All three read naturally and all three are wrong.

**How it is recoverable.** environment/samples/nameplate_marks.csv carries one decoded row for each first numeral 0-6 with no additional letter, which pins the numeral->access derivation exactly; a row for "IP1XB" (letter above the numeral's implied access) showing access "finger"; and a rejected row for "IP65C" with the reason "additional letter lower than protection implied by first numeral". environment/samples/acceptance_log.csv carries the asymmetric pair explicitly - requirement IPXXB / part IP2X / accepted / "finger-safe by numeral", and requirement IP2X / part IPXXB / rejected / "access letter only; 12.5 mm object test not on file". environment/docs/ip-marking-guide.md explains that access to hazardous parts and ingress of solid objects are separate tests and that the additional letter is used only where access protection exceeds the numeral, but never prints the derivation table - that comes only from the corpus.

## Is it still solvable?

Every rule is pinned by a shipped artifact, and instruction.md points at all of them by path, so the work is reading rather than guessing. The guide states each principle in prose (cumulative ladder, jets vs immersion, element order, edition-in-force, access is a separate test); the editions JSON is the literal table with its effective dates and extends chain visible as keys; the two CSV corpora demonstrate every rule the guide leaves unenumerated, including one row per first numeral for the access derivation and explicit rejected rows with reasons. Nothing requires invention: a careful engineer who opens environment/docs and environment/samples recovers a single consistent implementation, and the only thing that punishes them is skipping those directories - which is exactly the intended split. Reward stays continuous over ~38 test functions in seven independent groups (basic decode ~8, X/letters/normalisation ~7, rejection rules ~4, access derivation and the IP65C validity rule ~5, edition as-of and delta merge ~5, satisfies ladder and 7/8 exceptions ~6, dual-mark union and access asymmetry ~5), so a model that nails decoding but misreads the coverage relation still scores around 0.6-0.65, and one that gets decoding plus two of the four cruxes lands near 0.75. A model that never opens environment/ fails the edition merge (which governs even the default no-date path), every X mark, every letter mark and all of satisfies, landing near 0.15-0.3. The stub keeps raising NotImplementedError from every method - including the new satisfies/covers - and loses its giveaway SOLID/LIQ dicts, so it still scores 0; the reference engine is rewritten in the same edit to embed the merged tables and the coverage relation (the corpus is implementer-facing evidence, not a runtime dependency, since solve.sh copies only engine/ into /app/engine). check_mutations.py also becomes meaningful for the first time: the coverage sets, the access ranks and the as-of date comparison give it real comparisons and boundaries to break.

## What was easy about it before

Nothing has to be inferred. instruction.md §2 prints both complete numeral tables verbatim, §3 states the exact ValueError predicate ("either of the first two significant characters is not a digit"), §3 states dust_tight == (first numeral == 6), and §4 hands over four worked examples that between them cover every branch the suite tests. Worse, the starting stub environment/engine/engine.py already contains the finished SOLID and LIQ dicts, so the model only has to write six lines of glue; the same giveaway is repeated in the __init__.py docstrings, conftest headers, Dockerfile comment and task.toml description ("Solid: 5=dust-protected, 6=dust-tight. Liquid 0-8 per IEC 60529"), and task.toml even lists the two intended failure cruxes in plain text. tests/test_outputs.py is 8 test functions / 25 cases, all of them direct restatements of the printed tables. There is no environment/docs or environment/samples at all - nothing in the environment has to be read. A mid-tier model solves this by transcription in one shot; check_mutations.py has almost nothing to mutate because the reference engine has one comparison and two dict lookups.

## Measured, not asserted

`tools/check_crux.py` implements each wrong answer described above,
runs the full behaviour suite against it, and reports what the suite
catches. This is its output:

```
baseline: reference engine passes all 188 tests

bitten     naive transcription (no environment/ read)       106/188 failed
             tests/test_outputs.py::test_a_dual_code_is_how_an_immersion_part_meets_a_jet_requirement[IPX5/IPX8-IPX6-False]
             tests/test_outputs.py::test_a_dual_code_is_how_an_immersion_part_meets_a_jet_requirement[IPX6/IPX8-IPX6-True]
             tests/test_outputs.py::test_a_dual_code_is_how_an_immersion_part_meets_a_jet_requirement[IPX6/IPX8-IPX8-True]
             tests/test_outputs.py::test_a_dual_marking_is_read_against_the_edition_in_force
             ... and 102 more

bitten     monotonic liquid ladder (crux B)                  13/188 failed
             tests/test_outputs.py::test_a_dual_code_is_how_an_immersion_part_meets_a_jet_requirement[IPX5/IPX8-IPX6-False]
             tests/test_outputs.py::test_continuous_immersion_does_not_cover_the_jet_tests[IP58-IP56]
             tests/test_outputs.py::test_continuous_immersion_does_not_cover_the_jet_tests[IP68-IP65]
             tests/test_outputs.py::test_continuous_immersion_does_not_cover_the_jet_tests[IPX8-IPX6]
             ... and 9 more

bitten     dual marking evaluated per code (crux B)           3/188 failed
             tests/test_outputs.py::test_dual_marking_meets_what_no_single_code_meets[IP2X/IPX5-IP25]
             tests/test_outputs.py::test_dual_marking_meets_what_no_single_code_meets[IP54/IPX8-IP58]
             tests/test_outputs.py::test_dual_marking_meets_what_no_single_code_meets[IP6X/IPX7-IP67]

bitten     X and letters treated as malformed (crux D)       79/188 failed
             tests/test_outputs.py::test_a_dual_code_is_how_an_immersion_part_meets_a_jet_requirement[IPX5/IPX8-IPX6-False]
             tests/test_outputs.py::test_a_dual_code_is_how_an_immersion_part_meets_a_jet_requirement[IPX6/IPX8-IPX6-True]
             tests/test_outputs.py::test_a_dual_code_is_how_an_immersion_part_meets_a_jet_requirement[IPX6/IPX8-IPX8-True]
             tests/test_outputs.py::test_a_dual_marking_is_read_against_the_edition_in_force
             ... and 75 more

bitten     current edition always (crux I)                   14/188 failed
             tests/test_outputs.py::test_a_dual_marking_is_read_against_the_edition_in_force
             tests/test_outputs.py::test_a_test_date_before_the_base_edition_raises
             tests/test_outputs.py::test_amendment_takes_effect_on_its_effective_date[2013-07-31-unknown]
             tests/test_outputs.py::test_decode_against_an_earlier_edition_keeps_the_unchanged_positions
             ... and 10 more

bitten     access never derived from the numeral (crux H)    29/188 failed
             tests/test_outputs.py::test_access_and_object_protection_are_not_interchangeable
             tests/test_outputs.py::test_access_is_derived_from_the_first_numeral[IP01-none]
             tests/test_outputs.py::test_access_is_derived_from_the_first_numeral[IP12-back-of-hand]
             tests/test_outputs.py::test_access_is_derived_from_the_first_numeral[IP21-finger]
             ... and 25 more

bitten     additional letter overrides downward (crux H)     11/188 failed
             tests/test_outputs.py::test_additional_letter_below_the_implied_access_is_refused[IP2XA]
             tests/test_outputs.py::test_additional_letter_below_the_implied_access_is_refused[IP4XB]
             tests/test_outputs.py::test_additional_letter_below_the_implied_access_is_refused[IP53C]
             tests/test_outputs.py::test_additional_letter_below_the_implied_access_is_refused[IP65C]
             ... and 7 more

every wrong default is punished by the suite
```

Two properties matter in that output. Every wrong answer is caught, so
the difficulty is real. And the scores in between are spread rather
than clustered at nought and one, so a partially correct implementation
earns partial credit - the reward stays continuous, which is what makes
the gap between a strong and a weak model measurable at all.
