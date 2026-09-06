// The file and hook passes (spec sections 3-6).

import { resolveAnswers, type Prompt } from "./answers.ts";
import { ScaffoldError } from "./errors.ts";
import { interpolate } from "./interpolate.ts";
import { normalisePath } from "./paths.ts";
import { isTruthy, type Answers, type AnswerValue } from "./values.ts";

export interface TemplateFile {
  path: string;
  content?: string;
  when?: string;
  executable?: boolean;
  force?: boolean;
}

export interface TemplateHook {
  run: string;
  when?: string;
}

export interface Plan {
  template?: {
    prompts?: Prompt[];
    files?: TemplateFile[];
    hooks?: TemplateHook[];
  };
  answers?: Answers;
  existing?: string[];
}

export interface Report {
  files: { path: string; content: string; mode: string }[];
  skipped: { path: string; reason: "EXISTS" | "COLLISION" }[];
  hooks: string[];
  errors: { code: string; detail: string }[];
}

/** 3.1, 3.3: an absent `when` always holds; an unknown one is an error. */
function conditionHolds(
  when: string | undefined,
  answers: Answers,
): boolean {
  if (when === undefined) {
    return true;
  }
  if (!Object.hasOwn(answers, when)) {
    throw new ScaffoldError("UNKNOWN_VARIABLE", when);
  }
  return isTruthy(answers[when] as AnswerValue);
}

export function render(plan: Plan): Report {
  const template = plan.template ?? {};
  const supplied = plan.answers ?? {};
  const existing = new Set(plan.existing ?? []);

  try {
    const answers = resolveAnswers(template.prompts ?? [], supplied);

    const files: Report["files"] = [];
    const skipped: Report["skipped"] = [];
    // 4.3 every rendered path is claimed, whether or not it was written, so a
    // later file collides even when the earlier one was skipped as EXISTS
    const claimed = new Set<string>();

    for (const entry of template.files ?? []) { // 4.1 declaration order
      if (!conditionHolds(entry.when, answers)) {
        continue;
      }
      const path = normalisePath(interpolate(entry.path, answers)); // 2.5, 4.5
      const content = interpolate(entry.content ?? "", answers);

      if (claimed.has(path)) {
        skipped.push({ path, reason: "COLLISION" });
        continue;
      }
      claimed.add(path);

      if (existing.has(path) && !entry.force) { // 4.2
        skipped.push({ path, reason: "EXISTS" });
        continue;
      }

      files.push({ path, content, mode: entry.executable ? "755" : "644" }); // 4.4
    }

    const hooks: string[] = [];
    for (const entry of template.hooks ?? []) { // 5.1, 5.2
      if (!conditionHolds(entry.when, answers)) {
        continue;
      }
      hooks.push(interpolate(entry.run, answers)); // 5.3
    }

    return { files, skipped, hooks, errors: [] };
  } catch (failure) {
    // 5.4, 6.4 any error clears everything else
    if (failure instanceof ScaffoldError) {
      return {
        files: [],
        skipped: [],
        hooks: [],
        errors: [{ code: failure.code, detail: failure.detail }],
      };
    }
    throw failure;
  }
}
