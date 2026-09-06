// {{name}} substitution and brace escaping (spec section 2).

import { ScaffoldError } from "./errors.ts";
import { renderValue, type Answers } from "./values.ts";

const OPEN = "{{";
const CLOSE = "}}";

/**
 * 2.1 no whitespace is trimmed inside a reference, so `{{ name }}` looks for a
 * variable literally called " name ".
 * 2.3 `{{{{` is a literal `{{` and never opens a reference.
 */
export function interpolate(text: string, answers: Answers): string {
  const out: string[] = [];
  let i = 0;

  while (i < text.length) {
    if (text.startsWith(OPEN + OPEN, i)) {
      out.push(OPEN);
      i += 4;
      continue;
    }
    if (text.startsWith(CLOSE + CLOSE, i)) {
      out.push(CLOSE);
      i += 4;
      continue;
    }
    if (text.startsWith(OPEN, i)) {
      const end = text.indexOf(CLOSE, i + 2);
      if (end === -1) {
        out.push(text[i]!);
        i += 1;
        continue;
      }
      const name = text.slice(i + 2, end);
      if (!Object.hasOwn(answers, name)) {
        throw new ScaffoldError("UNKNOWN_VARIABLE", name); // 2.2
      }
      out.push(renderValue(answers[name]!));
      i = end + 2;
      continue;
    }
    out.push(text[i]!);
    i += 1;
  }

  return out.join("");
}
