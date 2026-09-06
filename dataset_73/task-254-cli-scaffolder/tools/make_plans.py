#!/usr/bin/env python3
"""Regenerate the sample and held-out plan corpora, and samples/expected.json.

  samples/       Six plans from a template that is easy on its renderer: every
                 prompt answered on the command line, no conditions, no escaped
                 braces, no executable files, no collisions, nothing already in
                 the target and no path that needs normalising. Almost every
                 plausible reading of the specification reproduces expected.json
                 here.

  tests/plans/   Held-out plans covering the rest: defaults, missing and unknown
                 answers, unknown variables, escaped braces, boolean and numeric
                 rendering, every truthiness edge, path interpolation and
                 normalisation, unsafe paths, collisions against force, existing
                 files, executable modes and hook suppression.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_scaffolder  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "plans"


def plan(prompts=None, files=None, hooks=None, answers=None, existing=None):
    template = {}
    if prompts is not None:
        template["prompts"] = prompts
    if files is not None:
        template["files"] = files
    if hooks is not None:
        template["hooks"] = hooks
    out = {"template": template}
    if answers is not None:
        out["answers"] = answers
    if existing is not None:
        out["existing"] = existing
    return out


def prompt(name, default=None):
    record = {"name": name}
    if default is not None:
        record["default"] = default
    return record


def f(path, content="", **kw):
    record = {"path": path, "content": content}
    record.update(kw)
    return record


# ------------------------------------------------------------ benign samples
def benign():
    # Every prompt is answered explicitly, so a renderer that ignores defaults
    # still reproduces the samples. No conditions, no escapes, no executables,
    # no collisions and nothing already present, for the same reason.
    return {
        "s01": plan(prompts=[prompt("name")],
                    files=[f("README.md", "# {{name}}\n")],
                    answers={"name": "acme"}),
        "s02": plan(prompts=[prompt("name"), prompt("author")],
                    files=[f("package.json", "{\"name\":\"{{name}}\"}"),
                           f("AUTHORS", "{{author}}\n")],
                    answers={"name": "acme", "author": "Dana"}),
        "s03": plan(prompts=[prompt("name")],
                    files=[f("src/index.js", "export const n = \"{{name}}\";\n")],
                    hooks=[{"run": "npm install"}],
                    answers={"name": "acme"}),
        "s04": plan(prompts=[prompt("name")],
                    files=[f("a.txt", "one"), f("b.txt", "two"), f("c.txt", "three")],
                    answers={"name": "acme"}),
        "s05": plan(prompts=[], files=[f("static.txt", "no variables here")],
                    answers={}),
        "s06": plan(prompts=[prompt("name")],
                    files=[f("docs/overview.md", "# {{name}}\n")],
                    hooks=[{"run": "echo done"}],
                    answers={"name": "acme"}),
    }


# --------------------------------------------------------- held-out corpus
def held_out():
    s = {}
    one = [prompt("name")]

    # -- defaults fill in for absent answers (1.1) -------------------------
    s["h01"] = plan(prompts=[prompt("name"), prompt("license", "MIT")],
                    files=[f("LICENSE", "{{license}} for {{name}}\n")],
                    answers={"name": "acme"})

    # -- a supplied answer beats the default (1.1) -------------------------
    s["h02"] = plan(prompts=[prompt("license", "MIT")],
                    files=[f("LICENSE", "{{license}}\n")],
                    answers={"license": "Apache-2.0"})

    # -- missing and unknown answers (1.2, 1.3) ----------------------------
    s["h03"] = plan(prompts=[prompt("name")], files=[f("a.txt", "x")], answers={})
    s["h04"] = plan(prompts=[prompt("name")], files=[f("a.txt", "x")],
                    answers={"name": "acme", "extra": 1})
    s["h05"] = plan(prompts=[prompt("name"), prompt("other")],
                    files=[f("a.txt", "x")], answers={"extra": 1})

    # -- unknown variables (2.2) -------------------------------------------
    s["h06"] = plan(prompts=one, files=[f("a.txt", "{{nope}}")],
                    answers={"name": "acme"})
    s["h07"] = plan(prompts=one, files=[f("{{nope}}.txt", "x")],
                    answers={"name": "acme"})

    # -- no whitespace trimming inside a reference (2.1) -------------------
    s["h08"] = plan(prompts=one, files=[f("a.txt", "{{ name }}")],
                    answers={"name": "acme"})

    # -- escaped braces (2.3) ----------------------------------------------
    s["h09"] = plan(prompts=one,
                    files=[f("a.txt", "{{{{name}}}} and {{name}}")],
                    answers={"name": "acme"})
    s["h10"] = plan(prompts=one, files=[f("a.txt", "{{{{raw}}}}")],
                    answers={"name": "acme"})

    # -- value rendering (2.4) ---------------------------------------------
    s["h11"] = plan(prompts=[prompt("flag"), prompt("count")],
                    files=[f("a.txt", "{{flag}}|{{count}}")],
                    answers={"flag": True, "count": 3})
    s["h12"] = plan(prompts=[prompt("flag"), prompt("count")],
                    files=[f("a.txt", "{{flag}}|{{count}}")],
                    answers={"flag": False, "count": 0})

    # -- truthiness (3.2) ---------------------------------------------------
    s["h13"] = plan(prompts=[prompt("v")], files=[f("a.txt", "x", when="v")],
                    answers={"v": "false"})
    s["h14"] = plan(prompts=[prompt("v")], files=[f("a.txt", "x", when="v")],
                    answers={"v": "0"})
    s["h15"] = plan(prompts=[prompt("v")], files=[f("a.txt", "x", when="v")],
                    answers={"v": ""})
    s["h16"] = plan(prompts=[prompt("v")], files=[f("a.txt", "x", when="v")],
                    answers={"v": 0})
    s["h17"] = plan(prompts=[prompt("v")], files=[f("a.txt", "x", when="v")],
                    answers={"v": False})
    s["h18"] = plan(prompts=[prompt("v")], files=[f("a.txt", "x", when="v")],
                    answers={"v": 2})

    # -- a condition naming an unknown answer (3.3) ------------------------
    s["h19"] = plan(prompts=one, files=[f("a.txt", "x", when="nope")],
                    answers={"name": "acme"})

    # -- paths are interpolated too (2.5) ----------------------------------
    s["h20"] = plan(prompts=one, files=[f("src/{{name}}/index.ts", "x")],
                    answers={"name": "acme"})

    # -- path normalisation (4.5) ------------------------------------------
    s["h21"] = plan(prompts=one, files=[f("src//a//b.txt", "x")],
                    answers={"name": "acme"})
    s["h22"] = plan(prompts=one, files=[f("./src/./a.txt", "x")],
                    answers={"name": "acme"})
    s["h23"] = plan(prompts=one, files=[f("src/nested/../a.txt", "x")],
                    answers={"name": "acme"})

    # -- unsafe paths (4.5) -------------------------------------------------
    s["h24"] = plan(prompts=one, files=[f("../escape.txt", "x")],
                    answers={"name": "acme"})
    s["h25"] = plan(prompts=one, files=[f("/etc/passwd", "x")],
                    answers={"name": "acme"})
    s["h26"] = plan(prompts=one, files=[f("./", "x")], answers={"name": "acme"})
    s["h27"] = plan(prompts=one, files=[f("{{name}}/../../out.txt", "x")],
                    answers={"name": "acme"})

    # -- existing files and force (4.2) ------------------------------------
    s["h28"] = plan(prompts=one, files=[f("README.md", "new")],
                    answers={"name": "acme"}, existing=["README.md"])
    s["h29"] = plan(prompts=one, files=[f("README.md", "new", force=True)],
                    answers={"name": "acme"}, existing=["README.md"])

    # -- collisions, and force does not excuse them (4.3) ------------------
    s["h30"] = plan(prompts=one,
                    files=[f("a.txt", "first"), f("a.txt", "second")],
                    answers={"name": "acme"})
    s["h31"] = plan(prompts=one,
                    files=[f("a.txt", "first"), f("a.txt", "second", force=True)],
                    answers={"name": "acme"})
    s["h32"] = plan(prompts=one,
                    files=[f("{{name}}.txt", "first"), f("acme.txt", "second")],
                    answers={"name": "acme"})

    # -- collision outranks existing (4.2, 4.3) ----------------------------
    s["h33"] = plan(prompts=one,
                    files=[f("a.txt", "first"), f("a.txt", "second")],
                    answers={"name": "acme"}, existing=["a.txt"])

    # -- executable mode (4.4) ---------------------------------------------
    s["h34"] = plan(prompts=one,
                    files=[f("bin/run", "#!/bin/sh\n", executable=True),
                           f("plain.txt", "x")],
                    answers={"name": "acme"})

    # -- hooks: conditions, interpolation, suppression (5.2-5.4) -----------
    s["h35"] = plan(prompts=[prompt("name"), prompt("ts", True)],
                    files=[f("a.txt", "x")],
                    hooks=[{"run": "npm install", "when": "ts"},
                           {"run": "echo {{name}}"}],
                    answers={"name": "acme"})
    s["h36"] = plan(prompts=[prompt("name"), prompt("ts", False)],
                    files=[f("a.txt", "x")],
                    hooks=[{"run": "npm install", "when": "ts"}],
                    answers={"name": "acme"})
    s["h37"] = plan(prompts=one,
                    files=[f("../escape.txt", "x")],
                    hooks=[{"run": "echo {{name}}"}],
                    answers={"name": "acme"})
    s["h38"] = plan(prompts=one, files=[f("a.txt", "x")],
                    hooks=[{"run": "echo {{nope}}"}], answers={"name": "acme"})

    # -- an error clears everything that came before it (6.4) --------------
    s["h39"] = plan(prompts=one,
                    files=[f("good.txt", "x"), f("../bad.txt", "y")],
                    answers={"name": "acme"})

    # -- absent sections are empty -----------------------------------------
    s["h40"] = plan(answers={})
    return s


def write(target, plans):
    target.mkdir(parents=True, exist_ok=True)
    for name, payload in sorted(plans.items()):
        (target / (name + ".plan")).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n")


def main():
    samples = benign()
    write(SAMPLES, samples)
    write(HELD_OUT, held_out())

    expected = {}
    for name in sorted(samples):
        text = (SAMPLES / (name + ".plan")).read_text(encoding="utf-8")
        expected[name] = reference_scaffolder.render_text(text)
    (SAMPLES / "expected.json").write_text(
        json.dumps(expected, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")

    print("samples  : %d" % len(samples))
    print("held-out : %d" % len(held_out()))
    print("expected.json written")


if __name__ == "__main__":
    main()
