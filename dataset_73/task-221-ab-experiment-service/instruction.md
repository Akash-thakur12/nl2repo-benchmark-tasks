We run about forty experiments at a time and the assignment logic lives in three
places, none of which agree. Last quarter an experiment reported a nine per cent
lift that turned out to be the same two thousand people being re-bucketed every
deploy, and the quarter before that a "staff excluded" experiment shipped a
broken checkout to our own support team for a day and a half.

We want one service that decides assignments, and we want to be able to replay a
day of traffic through it and see exactly what it would have done.

## What to build

A repository rooted at `/app` whose entry point is `/app/run.sh`, invoked as:

    ./run.sh <capture_dir> <output_json>

It reads every `*.experiments` file in the directory and writes one JSON report.
`/app/docs/report-format.md` fixes the shape of the capture and of the report -
that part is not negotiable, because other tools read it. Everything else is
yours: how you lay the repository out, how you decide which variant a user
lands in, and what you do about the awkward cases below.

`run.sh` must be executable and must work from any working directory.
`/app/samples/` holds a handful of captures to try it on. There is no expected
output shipped with them: there is more than one right answer here.

## How it should behave

**Assignment is a decision about a person, not a dice roll.** The same user
asking about the same experiment must land in the same variant every time -
within a run, across runs, and on a different machine. Two people looking at the
same report should see the same numbers. How you achieve that is up to you; a
hash of something stable is the usual answer, and the capture gives you a salt
if you want one.

**Experiments that are not running assign nobody.** A stopped experiment and a
draft experiment both hand back no variant, and they are different situations,
so say which.

**Excluded users are excluded.** If an experiment lists a user, that user never
receives a variant from it, whatever else is true.

**Traffic is a gate, not a variant.** An experiment on fifty per cent traffic
should let about half the requests through to variant selection and turn the
rest away; at zero per cent nobody gets in, at a hundred everybody does. Whether
you gate before or after you look at exclusivity is your call - both are
defensible, and the report has a reason code for each.

**Experiments in the same exclusion group must not overlap.** If a user has
already been given a variant by one experiment in a group, another experiment in
that group must not also give them one. Requests are processed in order, so the
first one to reach a user wins.

**Weights mean something.** Over a few hundred users, an experiment with two
equally weighted variants at full traffic should put a decent number of people
in each. It does not have to be exactly half. It does have to be both. A variant
weighted zero gets nobody at all.

**A request for an experiment nobody declared** is not a crash. Report it, and
carry on.

## Success criteria

1. `/app/run.sh` exists, is executable, and runs to completion on a directory of
   captures it has not seen before.
2. The report has the shape `/app/docs/report-format.md` describes: one entry per
   capture, exactly the three documented keys, one assignment per request in
   request order, and only documented reason codes.
3. Every variant it assigns is one the experiment declares, and every assignment
   without a variant gives a reason that is not `ASSIGNED`.
4. The same user asking about the same experiment always gets the same answer
   within a capture, and running the tool twice over the same captures produces
   an identical report.
5. Experiments that are stopped, in draft, or on zero traffic assign nobody, and
   an experiment on full traffic with nobody excluded assigns everybody who asks.
6. A user an experiment excludes never receives a variant from it.
7. No user receives a variant from two experiments in the same exclusion group.
8. Over a capture of several hundred users, a running experiment at full traffic
   with equally weighted variants puts at least one twentieth of its users in
   every variant it declares, and no experiment ever puts anybody in a variant
   weighted zero.
9. The summary counts every experiment the capture declares, with a count per
   declared variant and an unassigned count, and those numbers agree with the
   assignments the report itself lists.
10. A request naming an experiment that does not exist is reported as an error
    and as an unassigned request, and does not stop the run.

## Notes

Use only the Python standard library.
