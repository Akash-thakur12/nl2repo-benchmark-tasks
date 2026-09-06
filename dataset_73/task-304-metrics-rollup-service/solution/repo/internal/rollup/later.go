package rollup

import "sort"

// Every tier above the first, computed from the tier immediately below it and
// never from the raw samples again (spec section 4).

// bucketRows groups lower rows by the higher tier's window, keyed on each lower
// row's own window start (spec 4.2). That is what makes a tier which is not a
// multiple of the one below it behave differently from re-reading the raw
// samples.
func bucketRows(rows []Row, seconds int64) ([]int64, map[int64][]Row) {
	groups := make(map[int64][]Row)
	for _, row := range rows {
		start := windowStart(row.Window, seconds)
		groups[start] = append(groups[start], row)
	}
	starts := make([]int64, 0, len(groups))
	for start := range groups {
		starts = append(starts, start)
	}
	sort.Slice(starts, func(i, j int) bool { return starts[i] < starts[j] })
	for _, start := range starts {
		members := groups[start]
		sort.SliceStable(members, func(i, j int) bool {
			return members[i].Window < members[j].Window
		})
		groups[start] = members
	}
	return starts, groups
}

// rollCounter implements spec 4.3.
func rollCounter(rows []Row, seconds int64) []Row {
	starts, groups := bucketRows(rows, seconds)
	out := make([]Row, 0, len(starts))
	for _, start := range starts {
		var total int64
		for _, row := range groups[start] {
			total += row.Delta
		}
		out = append(out, Row{Window: start, Delta: total})
	}
	return out
}

// rollGauge implements spec 4.4. The average is recomputed from the totals; it
// is never the mean of the lower averages.
func rollGauge(rows []Row, seconds int64) []Row {
	starts, groups := bucketRows(rows, seconds)
	out := make([]Row, 0, len(starts))
	for _, start := range starts {
		members := groups[start]
		low, high := members[0].Min, members[0].Max
		var total, count int64
		for _, row := range members {
			if row.Min < low {
				low = row.Min
			}
			if row.Max > high {
				high = row.Max
			}
			total += row.Sum
			count += row.Count
		}
		out = append(out, Row{
			Window: start, Min: low, Max: high,
			Last:  members[len(members)-1].Last, // the latest lower window
			Count: count, Sum: total, Avg: roundHalfEven(total, count),
		})
	}
	return out
}

// rollHistogram implements spec 4.5.
func rollHistogram(rows []Row, seconds int64) []Row {
	starts, groups := bucketRows(rows, seconds)
	out := make([]Row, 0, len(starts))
	for _, start := range starts {
		members := groups[start]
		boundaries := append([]int64(nil), members[0].Boundaries...)
		counts := make([]int64, len(boundaries))
		for _, row := range members {
			for index, value := range row.Counts {
				counts[index] += value
			}
		}
		out = append(out, Row{Window: start, Boundaries: boundaries, Counts: counts})
	}
	return out
}
