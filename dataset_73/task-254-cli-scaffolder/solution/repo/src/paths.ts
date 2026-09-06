// Path normalisation and safety (spec section 4.5).

import { ScaffoldError } from "./errors.ts";

/**
 * Collapses repeated slashes and drops `.` segments, resolves `..` inside the
 * tree, and refuses anything absolute, escaping or empty.
 */
export function normalisePath(path: string): string {
  if (path.startsWith("/")) {
    throw new ScaffoldError("UNSAFE_PATH", path);
  }

  const parts: string[] = [];
  for (const segment of path.split("/")) {
    if (segment === "" || segment === ".") {
      continue;
    }
    if (segment === "..") {
      if (parts.length === 0) {
        throw new ScaffoldError("UNSAFE_PATH", path);
      }
      parts.pop();
      continue;
    }
    parts.push(segment);
  }

  if (parts.length === 0) {
    throw new ScaffoldError("UNSAFE_PATH", path);
  }
  return parts.join("/");
}
