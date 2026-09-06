# Write-ahead log format, v1  — SUPERSEDED

    !!  SUPERSEDED. Kept only so that old incident write-ups still resolve.
    !!  Do not implement from this file.

## Record shape

`wal.log` holds one JSON array per line:

```
[op, key, val]
```

`op` is `"p"` or `"d"`. Delete records are two elements long, `["d", key]`.
There is no sequence number: v1 records carry no ordering information of their
own beyond their position in the file.

## Recovery

Recovery replays every record in the file, in file order, applying each one to
the MemTable as though the client had just issued it. Later lines overwrite
earlier lines, so the last record for a key wins. Nothing is skipped and nothing
is validated; the log is assumed to end exactly where the last successful write
ended.

## Truncation

`truncate()` closes the log and reopens it for writing, which empties it.
