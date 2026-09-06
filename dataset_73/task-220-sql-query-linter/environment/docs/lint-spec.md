# SQL lint specification

This document specifies how a query is linted. The linter must reproduce it
exactly.

## 1. Lines and positions

**1.1** A query is text. Lines are separated by `\n`; the last line may have no
terminator. Lines are numbered from 1, columns from 1, counting characters.

**1.2** Every violation is reported at a line and a column.

## 2. Reading the text

**2.1** A single-quoted string runs from a `'` to the next `'`. Two quotes in a
row inside a string are one quote and do not end it. A string that is never
closed runs to the end of the line.

**2.2** Outside a string, `--` begins a comment that runs to the end of the line.

**2.3** A word is a run of `A-Z`, `a-z`, `0-9` and `_`, beginning with a letter
or an underscore. A number is a run of `0-9`. Everything else outside a string
and a comment is a single-character token.

**2.4** Only text outside strings and comments is tokenised. Section 4 is the
only rule that looks at anything else.

## 3. Keywords and statements

**3.1** The keywords are, and are only: `SELECT`, `FROM`, `WHERE`, `JOIN`, `ON`,
`GROUP`, `ORDER`, `BY`, `LIMIT`, `AS`, `AND`, `OR`, `INNER`, `LEFT`, `OUTER`.
A word is a keyword when it matches one of these ignoring case.

**3.2** A statement begins at a `SELECT` keyword and ends at the `;` before the
next one, or at the end of the text. Tokens before the first `SELECT` belong to
no statement.

**3.3** A **clause keyword** is `FROM`, `WHERE`, `JOIN`, `GROUP`, `ORDER` or
`LIMIT`.

## 4. The rules

Each rule reports at most once per place it applies.

**L001 select-star** - a `*` token after the statement's `SELECT` and before its
first `FROM`, or anywhere after the `SELECT` when the statement has no `FROM`.
Reported at the `*`.

**L002 missing-where** - a statement with no `WHERE` keyword. A statement that
has a `LIMIT` keyword is exempt. Reported at the statement's `SELECT`.

**L003 join-without-on** - a `JOIN` keyword with no `ON` keyword between it and
the next clause keyword or the end of the statement. Reported at the `JOIN`.

**L004 comma-join** - a `,` token between the statement's first `FROM` and the
next clause keyword. Reported at the comma.

**L005 keyword-case** - a keyword whose text is not entirely upper case.
Reported at the word.

**L006 order-by-position** - a number token in the `ORDER BY` list: the token
straight after `BY` when `BY` follows `ORDER`, or a token straight after a comma
in that list. The list ends at the next clause keyword or the end of the
statement. Reported at the number.

**L007 limit-without-order** - a `LIMIT` keyword in a statement with no `ORDER`
keyword. Reported at the `LIMIT`.

**L008 trailing-whitespace** - a line whose last character is a space or a tab.
Reported at the first character of the run of spaces and tabs that ends the line.
This rule reads the raw line, comments and strings included.

**L009 tab-indent** - a line whose leading whitespace contains a tab. Reported at
the first such tab. This rule reads the raw line.

## 5. Severity

**5.1** Every rule has a default severity: `error` for L003 and L004, `warning`
for L001, L002, L006 and L007, and `style` for L005, L008 and L009.

**5.2** The configuration may give a rule a severity of `error`, `warning`,
`style` or `off`. A rule set to `off` reports nothing.

**5.3** A severity named for a rule that does not exist records the error
`UNKNOWN_RULE` naming it. A severity that is not one of the four names records
`UNKNOWN_SEVERITY` naming it, and leaves the rule's severity alone. Both are
recorded in the order the configuration lists them.

## 6. Suppression

**6.1** A comment whose text, after the `--` and any spaces, is exactly `noqa`
suppresses every violation reported on that line.

**6.2** A comment of the form `noqa:` followed by rule names separated by commas
suppresses only those rules on that line. Spaces around the names are ignored;
the names are matched exactly, so `l001` suppresses nothing.

**6.3** A line may carry at most one comment for this purpose: the first one.

**6.4** Suppression is decided by the line the violation is reported on, not the
line the statement began on.

**6.5** A suppressed violation is not reported and is not counted.

## 7. Report

**7.1** `violations` lists what was reported, ordered by line, then by column,
then by rule name.

**7.2** Each violation has `line`, `column`, `rule` and `severity`.

**7.3** `counts` has `error`, `warning` and `style`, counting the violations
reported.

**7.4** `errors` lists the configuration errors of 5.3, with `code` and `detail`.
