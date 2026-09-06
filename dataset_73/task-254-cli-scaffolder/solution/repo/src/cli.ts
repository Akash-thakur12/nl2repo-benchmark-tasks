// CLI: node --experimental-strip-types src/cli.ts <plan_dir> <output_json>

import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { render, type Plan, type Report } from "./render.ts";

const SUFFIX = ".plan";

function main(argv: string[]): number {
  if (argv.length !== 2) {
    process.stderr.write("usage: run.sh <plan_dir> <output_json>\n");
    return 2;
  }
  const [planDir, outPath] = argv as [string, string];

  const report: Record<string, Report> = {};
  for (const name of readdirSync(planDir).sort()) {
    if (!name.endsWith(SUFFIX)) {
      continue;
    }
    const raw = readFileSync(join(planDir, name), "utf8");
    report[name.slice(0, -SUFFIX.length)] = render(JSON.parse(raw) as Plan);
  }

  writeFileSync(outPath, JSON.stringify(sortKeys(report), null, 2) + "\n", "utf8");
  return 0;
}

/** Emit object keys in sorted order so the report is byte-stable. */
function sortKeys(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(sortKeys);
  }
  if (value !== null && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const key of Object.keys(value as Record<string, unknown>).sort()) {
      out[key] = sortKeys((value as Record<string, unknown>)[key]);
    }
    return out;
  }
  return value;
}

process.exit(main(process.argv.slice(2)));
