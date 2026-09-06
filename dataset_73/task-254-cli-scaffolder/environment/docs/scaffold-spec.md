# Scaffolder specification

This document specifies how a project template is rendered into a file tree.
The tool must reproduce it exactly.

## 1. Answers

**1.1** A template declares `prompts`, each with a `name` and optionally a
`default`. The answer set is built by taking each prompt in declaration order
and using the supplied answer if one is present, otherwise the default.

**1.2** A prompt with no supplied answer and no `default` produces the error
`MISSING_ANSWER` naming that prompt, and nothing else is rendered.

**1.3** A supplied answer whose name matches no prompt produces the error
`UNKNOWN_ANSWER` naming it, and nothing else is rendered. Errors are reported in
the order the checks are described here, so a missing answer outranks an unknown
one.

**1.4** Answers may be strings, numbers or booleans.

## 2. Interpolation

**2.1** `{{name}}` is replaced by the answer called `name`. There is no
whitespace trimming: `{{ name }}` refers to a variable whose name is ` name `
and will not be found.

**2.2** A reference to a name that is not an answer produces the error
`UNKNOWN_VARIABLE` naming it. Nothing is rendered.

**2.3** `{{{{` renders as a literal `{{` and is never treated as the start of a
reference. `}}}}` renders as a literal `}}`.

**2.4** A boolean answer renders as `true` or `false`. A number renders without
a trailing `.0`.

**2.5** Interpolation applies to file bodies and to file paths alike.

## 3. Conditions

**3.1** A file may carry a `when`, naming a single answer. The file is rendered
only when that answer is truthy.

**3.2** Truthiness: `false` and `true` are themselves; the number `0` is falsy
and every other number is truthy; the empty string is falsy and **every**
non-empty string is truthy, including `"false"` and `"0"`.

**3.3** A `when` naming a name that is not an answer produces the error
`UNKNOWN_VARIABLE`, exactly as an interpolation would.

## 4. Rendering

**4.1** Files are processed in declaration order.

**4.2** A file whose rendered path already exists in the target produces a
`skipped` entry with reason `EXISTS`, unless the file carries `force`, in which
case it is written over.

**4.3** Two template files that render to the same path collide. The second and
any later ones produce a `skipped` entry with reason `COLLISION`, whether or not
they carry `force`. Collision is judged on the rendered path alone, so a later
file collides even when the earlier one was itself skipped as `EXISTS`.

**4.4** `mode` is `"755"` when the file declares `executable`, otherwise
`"644"`.

**4.5** A rendered path is normalised by collapsing repeated slashes and
removing `.` segments. A path that escapes the target with `..`, or that is
absolute, produces the error `UNSAFE_PATH` naming the rendered path, and nothing
else is rendered.

## 5. Hooks

**5.1** Hooks run after every file has been processed, in declaration order.

**5.2** A hook may carry a `when`, under the same rules as a file.

**5.3** A hook's `run` string is interpolated like any other.

**5.4** Hooks do not run at all when any error was produced.

## 6. Report

**6.1** `files` lists every file written, in the order written, each with
`path`, `content` and `mode`.

**6.2** `skipped` lists every file not written, in declaration order, each with
`path` and `reason`.

**6.3** `hooks` lists the rendered `run` strings of the hooks that ran, in
order.

**6.4** `errors` lists the errors produced, each with `code` and `detail`. When
any error is produced, `files`, `skipped` and `hooks` are all empty.
