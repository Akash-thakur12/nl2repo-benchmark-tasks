# Drift specification

This document specifies how declared configuration is compared against live
state. The tool must reproduce it exactly.

## 1. Resources

**1.1** A resource has an `id` and a body. The declared side and the live side
are each a list of resources.

**1.2** A resource id declared twice produces the error `DUPLICATE_DECLARED`
naming it; the first declaration stands and the later one is discarded. A live
id seen twice produces `DUPLICATE_LIVE` under the same rule.

**1.3** A resource declared but not live is reported as `MISSING`, with no path.

**1.4** A resource live but not declared is reported as `UNMANAGED`, with no
path.

**1.5** A resource on both sides is compared field by field.

## 2. Paths

**2.1** A path names one place inside a body. The root is the empty path.

**2.2** A child of an object extends the path with `.name`, so the path of `b`
inside `{"a": {"b": 1}}` is `a.b`.

**2.3** An element of a list extends the path with `[index]`, so the first
element of `a` is `a[0]`.

**2.4** A leading `.` is never emitted: the top-level field `a` has the path
`a`, not `.a`.

## 3. Comparison

**3.1** Two objects are compared by the union of their keys, in ascending key
order.

**3.2** A key present on one side only is `ADDED` when it is live and `REMOVED`
when it is declared, reported at that key's path.

**3.3** Two lists are compared element by element up to the shorter length. A
longer live list reports `ADDED` for each extra element, a longer declared list
reports `REMOVED`.

**3.4** Two values of different JSON types are `CHANGED`, and the descent stops
there. An object is never compared against a list.

**3.5** Two scalars are `CHANGED` when they differ. Comparison is type-strict:
the string `"1"` is not the number `1`, and `true` is not `1`.

**3.6** An object with no keys and a missing key are not the same thing. The
first is a value, the second is an absence.

## 4. Ignoring

**4.1** An ignore rule is a path with optional `*` segments. `tags.*` matches
`tags.owner` but not `tags` itself and not `tags.owner.sub`.

**4.2** A `*` matches exactly one segment, whether that segment is an object key
or a list index. `disks[*].size` matches `disks[0].size`.

**4.3** A path that matches any ignore rule is not reported, and neither is
anything beneath it.

**4.4** Ignore rules apply to a resource's paths only. A rule can never suppress
a `MISSING` or `UNMANAGED` resource.

## 5. Report

**5.1** `drift` lists every finding, ordered by resource id ascending, then by
path ascending, with the empty path sorting first.

**5.2** A finding has `resource`, `path`, `kind` and, for `CHANGED`, `declared`
and `live`. `MISSING`, `UNMANAGED`, `ADDED` and `REMOVED` carry neither.

**5.3** `counts` reports how many findings there are of each kind, as an object
with one entry per kind that occurred, keyed by kind.

**5.4** `errors` lists duplicates in the order they were read, with `code` and
`detail`.
