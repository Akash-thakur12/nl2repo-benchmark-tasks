#!/usr/bin/env python3
"""Regenerate the sample and held-out lint corpora, and samples/expected.json.

  samples/          Eight captures of queries that are already clean: keywords in
                    upper case, every column named, a WHERE on every statement,
                    every JOIN with its ON, no commas in the FROM list, no
                    ordering by position, no LIMIT, no trailing whitespace, no
                    tabs, no comments, no string literals and no configured
                    severities. Almost every plausible reading of the
                    specification reproduces expected.json here.

  tests/lints/      Held-out captures covering the rest: every rule at the place
                    it fires and the place next to it, strings and comments,
                    every form of noqa, configured and refused severities, and
                    the order violations come out in.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_lint  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "lints"


def config(rules=None):
    record = {"op": "config"}
    if rules is not None:
        record["rules"] = dict(rules)
    return record


def query(name, *lines):
    return {"op": "query", "name": name, "sql": "\n".join(lines)}


def end():
    return {"op": "end"}


# ------------------------------------------------------------ benign samples
def benign():
    # Already-clean queries: keywords in upper case, one named column, a WHERE
    # on every statement, every JOIN with its ON, no commas anywhere, no LIMIT,
    # no ordering by position, no trailing whitespace, no tabs, no comments, no
    # string literals and no configured severities.
    s = {}
    s["s01"] = [config(),
                query("orders",
                      "SELECT total",
                      "FROM orders",
                      "WHERE total > 0"),
                end()]
    s["s02"] = [config(),
                query("joined",
                      "SELECT o.id",
                      "FROM orders AS o",
                      "JOIN customers AS c ON c.id = o.customer_id",
                      "WHERE o.total > 0"),
                end()]
    s["s03"] = [config(),
                query("grouped",
                      "SELECT region",
                      "FROM sales",
                      "WHERE region_id > 0",
                      "GROUP BY region",
                      "ORDER BY region"),
                end()]
    s["s04"] = [config(),
                query("two_statements",
                      "SELECT id FROM a WHERE id > 0;",
                      "SELECT id FROM b WHERE id > 0"),
                end()]
    s["s05"] = [config(),
                query("wide",
                      "SELECT",
                      "    a",
                      "FROM t",
                      "WHERE a > 0"),
                end()]
    s["s06"] = [config(),
                query("nested_joins",
                      "SELECT a.id",
                      "FROM a",
                      "INNER JOIN b ON b.a_id = a.id",
                      "LEFT OUTER JOIN c ON c.b_id = b.id",
                      "WHERE a.id > 0"),
                end()]
    s["s07"] = [config(),
                query("one", "SELECT id FROM t WHERE id > 0"),
                query("two", "SELECT name FROM u WHERE name_id > 0"),
                end()]
    s["s08"] = [config(),
                query("ordered",
                      "SELECT created",
                      "FROM events",
                      "WHERE created > 0",
                      "ORDER BY created"),
                end()]
    return s


# --------------------------------------------------------- held-out corpus
def held_out():
    s = {}

    # -- L001, and the star that is not in the select list ------------------
    s["h01"] = [config(), query("q", "SELECT * FROM t WHERE id > 0"), end()]
    s["h02"] = [config(), query("q", "SELECT a * b FROM t WHERE id > 0"), end()]
    s["h03"] = [config(), query("q", "SELECT COUNT(*) FROM t WHERE id > 0"),
                end()]
    s["h04"] = [config(), query("q", "SELECT *"), end()]

    # -- L002, and the LIMIT that excuses it --------------------------------
    s["h05"] = [config(), query("q", "SELECT id FROM t"), end()]
    s["h06"] = [config(), query("q", "SELECT id FROM t LIMIT 10"), end()]
    s["h07"] = [config(), query("q", "SELECT id FROM t ORDER BY id LIMIT 10"),
                end()]

    # -- L003, and the ON that belongs to the next clause -------------------
    s["h08"] = [config(), query("q", "SELECT a FROM t JOIN u WHERE a > 0"),
                end()]
    s["h09"] = [config(),
                query("q", "SELECT a FROM t JOIN u ON u.id = t.id WHERE a > 0"),
                end()]
    s["h10"] = [config(),
                query("q",
                      "SELECT a",
                      "FROM t",
                      "JOIN u",
                      "JOIN v ON v.id = u.id",
                      "WHERE a > 0"),
                end()]

    # -- L004, and the comma that is in the select list ---------------------
    s["h11"] = [config(), query("q", "SELECT a FROM t, u WHERE a > 0"), end()]
    s["h12"] = [config(), query("q", "SELECT a, b FROM t WHERE a > 0"), end()]
    s["h13"] = [config(),
                query("q", "SELECT a FROM t WHERE a IN_LIST AND b > 0"), end()]

    # -- L005, on every keyword and nothing else ----------------------------
    s["h14"] = [config(), query("q", "select id from t where id > 0"), end()]
    s["h15"] = [config(), query("q", "SELECT Id FROM T WHERE Id > 0"), end()]
    s["h16"] = [config(), query("q", "Select id From t Where id > 0"), end()]

    # -- L006, and the column name that only looks like a position ----------
    s["h17"] = [config(),
                query("q", "SELECT a FROM t WHERE a > 0 ORDER BY 1"), end()]
    s["h18"] = [config(),
                query("q", "SELECT a FROM t WHERE a > 0 ORDER BY a, 2"), end()]
    s["h19"] = [config(),
                query("q", "SELECT a FROM t WHERE a > 0 ORDER BY a LIMIT 3"),
                end()]
    s["h20"] = [config(),
                query("q", "SELECT a FROM t WHERE a > 0 GROUP BY 1 ORDER BY a"),
                end()]

    # -- L007 ----------------------------------------------------------------
    s["h21"] = [config(), query("q", "SELECT a FROM t WHERE a > 0 LIMIT 10"),
                end()]
    s["h22"] = [config(),
                query("q", "SELECT a FROM t WHERE a > 0 ORDER BY a LIMIT 10"),
                end()]

    # -- L008 and L009, on the raw line -------------------------------------
    s["h23"] = [config(), query("q", "SELECT a FROM t WHERE a > 0   "), end()]
    s["h24"] = [config(), query("q", "SELECT a\t", "FROM t WHERE a > 0"), end()]
    s["h25"] = [config(), query("q", "SELECT a", "\tFROM t WHERE a > 0"), end()]
    s["h26"] = [config(), query("q", "SELECT a", "  \tFROM t WHERE a > 0"),
                end()]
    s["h27"] = [config(), query("q", "SELECT a", "FROM t\tWHERE a > 0"), end()]
    s["h28"] = [config(), query("q", "SELECT a FROM t WHERE a > 0", ""), end()]

    # -- strings and comments are not tokenised (2.1, 2.2, 2.4) -------------
    s["h29"] = [config(),
                query("q", "SELECT a FROM t WHERE b = 'select * from x'"),
                end()]
    s["h30"] = [config(),
                query("q", "SELECT a FROM t WHERE b = 'it''s select'"), end()]
    s["h31"] = [config(),
                query("q", "SELECT a FROM t -- select * from x", "WHERE a > 0"),
                end()]
    s["h32"] = [config(),
                query("q", "SELECT a FROM t WHERE b = 'unclosed -- select"),
                end()]

    # -- noqa, in each of its forms (section 6) -----------------------------
    s["h33"] = [config(), query("q", "SELECT * FROM t -- noqa"), end()]
    s["h34"] = [config(), query("q", "SELECT * FROM t -- noqa: L001"), end()]
    s["h35"] = [config(), query("q", "SELECT * FROM t -- noqa: L001, L002"),
                end()]
    s["h36"] = [config(), query("q", "SELECT * FROM t -- noqa:l001"), end()]
    s["h37"] = [config(), query("q", "SELECT * FROM t -- noqa please"), end()]
    s["h38"] = [config(),
                query("q", "select *  -- noqa", "from t"), end()]
    s["h39"] = [config(),
                query("q", "SELECT a -- noqa", "FROM t JOIN u"), end()]

    # -- severities (section 5) ----------------------------------------------
    s["h40"] = [config({"L001": "off"}), query("q", "SELECT * FROM t"), end()]
    s["h41"] = [config({"L001": "error", "L002": "style"}),
                query("q", "SELECT * FROM t"), end()]
    s["h42"] = [config({"L042": "error"}), query("q", "SELECT * FROM t"), end()]
    s["h43"] = [config({"L001": "loud"}), query("q", "SELECT * FROM t"), end()]
    s["h44"] = [config({"L042": "loud", "L001": "off"}),
                query("q", "SELECT * FROM t"), end()]

    # -- the order violations come out in, and the totals (7.1, 7.3) --------
    s["h45"] = [config(),
                query("q", "select * from t, u\tjoin v limit 1 "),
                end()]
    s["h46"] = [config(),
                query("one", "SELECT * FROM t"),
                query("two", "select a from u where a > 0"),
                query("three", "SELECT a FROM v WHERE a > 0"),
                end()]

    # -- more than one comma in the FROM list (L004) ------------------------
    s["h48"] = [config(), query("q", "SELECT a FROM t, u, v WHERE a > 0"), end()]

    # -- one SELECT after another with no semicolon between them (3.2) ------
    s["h49"] = [config(),
                query("q", "SELECT * FROM t WHERE a > 0 SELECT b FROM u"),
                end()]

    # -- ordering by position with no ORDER BY in sight (L006) --------------
    s["h50"] = [config(),
                query("q", "SELECT a FROM t WHERE a > 0 GROUP BY 1"), end()]

    # -- the ORDER BY list ends at the next clause keyword (L006) -----------
    s["h51"] = [config(),
                query("q", "SELECT a FROM t WHERE a > 0 ORDER BY a LIMIT 5, 10"),
                end()]

    # -- a star that is not in the select list at all (L001) ----------------
    s["h52"] = [config(), query("q", "SELECT a FROM t WHERE b = c * 2"), end()]

    # -- everything at once --------------------------------------------------
    s["h47"] = [config({"L009": "error", "L005": "off", "L999": "warning"}),
                query("messy",
                      "select *, count(*)  ",
                      "\tfrom orders, customers",
                      "join items -- noqa: L003",
                      "group by 1",
                      "order by 1, 2 -- noqa",
                      "limit 10;",
                      "SELECT id FROM t WHERE id = 'a -- b' LIMIT 1"),
                end()]
    return s


def write(target, captures):
    target.mkdir(parents=True, exist_ok=True)
    for name, records in sorted(captures.items()):
        text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in records)
        (target / (name + ".lint")).write_text(text, encoding="utf-8",
                                               newline="\n")


def main():
    samples = benign()
    write(SAMPLES, samples)
    write(HELD_OUT, held_out())

    expected = {}
    for name in sorted(samples):
        text = (SAMPLES / (name + ".lint")).read_text(encoding="utf-8")
        expected[name] = reference_lint.replay_text(text)
    (SAMPLES / "expected.json").write_text(
        json.dumps(expected, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")

    print("samples  : %d" % len(samples))
    print("held-out : %d" % len(held_out()))
    print("expected.json written")


if __name__ == "__main__":
    main()
