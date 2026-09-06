package rollup

// Assembly and row ordering (spec section 5).

// Report is the per-capture output.
type Report struct {
	Rows   []map[string]any `json:"rows"`
	Errors []ReportError    `json:"errors"`
}

// ReportError names a series that dropped out.
type ReportError struct {
	Code   string `json:"code"`
	Series string `json:"series"`
}

// Run rolls one capture into the documented report.
func Run(capture Capture) Report {
	grouped := group(capture.Samples)
	tiers := capture.Tiers

	errors := make([]ReportError, 0)
	stacks := make(map[string][][]Row)
	kinds := make(map[string]string)

	for _, key := range sortedKeys(grouped) { // 5.3 errors ordered by series key
		entry := grouped[key]
		var first []Row
		switch entry.kind {
		case "counter":
			first = counterRows(entry.samples, tiers[0].Seconds)
		case "gauge":
			first = gaugeRows(entry.samples, tiers[0].Seconds)
		default:
			rows, ok := histogramRows(entry.samples, tiers[0].Seconds)
			if !ok {
				errors = append(errors, ReportError{Code: "BUCKET_MISMATCH", Series: key})
				continue
			}
			first = rows
		}

		stack := [][]Row{first}
		for _, tier := range tiers[1:] { // 4.1 always from the tier below
			previous := stack[len(stack)-1]
			switch entry.kind {
			case "counter":
				stack = append(stack, rollCounter(previous, tier.Seconds))
			case "gauge":
				stack = append(stack, rollGauge(previous, tier.Seconds))
			default:
				stack = append(stack, rollHistogram(previous, tier.Seconds))
			}
		}
		stacks[key] = stack
		kinds[key] = entry.kind
	}

	keys := make([]string, 0, len(stacks))
	for key := range stacks {
		keys = append(keys, key)
	}
	sortStrings(keys)

	rows := make([]map[string]any, 0)
	for index, tier := range tiers { // 5.1 tier, then series, then window
		for _, key := range keys {
			for _, row := range stacks[key][index] {
				rows = append(rows, encode(tier.Name, key, kinds[key], row))
			}
		}
	}
	return Report{Rows: rows, Errors: errors}
}

// encode turns a row into the object shape its type defines (spec 5.2).
func encode(tier, key, kind string, row Row) map[string]any {
	out := map[string]any{
		"tier": tier, "series": key, "type": kind, "window": row.Window,
	}
	switch kind {
	case "counter":
		out["delta"] = row.Delta
	case "gauge":
		out["min"] = row.Min
		out["max"] = row.Max
		out["last"] = row.Last
		out["count"] = row.Count
		out["sum"] = row.Sum
		out["avg"] = row.Avg
	default:
		out["boundaries"] = row.Boundaries
		out["counts"] = row.Counts
	}
	return out
}
