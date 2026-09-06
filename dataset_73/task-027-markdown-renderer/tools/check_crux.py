#!/usr/bin/env python3
"""Prove that each crux actually bites.

A crux is only worth anything if the *obvious* implementation - the one a
competent engineer writes after skimming instruction.md and never opening
environment/ - fails the suite. This script builds those obvious
implementations mechanically, by rewriting the reference engine at the exact
points where the crux lives, and runs the full test suite against each one.

Each entry below is a wrong default that is genuinely plausible:

  H   the inline pipeline instruction.md used to prescribe verbatim - escape,
      then four independent regex substitutions over the whole string, and
      table rows split on every raw pipe. Code spans are not opaque.
  B   `_` treated as a symmetric synonym for `*`: two more regexes, no
      flanking restriction, so identifiers get eaten.
  D1  one <td> per cell actually present in the row, and a table treated only
      as a block start rather than as a paragraph interrupter.
  D2  every pipe is a separator, including a backslash-escaped one.
  C   the retired HTML4 house style still on disk under
      environment/docs/legacy/: align="..." on the <th> only, defaulting a
      plain column to left.

  BITES     at least one of the named tests failed  -> the crux is real
  TOOTHLESS every test still passed                 -> the suite does not
                                                       depend on that rule

This script ships no secrets: every rewrite it performs is visible in the
RULES table below, and the reference it starts from is solution/engine/.
It does not ship in the task image.
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
TASK = HERE.parent
REFERENCE = TASK / "solution" / "engine"
TESTS = TASK / "tests" / "test_outputs.py"

BACKSLASH = chr(92)

#: Each rewrite is (filename, exact text to find, replacement).
RULES = {
    "H": [
        ("inlines.py",
         "    return _CODE_SPAN_RE.sub(take, text)",
         "    return text"),
        ("inlines.py",
         "    return _PLACEHOLDER_RE.sub(give, text)",
         "    return text"),
        ("inlines.py",
         "    text = escape_html(text)",
         '    text = escape_html(text)\n'
         '    text = _CODE_SPAN_RE.sub(r"<code>' + BACKSLASH + '1</code>", text)'),
    ],
    "B": [
        ("inlines.py",
         '_STRONG_US_RE = re.compile(r"(?<![0-9A-Za-z])__(.+?)__(?![0-9A-Za-z])")',
         '_STRONG_US_RE = re.compile(r"__(.+?)__")'),
        ("inlines.py",
         '_EM_US_RE = re.compile(r"(?<![0-9A-Za-z_])_([^_]+)_(?![0-9A-Za-z_])")',
         '_EM_US_RE = re.compile(r"_([^_]+)_")'),
    ],
    "D1": [
        ("engine.py",
         '            row = (row + [""] * width)[:width]',
         "            row = list(row)"),
        ("engine.py",
         "        or _is_table_start(lines, i)",
         "        or False"),
    ],
    "D2": [
        ("engine.py",
         '_CELL_SPLIT_RE = re.compile(r"(?<!' + BACKSLASH * 2 + ')' + BACKSLASH + '|")',
         '_CELL_SPLIT_RE = re.compile(r"' + BACKSLASH + '|")'),
        ("engine.py",
         '        return [c.strip().replace("' + BACKSLASH * 2 + '|", "|") '
         "for c in _CELL_SPLIT_RE.split(line)]",
         "        return [c.strip() for c in _CELL_SPLIT_RE.split(line)]"),
    ],
    "C": [
        ("engine.py",
         "    return ' style=\"text-align: %s\"' % align if align else \"\"",
         "    return ' align=\"%s\"' % (align or \"left\")"),
        ("engine.py",
         '"<td%s>%s</td>" % (_style_attr(aligns[k]), render_masked(c, store))',
         '"<td%s>%s</td>" % ("", render_masked(c, store))'),
    ],
}

#: The tests each wrong default is expected to break.
EXPECTED = {
    "H": [
        "test_code_span_body_is_not_emphasized",
        "test_code_span_body_is_not_linkified",
        "test_pipe_inside_code_span_does_not_split_a_table_cell",
        "test_code_span_in_list_item_is_opaque",
    ],
    "B": [
        "test_underscore_does_not_fire_intraword",
        "test_underscore_in_link_target_is_preserved",
    ],
    "D1": [
        "test_short_row_is_padded_to_header_width",
        "test_long_row_is_truncated_to_header_width",
        "test_table_interrupts_an_open_paragraph",
    ],
    "D2": [
        "test_escaped_pipe_is_a_literal_cell_character",
    ],
    "C": [
        "test_alignment_markers_style_the_header_cells",
        "test_alignment_applies_to_body_cells_of_the_column",
        "test_plain_separator_column_carries_no_attribute",
        "test_html4_align_attribute_is_never_emitted",
        "test_aligned_table_full_serialization",
    ],
}

LABELS = {
    "H": "code spans are not opaque (spec-literal inline order, raw pipe split)",
    "B": "underscore treated as a symmetric synonym for star",
    "D1": "no header-width normalisation, table never interrupts a paragraph",
    "D2": "every pipe separates, including an escaped one",
    "C": "retired HTML4 align attribute on the header cell only",
}


def build(work, rewrites):
    """Copy the reference package and apply one crux's rewrites to it."""
    package = work / "engine"
    if package.exists():
        shutil.rmtree(package)
    shutil.copytree(REFERENCE, package,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for filename, old, new in rewrites:
        path = package / filename
        source = path.read_text(encoding="utf-8")
        if old not in source:
            raise SystemExit(
                "check_crux.py is out of date: it cannot find this text in %s\n"
                "  %r" % (filename, old))
        path.write_text(source.replace(old, new, 1), encoding="utf-8")
    return package


def run(package):
    """Return the set of test names that failed against this package."""
    environment = dict(os.environ)
    environment["ENGINE_DIR"] = str(package)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(TESTS), "-v", "--tb=no",
         "-p", "no:cacheprovider"],
        cwd=str(TASK), env=environment, capture_output=True, text=True,
        timeout=300)
    failed = set()
    for line in result.stdout.splitlines():
        if "::" in line and (" FAILED" in line or " ERROR" in line):
            name = line.split("::", 1)[1].split(" ")[0]
            failed.add(name.split("[")[0])
    return failed, result.returncode


