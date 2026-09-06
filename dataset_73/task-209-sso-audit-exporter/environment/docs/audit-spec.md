# Audit export specification

This document specifies how raw SSO sign-in events become an audit export. The
tool must reproduce it exactly.

This document and `docs/capture-format.md` and `docs/location-registry.md` are
the normative set. Nothing under `docs/retired/` or `tools/` is normative; where
they disagree with this document or with the registry, they are simply out of
date.

Where this document is silent on a boundary, `/app/samples/2029Q1/` is the
authority. It is a real export that Security accepted, and its numbers say what
the rule is.

## 1. Ordering

**1.1** Events are considered in ascending `t`. Two events with the same `t` are
considered in ascending `id`.

**1.2** The order they appear in the capture has no effect on anything.

## 2. Locations

**2.1** A location has integer `x` and `y` coordinates in kilometres on a flat
grid, as of the moment being measured. `docs/location-registry.md` defines which
coordinates are in force when.

**2.2** The distance between two locations is the straight-line distance between
the coordinates in force, reported as a whole number of kilometres.

**2.3** An event naming a location the capture does not define produces the
error `UNKNOWN_LOCATION` naming it. That event is discarded and takes no further
part.

## 3. Duplicates

**3.1** Two events are duplicates when they share a `user` and a `session`.

**3.2** The **first** such event in consideration order is accepted. A later one
is a duplicate when it falls within `dedup_window_seconds` of the accepted one.

**3.3** A later event outside that window is not a duplicate; it is accepted.

**3.4** A duplicate is recorded and then discarded. It never establishes a
location and is never flagged for travel.

## 4. Impossible travel

**4.1** Only a **successful** sign-in establishes where a user was. A failed
sign-in is accepted and exported, but it neither sets nor uses a previous
location.

**4.2** A successful sign-in is compared against that user's previous successful
accepted sign-in. If the user has none, nothing is flagged and this one becomes
the previous.

**4.3** Let `km` be the distance between the two locations and `seconds` the
difference in `t`. The sign-in is impossible when the speed it implies exceeds
the limit in force. `docs/location-registry.md` defines which limit is in force
for a given sign-in.

**4.4** The flag is recorded against the **later** event. The earlier one is
never revisited.

## 5. Report

**5.1** `accepted` lists the ids of every event that was neither discarded for an
unknown location nor recorded as a duplicate, in consideration order.

**5.2** `duplicates` lists the ids of duplicate events, in consideration order.

**5.3** `impossible` lists one entry per flagged sign-in, in consideration order,
each with `id`, `user`, `from` and `to` (the location names), `km` and
`seconds`.

**5.4** `errors` lists each unknown location in consideration order, with `code`
and `detail`.
