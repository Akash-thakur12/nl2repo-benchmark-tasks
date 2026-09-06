# rollup

Rolls raw metric samples into retention tiers and reports every row it would
store, without writing to any store.

    ./run.sh <capture_dir> <output_json>

Standard library only, so `go run` works offline with nothing to fetch.

## Layout

    internal/rollup/series.go     series keys and grouping
    internal/rollup/arith.go      floor division and half-to-even rounding
    internal/rollup/first.go      the first tier, from raw samples
    internal/rollup/later.go      every tier above it, from the tier below
    internal/rollup/rollup.go     assembly and row ordering
    cmd/rollup/main.go            directory walk and JSON output

Behaviour is specified in `docs/rollup-spec.md`; section numbers appear in
comments beside the rule each piece implements.

Note on arithmetic: the specification asks for floor division and for exact
halves to round to the even neighbour. Go's `/` truncates toward zero and
`math.Round` sends halves away from zero, so neither is used here.
