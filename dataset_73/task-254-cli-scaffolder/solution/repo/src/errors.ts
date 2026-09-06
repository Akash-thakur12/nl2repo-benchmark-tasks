// The four error codes the specification defines (section 6.4).

export type ErrorCode =
  | "MISSING_ANSWER"
  | "UNKNOWN_ANSWER"
  | "UNKNOWN_VARIABLE"
  | "UNSAFE_PATH";

export class ScaffoldError extends Error {
  readonly code: ErrorCode;
  readonly detail: string;

  constructor(code: ErrorCode, detail: string) {
    super(code);
    this.code = code;
    this.detail = detail;
  }
}
