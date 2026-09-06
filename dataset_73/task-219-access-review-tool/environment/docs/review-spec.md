# Access review specification

This document specifies how a quarterly access review is resolved. The tool must
reproduce it exactly.

## 1. The directory

**1.1** A user has a `name`, a `terminated` flag, a list of `groups` and a list
of `entitlements` held directly.

**1.2** A group has a `name`, a list of `members` naming other groups, and a list
of `entitlements`.

**1.3** A user belongs to the groups listed against them, and to every group
those belong to, however deep.

**1.4** A group named in a membership list that the directory does not define
records the error `UNKNOWN_GROUP` naming it, the first time it is reached, and is
otherwise ignored.

**1.5** A group that can reach itself through membership records the error
`MEMBERSHIP_CYCLE` naming it. Every such group is reported, in the order the
directory lists them, before anything else in this document happens. A cycle
does not stop membership resolving; a group already visited is simply not
visited again.

## 2. Effective access

**2.1** A user's access is every entitlement they hold directly, and every
entitlement of every group they belong to.

**2.2** The groups a user belongs to are reached **breadth first**: first the
groups listed against the user, in order; then the members of those groups, in
order; and so on. A group already reached is not reached again.

**2.3** An entitlement's `source` is `DIRECT` when the user holds it directly,
whatever else also grants it, and `GROUP` otherwise. `via` names the group it was
first reached through, and is null for a direct entitlement.

**2.4** A user's entitlements are listed in the order they were first reached:
the direct ones in the order the user lists them, then the group ones in the
order the groups were reached and, within a group, in the order that group lists
them.

## 3. Decisions

**3.1** A decision names a `user`, an `entitlement` and a verdict of `approve` or
`revoke`. Decisions are read in capture order, and are applied only once the
whole directory has been resolved.

**3.2** A decision naming a user the directory does not define records
`UNKNOWN_USER` naming the user, and is otherwise ignored.

**3.3** A decision naming a terminated user records `TERMINATED_USER` naming the
user, and is otherwise ignored.

**3.4** A decision naming an entitlement the user does not have records
`NO_SUCH_ACCESS` naming `user:entitlement`, and is otherwise ignored.

**3.5** A second decision for a pair that already has one records
`DUPLICATE_DECISION` naming `user:entitlement`. The first decision stands.

**3.6** These four checks are made in the order given above.

## 4. What a decision does

**4.1** `approve` leaves the access in place, in state `APPROVED`.

**4.2** `revoke` on a `DIRECT` entitlement removes it, in state `REVOKED`, unless
a group the user belongs to also grants it. In that case it stays, in state
`STILL_INHERITED`.

**4.3** `revoke` on a `GROUP` entitlement changes nothing: a review cannot take
away what a group grants. Its state is `STILL_INHERITED`.

## 5. Access nobody reviewed

**5.1** When the configuration's `default_revoke` is false, access with no
decision is left in place in state `UNREVIEWED`.

**5.2** When it is true, access with no decision is treated exactly as a
`revoke`, except that the states are `AUTO_REVOKED` in place of `REVOKED` and
`STILL_INHERITED` where 4.2 and 4.3 say so.

**5.3** Access is **effective** at the end of the review unless its state is
`REVOKED`, `AUTO_REVOKED` or `TERMINATED`.

## 6. Terminated users

**6.1** Every entitlement of a terminated user is in state `TERMINATED` and none
of it is effective, whatever any group grants and whatever any decision said.

## 7. Segregation of duties

**7.1** The configuration lists pairs of entitlements that must not be held
together. A pair is unordered, and the configuration will not list the same pair
twice.

**7.2** A user who still effectively holds both entitlements of a pair records a
violation naming them in the order the configuration lists them.

**7.3** Violations are listed by user in directory order, and within a user by
pair in configuration order.

## 8. Report

**8.1** `access` lists every user's entitlements, users in directory order and
entitlements in the order of 2.4, each with `user`, `entitlement`, `source`,
`via`, `state` and `effective`.

**8.2** `violations` lists `{user, entitlements}` as section 7 describes.

**8.3** `errors` lists each error with `code` and `detail`, the cycle errors of
1.5 first, then the rest in the order they happened.
