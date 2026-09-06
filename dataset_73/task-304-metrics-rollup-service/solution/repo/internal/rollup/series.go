package rollup

import (
	"sort"
	"strings"
)

// Sample is one raw reading from the capture.
type Sample struct {
	T          int64             `json:"t"`
	Name       string            `json:"name"`
	Labels     map[string]string `json:"labels"`
	Type       string            `json:"type"`
	Value      int64             `json:"value"`
	Boundaries []int64           `json:"boundaries"`
	Counts     []int64           `json:"counts"`
}

// Tier is one retention level.
type Tier struct {
	Name    string `json:"name"`
	Seconds int64  `json:"seconds"`
}

// Capture is a whole input file.
type Capture struct {
	Tiers   []Tier   `json:"tiers"`
	Samples []Sample `json:"samples"`
}

// SeriesKey renders spec 1.3: the name, then ",key=value" for each label in
// ascending key order. Label order in the capture is not significant (1.2).
func SeriesKey(name string, labels map[string]string) string {
	if len(labels) == 0 {
		return name
	}
	keys := make([]string, 0, len(labels))
	for key := range labels {
		keys = append(keys, key)
	}
	sort.Strings(keys)

	var builder strings.Builder
	builder.WriteString(name)
	for _, key := range keys {
		builder.WriteString(",")
		builder.WriteString(key)
		builder.WriteString("=")
		builder.WriteString(labels[key])
	}
	return builder.String()
}

type series struct {
	kind    string
	samples []Sample
}

// group buckets samples by series and sorts each bucket by time, because the
// capture is written in whatever order the collector produced.
func group(samples []Sample) map[string]*series {
	grouped := make(map[string]*series)
	for _, sample := range samples {
		key := SeriesKey(sample.Name, sample.Labels)
		entry, seen := grouped[key]
		if !seen {
			entry = &series{kind: sample.Type}
			grouped[key] = entry
		}
		entry.samples = append(entry.samples, sample)
	}
	for _, entry := range grouped {
		sort.SliceStable(entry.samples, func(i, j int) bool {
			return entry.samples[i].T < entry.samples[j].T
		})
	}
	return grouped
}

func sortedKeys(m map[string]*series) []string {
	keys := make([]string, 0, len(m))
	for key := range m {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}

func sortStrings(values []string) {
	sort.Strings(values)
}
