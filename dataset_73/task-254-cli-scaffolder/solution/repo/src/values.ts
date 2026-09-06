// Value rendering and truthiness (spec sections 2.4, 3.2).

export type AnswerValue = string | number | boolean;
export type Answers = Record<string, AnswerValue>;

/** 2.4: booleans render as true/false, integral numbers without a trailing .0. */
export function renderValue(value: AnswerValue): string {
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : String(value);
  }
  return value;
}

/**
 * 3.2: a boolean is itself; 0 is the only falsy number; the empty string is the
 * only falsy string, so "false" and "0" are both truthy.
 */
export function isTruthy(value: AnswerValue): boolean {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return value !== 0;
  }
  return value !== "";
}