def main():
    if not (REFERENCE / "engine.py").exists():
        print("no reference engine at %s" % REFERENCE)
        return 1

    work = pathlib.Path(tempfile.mkdtemp(prefix="crux-"))
    try:
        baseline, code = run(build(work, []))
        if code != 0:
            print("BASELINE BROKEN: the reference engine does not pass its own "
                  "tests (%d failing). Nothing below would mean anything."
                  % len(baseline))
            return 1
        print("baseline: reference engine passes the whole suite")
        print()

        toothless = []
        for letter in ("H", "B", "D1", "D2", "C"):
            failed, _ = run(build(work, RULES[letter]))
            wanted = [t for t in EXPECTED[letter] if t in failed]
            missed = [t for t in EXPECTED[letter] if t not in failed]
            verdict = "BITES    " if wanted else "TOOTHLESS"
            print("%s crux %-2s  %s" % (verdict, letter, LABELS[letter]))
            print("            %d of %d guard tests failed, %d tests failing "
                  "in total" % (len(wanted), len(EXPECTED[letter]), len(failed)))
            for name in wanted:
                print("              caught by  %s" % name)
            for name in missed:
                print("              NOT caught  %s" % name)
            if not wanted:
                toothless.append(letter)
            print()

        if toothless:
            print("TOOTHLESS cruxes: %s -- the obvious wrong implementation "
                  "still passes, so the suite does not test that rule."
                  % ", ".join(toothless))
            return 1
        print("every crux bites: each wrong default is caught by the suite")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
