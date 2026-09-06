#!/usr/bin/env python3
"""Prove the corpus discriminates, rather than asserting that it does.

Every entry below is a plausible near-miss. For each one this asserts that it
still reproduces environment/samples/expected.json exactly, and that at least
one held-out plan catches it.

The golden repository is TypeScript, but the near-misses are written against the
Python reference model, because that is the authority the tests derive expected
output from. A shortcut caught here would be caught in any language.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_scaffolder as ref  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "plans"


# ------------------------------------------------------ interpolation variants
def interp_trimmed(text, answers):
    out, i, n = [], 0, len(text)
    while i < n:
        if text.startswith("{{{{", i):
            out.append("{{")
            i += 4
            continue
        if text.startswith("}}}}", i):
            out.append("}}")
            i += 4
            continue
        if text.startswith("{{", i):
            end = text.find("}}", i + 2)
            if end == -1:
                out.append(text[i])
                i += 1
                continue
            name = text[i + 2:end].strip()          # trims
            if name not in answers:
                raise ref.ScaffoldError("UNKNOWN_VARIABLE", name)
            out.append(ref.render_value(answers[name]))
            i = end + 2
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def interp_missing_is_blank(text, answers):
    out, i, n = [], 0, len(text)
    while i < n:
        if text.startswith("{{{{", i):
            out.append("{{")
            i += 4
            continue
        if text.startswith("}}}}", i):
            out.append("}}")
            i += 4
            continue
        if text.startswith("{{", i):
            end = text.find("}}", i + 2)
            if end == -1:
                out.append(text[i])
                i += 1
                continue
            name = text[i + 2:end]
            out.append(ref.render_value(answers[name]) if name in answers else "")
            i = end + 2
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def interp_no_escape(text, answers):
    out, i, n = [], 0, len(text)
    while i < n:
        if text.startswith("{{", i):                # no escape handling at all
            end = text.find("}}", i + 2)
            if end == -1:
                out.append(text[i])
                i += 1
                continue
            name = text[i + 2:end]
            if name not in answers:
                raise ref.ScaffoldError("UNKNOWN_VARIABLE", name)
            out.append(ref.render_value(answers[name]))
            i = end + 2
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def value_host_formatting(value):
    if isinstance(value, bool):
        return str(value)                           # "True" / "False"
    if isinstance(value, float) and value.is_integer():
        return str(value)                           # "3.0"
    return str(value)


# ---------------------------------------------------------- truthiness variants
def truthy_python(value):
    return bool(value)                              # "false" and "0" become truthy
                                                    # in Python too, so this only
                                                    # differs for other shapes


def truthy_string_words(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return value.lower() not in ("", "false", "0")


def truthy_zero_is_true(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return True                                 # any number is truthy
    return value != ""


# ----------------------------------------------------------- answers variants
def answers_ignore_defaults(template, supplied):
    prompts = template.get("prompts", []) or []
    answers = {}
    for prompt in prompts:
        if prompt["name"] in supplied:
            answers[prompt["name"]] = supplied[prompt["name"]]
        else:
            raise ref.ScaffoldError("MISSING_ANSWER", prompt["name"])
    known = {p["name"] for p in prompts}
    for name in supplied:
        if name not in known:
            raise ref.ScaffoldError("UNKNOWN_ANSWER", name)
    return answers


def answers_no_unknown_check(template, supplied):
    prompts = template.get("prompts", []) or []
    answers = {}
    for prompt in prompts:
        if prompt["name"] in supplied:
            answers[prompt["name"]] = supplied[prompt["name"]]
        elif "default" in prompt:
            answers[prompt["name"]] = prompt["default"]
        else:
            raise ref.ScaffoldError("MISSING_ANSWER", prompt["name"])
    return answers


def answers_unknown_first(template, supplied):
    prompts = template.get("prompts", []) or []
    known = {p["name"] for p in prompts}
    for name in supplied:
        if name not in known:
            raise ref.ScaffoldError("UNKNOWN_ANSWER", name)
    return ref.build_answers(template, supplied)


# -------------------------------------------------------------- path variants
def path_no_normalise(path):
    if path.startswith("/") or ".." in path.split("/"):
        raise ref.ScaffoldError("UNSAFE_PATH", path)
    return path                                     # slashes and dots left alone


def path_allow_escape(path):
    parts = []
    for segment in path.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if parts:
                parts.pop()
            continue                                # silently tolerated
        parts.append(segment)
    return "/".join(parts)


def path_allow_absolute(path):
    parts = [s for s in path.split("/") if s not in ("", ".")]
    out = []
    for segment in parts:
        if segment == "..":
            if not out:
                raise ref.ScaffoldError("UNSAFE_PATH", path)
            out.pop()
            continue
        out.append(segment)
    if not out:
        raise ref.ScaffoldError("UNSAFE_PATH", path)
    return "/".join(out)


def path_allow_empty(path):
    if path.startswith("/"):
        raise ref.ScaffoldError("UNSAFE_PATH", path)
    parts = []
    for segment in path.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if not parts:
                raise ref.ScaffoldError("UNSAFE_PATH", path)
            parts.pop()
            continue
        parts.append(segment)
    return "/".join(parts)                          # "" is allowed through


# ------------------------------------------------------------ the renderer
def make_render(interp=None, value_fn=None, truthy_fn=None, answers_fn=None,
                path_fn=None, interp_paths=True, collide_on_written=False,
                force_beats_collision=False, always_644=False,
                drop_skipped=False, hooks_after_error=False,
                raw_hooks=False, keep_partial_on_error=False):
    interp = interp or ref.interpolate
    truthy_fn = truthy_fn or ref.truthy
    answers_fn = answers_fn or ref.build_answers
    path_fn = path_fn or ref.normalise

    saved_render_value = ref.render_value

    def do(plan):
        template = plan.get("template", {}) or {}
        supplied = plan.get("answers", {}) or {}
        existing = set(plan.get("existing", []) or [])
        files, skipped, hooks = [], [], []
        if value_fn is not None:
            ref.render_value = value_fn
        try:
            answers = answers_fn(template, supplied)

            def holds(entry):
                when = entry.get("when")
                if when is None:
                    return True
                if when not in answers:
                    raise ref.ScaffoldError("UNKNOWN_VARIABLE", when)
                return truthy_fn(answers[when])

            claimed, written = set(), set()
            for entry in template.get("files", []) or []:
                if not holds(entry):
                    continue
                raw_path = interp(entry["path"], answers) if interp_paths else entry["path"]
                path = path_fn(raw_path)
                content = interp(entry.get("content", ""), answers)
                seen = written if collide_on_written else claimed
                if path in seen and not (force_beats_collision and entry.get("force")):
                    if not drop_skipped:
                        skipped.append({"path": path, "reason": "COLLISION"})
                    continue
                claimed.add(path)
                if path in existing and not entry.get("force"):
                    if not drop_skipped:
                        skipped.append({"path": path, "reason": "EXISTS"})
                    continue
                written.add(path)
                mode = "644" if always_644 else ("755" if entry.get("executable") else "644")
                files.append({"path": path, "content": content, "mode": mode})

            for entry in template.get("hooks", []) or []:
                if not holds(entry):
                    continue
                hooks.append(entry["run"] if raw_hooks else interp(entry["run"], answers))

            return {"files": files, "skipped": skipped, "hooks": hooks, "errors": []}
        except ref.ScaffoldError as failure:
            if hooks_after_error:
                pass
            if keep_partial_on_error:
                return {"files": files, "skipped": skipped, "hooks": hooks,
                        "errors": [{"code": failure.code, "detail": failure.detail}]}
            return {"files": [], "skipped": [], "hooks": [],
                    "errors": [{"code": failure.code, "detail": failure.detail}]}
        finally:
            ref.render_value = saved_render_value
    return do


SHORTCUTS = [
    ("whitespace is trimmed inside a reference", make_render(interp=interp_trimmed)),
    ("an unknown variable renders as an empty string", make_render(interp=interp_missing_is_blank)),
    ("{{{{ is not treated as an escaped brace", make_render(interp=interp_no_escape)),
    ("values are rendered with the host language's formatting", make_render(value_fn=value_host_formatting)),
    ('the strings "false" and "0" are falsy', make_render(truthy_fn=truthy_string_words)),
    ("every number is truthy, including zero", make_render(truthy_fn=truthy_zero_is_true)),
    ("prompt defaults are ignored", make_render(answers_fn=answers_ignore_defaults)),
    ("an answer matching no prompt is accepted", make_render(answers_fn=answers_no_unknown_check)),
    ("an unknown answer is reported before a missing one", make_render(answers_fn=answers_unknown_first)),
    ("file paths are not interpolated", make_render(interp_paths=False)),
    ("paths are not normalised before comparison", make_render(path_fn=path_no_normalise)),
    ("a path that escapes the target is tolerated", make_render(path_fn=path_allow_escape)),
    ("an absolute path is accepted", make_render(path_fn=path_allow_absolute)),
    ("a path that normalises to nothing is accepted", make_render(path_fn=path_allow_empty)),
    ("collision is judged only against files actually written", make_render(collide_on_written=True)),
    ("force excuses a collision as well as an existing file", make_render(force_beats_collision=True)),
    ("every file is written with mode 644", make_render(always_644=True)),
    ("skipped files are not recorded", make_render(drop_skipped=True)),
    ("hook strings are not interpolated", make_render(raw_hooks=True)),
    ("an error leaves earlier results in place", make_render(keep_partial_on_error=True)),
]


def main():
    sample_files = sorted(SAMPLES.glob("*.plan"))
    held_files = sorted(HELD_OUT.glob("*.plan"))
    expected = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))

    for f in sample_files:
        assert ref.render_text(f.read_text(encoding="utf-8")) == expected[f.stem], \
            "reference disagrees with expected.json on %s" % f.stem

    truth = {f.stem: ref.render_text(f.read_text(encoding="utf-8")) for f in held_files}

    bad, uncaught, rows = [], [], []
    for label, fn in SHORTCUTS:
        ok = True
        for f in sample_files:
            try:
                if fn(json.loads(f.read_text(encoding="utf-8"))) != expected[f.stem]:
                    ok = False
                    break
            except Exception:
                ok = False
                break
        caught = []
        for f in held_files:
            try:
                if fn(json.loads(f.read_text(encoding="utf-8"))) != truth[f.stem]:
                    caught.append(f.stem)
            except Exception:
                caught.append(f.stem)
        rows.append((label, ok, caught))
        if not ok:
            bad.append(label)
        if not caught:
            uncaught.append(label)

    width = max(len(r[0]) for r in rows)
    print("%-*s  %-8s  %s" % (width, "shortcut", "samples", "caught by"))
    print("-" * (width + 30))
    for label, ok, caught in rows:
        shown = ",".join(caught[:4]) + ("..." if len(caught) > 4 else "")
        print("%-*s  %-8s  %s" % (width, label, "pass" if ok else "FAIL",
                                  ("%d: %s" % (len(caught), shown)) if caught else "NONE"))
    print()
    print("shortcuts          : %d" % len(rows))
    print("reproduce samples  : %d" % sum(1 for r in rows if r[1]))
    print("caught by held-out : %d" % sum(1 for r in rows if r[2]))

    if bad:
        print("\nAlready rejected by the visible samples, so not evidence of anything:")
        for lb in bad:
            print("  -", lb)
    if uncaught:
        print("\nHOLE IN THE CORPUS - these survive every held-out plan:")
        for lb in uncaught:
            print("  -", lb)
    if bad or uncaught:
        sys.exit(1)
    print("\nOK: every shortcut reproduces the samples and every one is caught.")


if __name__ == "__main__":
    main()
