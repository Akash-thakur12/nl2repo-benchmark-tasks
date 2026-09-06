// Prompt resolution (spec section 1).

import { ScaffoldError } from "./errors.ts";
import type { Answers, AnswerValue } from "./values.ts";

export interface Prompt {
  name: string;
  default?: AnswerValue;
}

/**
 * 1.1 prompts in declaration order, a supplied answer beating the default.
 * 1.2/1.3 a missing answer is reported before an unknown one.
 */
export function resolveAnswers(
  prompts: Prompt[],
  supplied: Answers,
): Answers {
  const answers: Answers = {};

  for (const prompt of prompts) {
    if (Object.hasOwn(supplied, prompt.name)) {
      answers[prompt.name] = supplied[prompt.name]!;
    } else if (Object.hasOwn(prompt, "default")) {
      answers[prompt.name] = prompt.default!;
    } else {
      throw new ScaffoldError("MISSING_ANSWER", prompt.name);
    }
  }

  const known = new Set(prompts.map((prompt) => prompt.name));
  for (const name of Object.keys(supplied)) {
    if (!known.has(name)) {
      throw new ScaffoldError("UNKNOWN_ANSWER", name);
    }
  }

  return answers;
}
