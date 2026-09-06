#!/usr/bin/env python3
"""Regenerate the sample and held-out history corpora, and samples/expected.json.

  samples/          Eight ranges from a well-behaved repository: every subject
                    conventional and scoped, every author distinct and already in
                    the order they first appear, one entry per section, no
                    breaking changes, no reverts, no duplicates, no excluded
                    types, no pull request references and a stable major version.
                    Almost every plausible reading of the specification
                    reproduces expected.json here.

  tests/histories/  Held-out ranges covering the rest: subjects that are not
                    conventional, the two breaking footers and the near misses
                    that are not footers, the unstable 0.x rule, pull request
                    references and merged pull requests, duplicates and near
                    duplicates, reverts of every shape, excluded types, the Other
                    section, and the order of contributors and skips.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_notes  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "histories"

FEATURES = {"type": "feat", "title": "Features"}
FIXES = {"type": "fix", "title": "Bug Fixes"}
PERF = {"type": "perf", "title": "Performance"}


def config(previous="1.4.2", sections=None, include=None):
    return {"op": "config", "previous_version": previous,
            "sections": list(sections if sections is not None
                             else [FEATURES, FIXES]),
            "include_types": list(include if include is not None
                                  else ["feat", "fix", "revert"])}


_counter = [0]


def sha(seed=None):
    if seed is not None:
        return seed
    _counter[0] += 1
    return "%07x" % (0xa10000 + _counter[0])


def commit(subject, author="Ana Ruiz", body="", pr=None, at=None):
    record = {"op": "commit", "sha": sha(at), "subject": subject,
              "body": body, "author": author}
    if pr is not None:
        record["merged_pr"] = pr
    return record


def end():
    return {"op": "end"}


# ------------------------------------------------------------ benign samples
def benign():
    # Every commit conventional and scoped, one entry per section and every
    # configured section filled, sections in the order the configuration asks
    # for, one author per commit and those authors already alphabetical, no
    # bodies, no pull requests, no reverts, no duplicates, no excluded types, a
    # major version well past zero and a previous patch of zero wherever the
    # bump is a minor one.
    s = {}
    s["s01"] = [config("1.4.0"),
                commit("feat(api): add cursor pagination", "Ana Ruiz",
                       at="a000001"),
                commit("fix(auth): refresh the token before it expires",
                       "Bo Lindqvist", at="a000002"),
                end()]
    s["s02"] = [config("2.0.0", sections=[FEATURES]),
                commit("feat(cli): read the profile from the environment",
                       "Ana Ruiz", at="a000003"),
                end()]
    s["s03"] = [config("1.9.7", sections=[FIXES]),
                commit("fix(db): close the cursor on an empty result",
                       "Ana Ruiz", at="a000004"),
                end()]
    s["s04"] = [config("5.1.0", sections=[FEATURES]),
                commit("feat(queue): acknowledge in batches", "Ana Ruiz",
                       at="a000010"),
                end()]
    s["s05"] = [config("1.0.0"),
                commit("feat(sync): resume from the last acknowledged offset",
                       "Ana Ruiz", at="a000005"),
                commit("fix(sync): stop retrying a permanent failure",
                       "Bo Lindqvist", at="a000006"),
                end()]
    s["s06"] = [config("4.4.0", sections=[FEATURES, FIXES, PERF],
                       include=["feat", "fix", "perf", "revert"]),
                commit("feat(report): group rows by tenant", "Ana Ruiz",
                       at="a000007"),
                commit("fix(report): round the totals once", "Bo Lindqvist",
                       at="a000008"),
                commit("perf(report): stream the rows instead of buffering",
                       "Cai Wen", at="a000009"),
                end()]
    s["s07"] = [config("10.0.3", sections=[FIXES]),
                commit("fix(build): pin the toolchain", "Ana Ruiz", at="a00000a"),
                end()]
    s["s08"] = [config("1.4.0", sections=[FEATURES, PERF],
                       include=["feat", "fix", "perf", "revert"]),
                commit("feat(search): match on the tenant prefix", "Ana Ruiz",
                       at="a00000b"),
                commit("perf(search): cache the compiled matcher",
                       "Bo Lindqvist", at="a00000c"),
                end()]
    return s


# --------------------------------------------------------- held-out corpus
def held_out():
    s = {}

    # -- subjects that are not conventional (2.1-2.3) -----------------------
    s["h01"] = [config(),
                commit("add pagination", at="b000001"),
                commit("Feat: add pagination", at="b000002"),
                commit("feat:add pagination", at="b000003"),
                commit("feat:  add pagination", at="b000004"),
                commit("feat: ", at="b000005"),
                commit("feat2: add pagination", at="b000006"),
                commit(" feat: add pagination", at="b000007"),
                end()]

    # -- scopes, present, empty and awkward (2.1) ---------------------------
    s["h02"] = [config(),
                commit("feat: no scope at all", at="b000010"),
                commit("feat(): empty scope", at="b000011"),
                commit("feat(a/b,c): punctuation in the scope", at="b000012"),
                commit("fix(deps)!: drop node 18", at="b000013"),
                end()]

    # -- breaking by bang, and the note that stands in for it (3.1, 3.3) ----
    s["h03"] = [config(),
                commit("feat(api)!: remove the v1 endpoints", at="b000020"),
                end()]

    # -- breaking by footer, both spellings (3.2, 3.3) ----------------------
    s["h04"] = [config(),
                commit("feat(api): rework the filters",
                       body="Rewrites the filter parser.\n"
                            "BREAKING CHANGE: filter syntax has changed",
                       at="b000030"),
                end()]
    s["h05"] = [config(),
                commit("feat(api): rework the filters",
                       body="BREAKING-CHANGE: filter syntax has changed",
                       at="b000031"),
                end()]

    # -- footers that are not footers (3.2) ---------------------------------
    s["h06"] = [config(),
                commit("feat(api): one", body="breaking change: lowercase",
                       at="b000040"),
                commit("feat(api): two", body="  BREAKING CHANGE: indented",
                       at="b000041"),
                commit("feat(api): three", body="see BREAKING CHANGE: inline",
                       at="b000042"),
                commit("feat(api): four", body="BREAKING CHANGE:no space",
                       at="b000043"),
                end()]

    # -- a footer line with trailing whitespace still counts (3.2) ----------
    s["h07"] = [config(),
                commit("feat(api): five",
                       body="BREAKING CHANGE: the note   \nmore text",
                       at="b000050"),
                end()]

    # -- the unstable 0.x rule (4.4) ----------------------------------------
    s["h08"] = [config("0.4.1"),
                commit("feat(api)!: remove the v1 endpoints", at="b000060"),
                end()]
    s["h09"] = [config("0.4.1"),
                commit("feat(api): add a filter", at="b000061"),
                end()]
    s["h10"] = [config("0.4.1"),
                commit("fix(api): stop double counting", at="b000062"),
                end()]
    s["h11"] = [config("0.0.0"),
                commit("feat(api)!: the first breaking change", at="b000063"),
                end()]

    # -- no surviving entry means no bump (4.2) -----------------------------
    s["h12"] = [config("1.4.2"),
                commit("chore(deps): bump the lockfile", at="b000070"),
                commit("not a conventional subject", at="b000071"),
                end()]

    # -- pull request references (2.4-2.6) ----------------------------------
    s["h13"] = [config(),
                commit("feat(api): add pagination (#412)", at="b000080"),
                commit("feat(api): add (#7) sorting", at="b000081"),
                commit("fix(api): repair (#8) counting (#9)", at="b000082"),
                commit("fix(api): trailing not a reference (#)", at="b000083"),
                end()]
    s["h14"] = [config(),
                commit("feat(api): add pagination (#412)", pr=999, at="b000090"),
                commit("fix(api): tidy up", pr=1000, at="b000091"),
                end()]

    # -- duplicates and near duplicates (5.3) -------------------------------
    s["h15"] = [config(),
                commit("feat(api): add pagination", "Ana Ruiz", at="b000100"),
                commit("feat(api): add pagination", "Bo Lindqvist", at="b000101"),
                commit("feat(cli): add pagination", "Cai Wen", at="b000102"),
                commit("fix(api): add pagination", "Dee Okafor", at="b000103"),
                commit("feat(api): add pagination twice", "Eli Moss", at="b000104"),
                end()]

    # -- a duplicate does not change the entry it duplicates (5.3) ----------
    s["h16"] = [config(),
                commit("feat(api): add pagination", at="b000110"),
                commit("feat(api): add pagination", pr=77,
                       body="BREAKING CHANGE: it changed", at="b000111"),
                end()]

    # -- a revert takes its entry with it, and the bump follows (5.5, 4.2) --
    s["h17"] = [config(),
                commit("feat(api): add pagination", "Ana Ruiz", at="b000120"),
                commit("fix(api): stop double counting", "Bo Lindqvist",
                       at="b000121"),
                commit("revert: add pagination", "Cai Wen",
                       body="Reverts: b000120", at="b000122"),
                end()]

    # -- reverting the only breaking change drops the major bump (4.2) ------
    s["h18"] = [config(),
                commit("feat(api)!: remove the v1 endpoints", at="b000130"),
                commit("fix(api): stop double counting", at="b000131"),
                commit("revert: put the v1 endpoints back",
                       body="Reverts: b000130", at="b000132"),
                end()]

    # -- reverting everything leaves no bump at all (4.2) -------------------
    s["h19"] = [config(),
                commit("feat(api): add pagination", at="b000140"),
                commit("revert: drop pagination again",
                       body="Reverts: b000140", at="b000141"),
                end()]

    # -- a revert of a sha nobody has (5.6) ---------------------------------
    s["h20"] = [config(),
                commit("feat(api): add pagination", at="b000150"),
                commit("revert: something else",
                       body="Reverts: 9999999", at="b000151"),
                end()]

    # -- two reverts of the same commit (5.6) -------------------------------
    s["h21"] = [config(),
                commit("feat(api): add pagination", at="b000160"),
                commit("revert: drop pagination", body="Reverts: b000160",
                       at="b000161"),
                commit("revert: drop pagination once more",
                       body="Reverts: b000160", at="b000162"),
                end()]

    # -- a revert naming a commit that was skipped as a duplicate (5.6) -----
    s["h22"] = [config(),
                commit("feat(api): add pagination", at="b000170"),
                commit("feat(api): add pagination", at="b000171"),
                commit("revert: drop the duplicate", body="Reverts: b000171",
                       at="b000172"),
                end()]

    # -- a revert with nothing to go on (5.7) -------------------------------
    s["h23"] = [config(),
                commit("feat(api): add pagination", at="b000180"),
                commit("revert: no footer here", body="just prose",
                       at="b000181"),
                end()]

    # -- a revert naming an unconventional commit (5.6) ---------------------
    s["h24"] = [config(),
                commit("wip", at="b000190"),
                commit("revert: undo the wip", body="Reverts: b000190",
                       at="b000191"),
                end()]

    # -- a revert naming a later commit, which does not exist yet (5.8) -----
    s["h25"] = [config(),
                commit("revert: too early", body="Reverts: b000201",
                       at="b000200"),
                commit("feat(api): add pagination", at="b000201"),
                end()]

    # -- excluded types take no part, breaking or not (3.4, 5.2) ------------
    s["h26"] = [config(include=["feat", "fix", "revert"]),
                commit("chore(deps)!: bump everything",
                       body="BREAKING CHANGE: everything moved", at="b000210"),
                commit("docs(readme): tidy the intro", at="b000211"),
                commit("fix(api): stop double counting", at="b000212"),
                end()]

    # -- an excluded revert type does nothing at all (5.2) ------------------
    s["h27"] = [config(include=["feat", "fix"]),
                commit("feat(api): add pagination", at="b000220"),
                commit("revert: drop pagination", body="Reverts: b000220",
                       at="b000221"),
                end()]

    # -- an included type with no section falls into Other, last (6.3) ------
    s["h28"] = [config(include=["feat", "fix", "perf", "build", "revert"]),
                commit("perf(api): stream the rows", at="b000230"),
                commit("feat(api): add pagination", at="b000231"),
                commit("build(ci): cache the toolchain", at="b000232"),
                end()]

    # -- a configured section with no entries is not emitted (6.1) ----------
    s["h29"] = [config(sections=[FEATURES, PERF, FIXES],
                       include=["feat", "fix", "perf", "revert"]),
                commit("fix(api): stop double counting", at="b000240"),
                end()]

    # -- sections follow the configuration, not the history (6.1) -----------
    s["h30"] = [config(sections=[FEATURES, FIXES]),
                commit("fix(api): stop double counting", at="b000250"),
                commit("feat(api): add pagination", at="b000251"),
                end()]

    # -- entries inside a section follow history order (6.2) ----------------
    s["h31"] = [config(),
                commit("feat(api): first", at="b000260"),
                commit("fix(api): second", at="b000261"),
                commit("feat(cli): third", at="b000262"),
                commit("feat(db): fourth", at="b000263"),
                end()]

    # -- contributors: deduplicated, in first appearance order (7.1) --------
    s["h32"] = [config(),
                commit("feat(api): first", "Zoe Adler", at="b000270"),
                commit("fix(api): second", "Ana Ruiz", at="b000271"),
                commit("feat(cli): third", "Zoe Adler", at="b000272"),
                end()]

    # -- a skipped commit's author contributes nothing (7.2) ----------------
    s["h33"] = [config(),
                commit("feat(api): first", "Ana Ruiz", at="b000280"),
                commit("chore(deps): bump", "Bo Lindqvist", at="b000281"),
                commit("nothing conventional", "Cai Wen", at="b000282"),
                commit("feat(api): first", "Dee Okafor", at="b000283"),
                end()]

    # -- a reverted entry's author, and the reverter, contribute nothing ----
    s["h34"] = [config(),
                commit("feat(api): first", "Ana Ruiz", at="b000290"),
                commit("fix(api): second", "Bo Lindqvist", at="b000291"),
                commit("revert: undo the first", "Cai Wen",
                       body="Reverts: b000290", at="b000292"),
                end()]

    # -- skipped is in history order, not in the order reasons were decided -
    s["h35"] = [config(),
                commit("feat(api): first", at="b000300"),
                commit("chore(deps): bump", at="b000301"),
                commit("revert: undo the first", body="Reverts: b000300",
                       at="b000302"),
                commit("nothing conventional", at="b000303"),
                end()]

    # -- everything at once --------------------------------------------------
    s["h36"] = [config("0.9.9", sections=[FEATURES, FIXES, PERF],
                       include=["feat", "fix", "perf", "revert", "build"]),
                commit("feat(api): add pagination (#12)", "Ana Ruiz",
                       at="b000310"),
                commit("perf(api): stream the rows", "Bo Lindqvist",
                       at="b000311"),
                commit("build(ci): cache the toolchain", "Cai Wen",
                       at="b000312"),
                commit("fix(api)!: drop the legacy header", "Ana Ruiz",
                       body="BREAKING CHANGE: the X-Legacy header is gone",
                       at="b000313"),
                commit("feat(api): add pagination", "Dee Okafor", at="b000314"),
                commit("revert: undo the header change", "Eli Moss",
                       body="Reverts: b000313", at="b000315"),
                commit("docs(readme): tidy", "Fay Ito", at="b000316"),
                end()]
    return s


def write(target, histories):
    target.mkdir(parents=True, exist_ok=True)
    for name, records in sorted(histories.items()):
        text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in records)
        (target / (name + ".history")).write_text(text, encoding="utf-8",
                                                  newline="\n")


def main():
    samples = benign()
    write(SAMPLES, samples)
    write(HELD_OUT, held_out())

    expected = {}
    for name in sorted(samples):
        text = (SAMPLES / (name + ".history")).read_text(encoding="utf-8")
        expected[name] = reference_notes.replay_text(text)
    (SAMPLES / "expected.json").write_text(
        json.dumps(expected, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")

    print("samples  : %d" % len(samples))
    print("held-out : %d" % len(held_out()))
    print("expected.json written")


if __name__ == "__main__":
    main()
