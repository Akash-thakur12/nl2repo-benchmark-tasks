> **SUPERSEDED.** These are the v1 replay notes, kept only for the change
> history. They are replaced in full by `aof-recovery.md`. Do not implement
> from this file.

# Replay notes (v1, draft)

## The ordering problem

`LPUSH` inserts at the *head* of the list, but the log is written in *arrival*
order, oldest first. Replaying the file forwards therefore reconstructs the list
backwards: each replayed `LPUSH` pushes onto a head that already contains the
elements that were pushed after it.

The fix is to walk the record stream in **reverse** for list keys, so that the
newest `LPUSH` is applied first and ends up deepest — or, equivalently, to
reverse each reconstructed list once replay finishes.

Worked example:

```
  log:  ["lpush", "jobs", "a"]
        ["lpush", "jobs", "b"]

  forward replay:   a -> [a],  b -> [b, a]      # wrong, live order was [a, b]
  reverse replay:   b -> [b],  a -> [a, b]      # matches the live store
```

`RPOP` records have to be reversed along with them, otherwise a replayed pop
removes the element at the wrong end.

## Open questions before this ships

- Confirm the worked example above against a captured log. (TODO, nobody has
  done this.)
- Decide what to do about half-written records at the end of the file.
