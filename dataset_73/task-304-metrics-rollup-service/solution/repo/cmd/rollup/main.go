// Command rollup renders every capture in a directory into the documented report.
//
// Usage: run.sh <capture_dir> <output_json>
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"rollup/internal/rollup"
)

const suffix = ".capture"

func main() {
	if len(os.Args) != 3 {
		fmt.Fprintln(os.Stderr, "usage: run.sh <capture_dir> <output_json>")
		os.Exit(2)
	}
	if err := run(os.Args[1], os.Args[2]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run(captureDir, outPath string) error {
	entries, err := os.ReadDir(captureDir)
	if err != nil {
		return err
	}
	names := make([]string, 0, len(entries))
	for _, entry := range entries {
		if strings.HasSuffix(entry.Name(), suffix) {
			names = append(names, entry.Name())
		}
	}
	sort.Strings(names)

	report := make(map[string]rollup.Report, len(names))
	for _, name := range names {
		raw, err := os.ReadFile(filepath.Join(captureDir, name))
		if err != nil {
			return err
		}
		var capture rollup.Capture
		if err := json.Unmarshal(raw, &capture); err != nil {
			return fmt.Errorf("%s: %w", name, err)
		}
		report[strings.TrimSuffix(name, suffix)] = rollup.Run(capture)
	}

	encoded, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(outPath, append(encoded, '\n'), 0o644)
}
