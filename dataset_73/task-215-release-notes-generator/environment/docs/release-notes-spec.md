# Release notes specification

This document specifies how release notes are derived from a range of commits.
The generator must reproduce it exactly.

## 1. History and configuration

**1.1** A capture holds a configuration and a list of commits in the order they
were made, oldest first.

**1.2** The configuration names the previous version, the sections to emit and
their order, and which commit types are included.

**1.3** Commits are read in history order. Nothing in this specification depends
on commit timestamps.

## 2. Reading a commit subject

**2.1** A conventional subject is `type(scope)!: description`, where:

- `type` is one or more lowercase ASCII letters,
- `(scope)` is optional; when present the scope is one or more characters that
  are not `)` and not empty,
- `!` is optional,
- the separator is a colon followed by exactly one space,
- `description` is everything after that separator, with no leading or trailing
  whitespace.

**2.2** A subject that does not match this shape is not conventional. Its commit
is skipped with reason `UNCONVENTIONAL`, and it takes no part in anything else:
not the version bump, not the sections, not the contributors.

**2.3** A conventional subject whose description is empty after trimming is also
skipped with reason `UNCONVENTIONAL`.

**2.4** If the description ends with a pull request reference - a space, then
`(#` , then one or more digits, then `)`, at the very end and nowhere else - that
reference is removed from the description and its number is the entry's pull
request. A reference anywhere but at the end stays in the description.

**2.5** If the commit record names a merged pull request, that number is the
entry's pull request and it wins over any reference found in the subject, which
is still removed from the description.

**2.6** An entry with neither has a null pull request.

## 3. Breaking changes

**3.1** A commit is breaking if its subject carries `!` before the colon.

**3.2** A commit is also breaking if any line of its body, after stripping
trailing whitespace from the line, begins with `BREAKING CHANGE: ` or
`BREAKING-CHANGE: `. The text is matched exactly, including case; the line must
begin with it.

**3.3** The text after that prefix, trimmed, is the breaking note. A commit
breaking only because of `!` has no note, and its description is used instead.

**3.4** A commit whose type is excluded by the configuration is not breaking,
whatever its subject or body says. Exclusion is decided first.

## 4. The version bump

**4.1** The previous version is `major.minor.patch`, three non-negative
integers.

**4.2** The bump is decided by the entries that survive section 5, not by the
commits as read:

- if any surviving entry is breaking, the bump is **major**,
- otherwise if any surviving entry has type `feat`, the bump is **minor**,
- otherwise if there is at least one surviving entry, the bump is **patch**,
- otherwise there is no bump and the version is unchanged.

**4.3** A major bump increases `major` by one and sets `minor` and `patch` to
zero. A minor bump increases `minor` by one and sets `patch` to zero. A patch
bump increases `patch` by one.

**4.4** While `major` is zero the project is unstable, and a breaking change is
only a **minor** bump. `0.4.1` with a breaking change becomes `0.5.0`, not
`1.0.0`. Every other rule is unchanged.

## 5. Entries, deduplication and reverts

**5.1** Each commit that is conventional and whose type is included contributes
one entry, carrying its type, scope (null when absent), description, pull
request, breaking flag and the commit's sha.

**5.2** A commit whose type is not in the configuration's included types is
skipped with reason `TYPE_EXCLUDED`. Exclusion is decided before anything else
in this section, reverts included.

**5.3** Two entries are duplicates when their type, scope and description are all
equal. Only the first is kept; each later one is skipped with reason
`DUPLICATE`. The kept entry is not modified by the duplicate in any way.

**5.4** A commit of type `revert` is never an entry of its own. Its body is
searched for a line beginning with `Reverts: `, whose remainder, trimmed, is a
sha.

**5.5** If that sha belongs to an entry that survives so far, that entry is
removed and both commits are skipped: the reverted one with reason `REVERTED`
and the revert itself with reason `REVERT`.

**5.6** If the sha names no surviving entry - because no commit in this range has
it, or because its entry was already removed or skipped - the revert is recorded
as the error `UNKNOWN_REVERT` naming the sha, and the revert commit is skipped
with reason `REVERT`.

**5.7** A `revert` commit with no `Reverts: ` line is recorded as the error
`MALFORMED_REVERT` naming the revert's own sha, and is skipped with reason
`REVERT`.

**5.8** Reverts are applied in history order, as each is read.

## 6. Sections

**6.1** The configuration lists sections in order, each with a commit type and a
title. A section is emitted only if at least one surviving entry has its type.

**6.2** Entries within a section keep history order.

**6.3** A surviving entry whose type has no configured section is not lost: it is
collected into a final section titled `Other`, in history order. That section is
emitted only if it has entries, and always comes last.

**6.4** The same type never appears in two sections; the configuration will not
ask for that.

## 7. Contributors

**7.1** Contributors are the authors of surviving entries, deduplicated by
author name, in the order each first appears.

**7.2** The author of a commit that was skipped for any reason does not become a
contributor by that commit. The author of a revert commit likewise contributes
nothing.

## 8. Skipped commits and errors

**8.1** `skipped` lists each skipped commit as its sha and reason, in the order
the commits were read, not the order the reasons were decided. A commit is
skipped for exactly one reason; where more than one could apply, the first of
`UNCONVENTIONAL`, `TYPE_EXCLUDED`, `REVERT`, `REVERTED`, `DUPLICATE` applies.

**8.2** `errors` lists each error in the order it was found, with `code` and
`detail`.

## 9. Report

**9.1** `version` is the new version as `major.minor.patch`.

**9.2** `bump` is `major`, `minor`, `patch` or `none`.

**9.3** `sections` is a list of `{title, entries}`, each entry
`{sha, type, scope, description, pr, breaking}`.

**9.4** `breaking` lists the breaking notes of surviving entries in history
order, each `{sha, note}`.

**9.5** `contributors` is a list of names.

**9.6** `skipped` is a list of `{sha, reason}` and `errors` a list of
`{code, detail}`.
