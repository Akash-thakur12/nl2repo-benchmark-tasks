# Schema registry specification

This document specifies how the registry stores schemas and decides whether one
may replace another. The replay tool must reproduce it exactly.

## 1. Schemas

**1.1** A schema is an ordered list of fields. A field has a `name`, a `type`,
and optionally a `default`.

**1.2** The types are `int`, `long`, `float`, `double`, `string`, `boolean` and
`bytes`. No other type appears.

**1.3** Two schemas are the same schema when their field lists are equal:
the same fields, in the same order, with the same names, the same types, and the
same defaults - where having no default and having a default of `null` are
different.

**1.4** Field order is part of the schema. Two schemas with the same fields in a
different order are different schemas.

## 2. Reading data written with another schema

**2.1** A type may be **promoted** when data written as one type can be read as
another. The promotions are, and are only:

    int    -> long, float, double
    long   -> float, double
    float  -> double
    string -> bytes
    bytes  -> string

A type is always promotable to itself. Promotion is not symmetric: `long` does
not promote to `int`.

**2.2** A schema R can read data written with a schema W when both hold:

- for every field of W whose name also appears in R, the W type promotes to the
  R type;
- every field of R whose name does not appear in W has a default.

**2.3** A field of W whose name does not appear in R is ignored, and is never a
reason to fail.

## 3. Compatibility levels

**3.1** A level says which direction, or directions, must hold when a new schema
`N` is offered for a subject whose existing schema is `E`:

| level | requires |
|-------|----------|
| `NONE` | nothing |
| `BACKWARD` | `N` can read data written with `E` |
| `FORWARD` | `E` can read data written with `N` |
| `FULL` | both |

**3.2** Each of `BACKWARD`, `FORWARD` and `FULL` has a transitive form named by
appending `_TRANSITIVE`, which requires the same thing.

**3.3** A non-transitive level checks `N` against the latest version of the
subject only. A transitive level checks `N` against **every** version of the
subject. `NONE` checks nothing.

**3.4** A version that has been deleted is never checked against, at any level.

**3.5** A subject with no versions to check against is compatible with anything.

## 4. Subjects and versions

**4.1** A subject's compatibility level is the one set for it, or the
configuration's default when none has been set.

**4.2** Registering a schema under a subject that does not exist creates the
subject.

**4.3** If the schema offered is the same schema as one of the subject's
versions that has not been deleted, no version is created: the registration
returns that version and its id, and reports `created` as false.

**4.4** Otherwise the schema is checked for compatibility. If it fails, nothing
is created, the registration returns a null version and a null id, and the error
`INCOMPATIBLE` is recorded naming the subject.

**4.5** Otherwise a new version is created. Version numbers within a subject
start at 1 and increase by one for each version created. A number is never
reused, even after the version it belonged to is deleted.

**4.6** Schema ids are global to the registry, not to a subject. The first time a
schema is stored it takes the next id, starting at 1. The same schema registered
again, under any subject, takes the id it already has.

## 5. Operations

**5.1** `register` behaves as section 4 describes.

**5.2** `check` reports whether the schema would be accepted for the subject
under its level, without changing anything. A check against a subject that does
not exist, or one with no undeleted versions, is compatible and is not an error.

**5.3** `lookup` reports the version and id under which the given schema is
registered in the subject, ignoring deleted versions. If the subject does not
exist, or the schema is not among its versions, both are null and the error
`UNKNOWN_SUBJECT` is recorded naming the subject only when the subject itself
does not exist.

**5.4** `delete_version` marks a version deleted. A deleted version keeps its
number, is not listed among the subject's versions, is never checked against,
and cannot be looked up or deleted again. Deleting from a subject that does not
exist records `UNKNOWN_SUBJECT` naming the subject; deleting a version that does
not exist or is already deleted records `UNKNOWN_VERSION` naming the version as
a string.

**5.5** `set_compatibility` sets a subject's level. A level that is not one of
the seven names records `INVALID_LEVEL` naming the level, and changes nothing.
Setting a level for a subject that does not exist creates the subject with no
versions.

## 6. Report

**6.1** `results` lists one entry per operation, in capture order:

- `register`: `{op, subject, version, id, created}`
- `check`: `{op, subject, compatible}`
- `lookup`: `{op, subject, version, id}`
- `delete_version`: `{op, subject, version}`
- `set_compatibility`: `{op, subject, level}`

For a rejected registration `version` and `id` are null and `created` is false.
For a delete that did not happen `version` is null. For a `set_compatibility`
that was refused, `level` is the level the subject still has.

**6.2** `subjects` lists every subject in the order each first appeared, with
`name`, `compatibility` (the level in force at the end) and `versions`, a list of
`{version, id}` for the versions that remain, in increasing version order.

**6.3** `errors` lists each error in the order it happened, with `code`
(`UNKNOWN_SUBJECT`, `UNKNOWN_VERSION`, `INCOMPATIBLE` or `INVALID_LEVEL`) and
`detail`.
