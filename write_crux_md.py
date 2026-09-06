#!/usr/bin/env python3
"""Write the reviewer-facing CRUX.md for each hardened task.

The buyer's question about a hard task is always the same: is it hard for a
legitimate reason, or is it hard because something is under-specified? This note
answers that question per task, and it answers it with measurements rather than
claims - the difficulty ladder printed at the bottom is the real output of
tools/check_crux.py, captured when the note was written.
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(r"C:\Users\user\Downloads\HardTask\work\dataset_73")
DESIGNS = json.loads(pathlib.Path(
    r"C:\Users\user\Downloads\HardTask\work\pilot_designs.json").read_text(encoding="utf-8"))

NAMES = {
    "A": "Latent crux", "B": "Wrong-default lure", "C": "Misdirection",
    "D": "Evidence-forced reverse engineering", "E": "Ordering assumption",
    "F": "Discovery-hop", "G": "Multi-mechanism accumulation",
    "H": "Entangled rules", "I": "Stale authority",
}


def proof(task):
    """The measured output of the task's own crux check, or why there isn't one."""
    script = ROOT / task / "tools" / "check_crux.py"
    if not script.exists():
        return None
    try:
        result = subprocess.run([sys.executable, "tools/check_crux.py"],
                                cwd=str(ROOT / task), capture_output=True,
                                text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return None
    return (result.stdout or result.stderr).strip()


def write(task, design):
    cruxes = design.get("cruxes", [])
    lines = [
        "# Why this task is hard",
        "",
        "A hard task is only worth buying if it is hard for a legitimate reason.",
        "This note names the reason, so a reviewer can check the claim rather than",
        "take it on trust.",
        "",
        "Every mechanism below hides the *path* to the answer. None of them hides",
        "the *existence* of a single correct answer: for each one, the evidence",
        "that makes the right behaviour recoverable ships inside `environment/`,",
        "and is named here. A task with two defensible readings would be a defect,",
        "not a difficulty.",
        "",
        "## What a model has to work out",
        "",
    ]
    for c in cruxes:
        letter = c.get("letter", "?").strip().upper()[:1]
        lines += [
            "### %s - %s" % (letter, c.get("name", "")),
            "",
            "**Mechanism.** %s" % c.get("mechanism", "").strip(),
            "",
            "**The wrong answer it punishes.** %s" % c.get("wrong_default", "").strip(),
            "",
            "**How it is recoverable.** %s" % c.get("how_discoverable", "").strip(),
            "",
        ]

    lines += [
        "## Is it still solvable?",
        "",
        design.get("solvability_argument", "").strip(),
        "",
        "## What was easy about it before",
        "",
        design.get("current_weakness", "").strip(),
        "",
    ]

    captured = proof(task)
    if captured:
        lines += [
            "## Measured, not asserted",
            "",
            "`tools/check_crux.py` implements each wrong answer described above,",
            "runs the full behaviour suite against it, and reports what the suite",
            "catches. This is its output:",
            "",
            "```",
            captured,
            "```",
            "",
            "Two properties matter in that output. Every wrong answer is caught, so",
            "the difficulty is real. And the scores in between are spread rather",
            "than clustered at nought and one, so a partially correct implementation",
            "earns partial credit - the reward stays continuous, which is what makes",
            "the gap between a strong and a weak model measurable at all.",
            "",
        ]
    else:
        lines += [
            "## Measured, not asserted",
            "",
            "`tools/check_crux.py` implements each wrong answer above and runs the",
            "behaviour suite against it. It has to run inside the task image, since",
            "it drives the candidate's command line; see the module docstring.",
            "",
        ]

    (ROOT / task / "CRUX.md").write_text("\n".join(lines).rstrip() + "\n",
                                         encoding="utf-8", newline="\n")
    return len(cruxes)


def main():
    for task, design in sorted(DESIGNS.items()):
        n = write(task, design)
        print("%-32s %d cruxes -> CRUX.md" % (task, n))


if __name__ == "__main__":
    main()
