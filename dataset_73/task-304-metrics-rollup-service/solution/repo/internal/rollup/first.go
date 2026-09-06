package rollup

// The first tier, computed from the raw samples (spec section 3).

// Row is one stored row. Only the fields its type defines are populated; the
// assembler turns it into the documented object.
type Row struct {
	Window     int64
	Delta      int64
	Min        int64
	Max        int64
	Last       int64
	Count      int64
	Sum        int64
	Avg        int64
	Boundaries []int64
	Counts     []int64
}

// counterRows implements spec 3.1. A counter is cumulative, so a window reports
// the increase across it. The baseline carries over from the previous window,
// and a value below the baseline is a reset that contributes its whole value.
func counterRows(samples []Sample, seconds int64) []Row {
	var rows []Row
	var baseline int64
	haveBaseline := false
	var current int64
	haveWindow := false
	var delta int64

	for _, sample := range samples {
		start := windowStart(sample.T, seconds)
		if !haveWindow {
			current, haveWindow = start, true
		} else if start != current {
			rows = append(rows, Row{Window: current, Delta: delta})
			current, delta = start, 0
		}
		switch {
		case !haveBaseline: // 3.1.1 the first sample ever contributes nothing
		case sample.Value >= baseline:
			delta += sample.Value - baseline // 3.1.2
		default:
			delta += sample.Value // 3.1.2 a reset
		}
		baseline, haveBaseline = sample.Value, true
	}
	if haveWindow {
		rows = append(rows, Row{Window: current, Delta: delta})
	}
	return rows
}

// gaugeRows implements spec 3.2.
func gaugeRows(samples []Sample, seconds int64) []Row {
	buckets := make(map[int64][]int64)
	var order []int64
	for _, sample := range samples {
		start := windowStart(sample.T, seconds)
		if _, seen := buckets[start]; !seen {
			order = append(order, start)
		}
		buckets[start] = append(buckets[start], sample.Value)
	}

	rows := make([]Row, 0, len(order))
	for _, start := range order {
		values := buckets[start]
		low, high, total := values[0], values[0], int64(0)
		for _, value := range values {
			if value < low {
				low = value
			}
			if value > high {
				high = value
			}
			total += value
		}
		count := int64(len(values))
		rows = append(rows, Row{
			Window: start, Min: low, Max: high, Last: values[len(values)-1],
			Count: count, Sum: total, Avg: roundHalfEven(total, count),
		})
	}
	return rows
}

// histogramRows implements spec 3.3. A disagreement about boundaries anywhere in
// the series takes the whole series out, at every tier.
func histogramRows(samples []Sample, seconds int64) ([]Row, bool) {
	boundaries := samples[0].Boundaries
	for _, sample := range samples {
		if !sameInts(sample.Boundaries, boundaries) { // 3.3.2
			return nil, false
		}
	}

	buckets := make(map[int64][]int64)
	var order []int64
	for _, sample := range samples {
		start := windowStart(sample.T, seconds)
		running, seen := buckets[start]
		if !seen {
			running = make([]int64, len(boundaries))
			order = append(order, start)
		}
		for index, count := range sample.Counts {
			running[index] += count // 3.3.3
		}
		buckets[start] = running
	}

	rows := make([]Row, 0, len(order))
	for _, start := range order {
		rows = append(rows, Row{
			Window: start, Boundaries: append([]int64(nil), boundaries...),
			Counts: buckets[start],
		})
	}
	return rows, true
}

func sameInts(a, b []int64) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}
