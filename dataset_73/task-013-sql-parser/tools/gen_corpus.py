#!/usr/bin/env python3
"""Regenerate environment/samples/conformance/*.json from the reference engine.

The corpus is the normative expectation shipped to the implementer, so it must
never be hand-edited: run this after any change to solution/engine/ so the data
and the reference cannot drift apart.

Also re-checks environment/samples/rejects.txt: every line there must actually
raise ParseError under the reference.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
TASK = HERE.parent
sys.path.insert(0, str(TASK / "solution"))

from engine.engine import SqlParserEngine, ParseError  # noqa: E402

GROUPS = {
    "basics": [
        "SELECT a FROM t",
        "SELECT * FROM users",
        "SELECT a, b, c FROM t1",
        "SELECT DISTINCT a FROM t",
        "SELECT a FROM t;",
        "SELECT u.id AS uid, name n FROM users AS u",
        "select a from t where a > 1",
    ],
    "lexical": [
        "SELECT ID FROM Users",
        "SELECT u.Total AS Grand FROM Orders AS U",
        "SELECT a FROM Sales ORDER BY Region DESC, Amount",
        "SELECT a FROM t GROUP BY Dept, T.Region",
        "SELECT a FROM t WHERE Name LIKE 'A%'",
        "SELECT a FROM t WHERE City = 'New York'",
        "SELECT a FROM t WHERE s = 'it''s'",
        "SELECT left FROM t",
        "SELECT offset FROM t LIMIT 5 OFFSET 2",
        "SELECT a FROM orders inner",
        "SELECT a FROM orders left JOIN u ON u.id = orders.id",
        "SELECT a FROM t ORDER BY desc DESC",
        "SELECT a FROM t ORDER BY asc",
    ],
    "expressions": [
        "SELECT a FROM t WHERE age >= 21",
        "SELECT a FROM t WHERE a = 1 OR b = 2 AND c = 3",
        "SELECT a FROM t WHERE a = 1 OR b = 2 AND c = 3 OR d = 4",
        "SELECT a FROM t WHERE a = 1 AND b = 2 AND c = 3",
        "SELECT a FROM t WHERE (a = 1 OR b = 2) AND c = 3",
        "SELECT a FROM t WHERE NOT a IS NULL",
        "SELECT a FROM t WHERE a IS NOT NULL",
        "SELECT a FROM t WHERE NOT a IS NOT NULL",
        "SELECT a FROM t WHERE x IN (1, 2, 3)",
        "SELECT a FROM t WHERE x IN (-1, 0, 1)",
        "SELECT a FROM t WHERE balance > -100",
        "SELECT a FROM t WHERE ratio = 2.0",
        "SELECT a FROM t WHERE n = 2",
        "SELECT a FROM t WHERE a = NULL",
    ],
    "clauses": [
        "SELECT a FROM t GROUP BY a, b HAVING cnt > 1",
        "SELECT a FROM t ORDER BY name DESC, id",
        "SELECT a FROM t LIMIT 5 OFFSET 10",
        "SELECT a FROM t LIMIT 0",
    ],
    "joins": [
        "SELECT a FROM t1 INNER JOIN t2 ON t1.id = t2.tid",
        "SELECT a FROM t1 JOIN t2 ON t1.id = t2.tid",
        "SELECT a FROM t1 LEFT JOIN t2 ON t1.id = t2.id",
        "SELECT a FROM t1 RIGHT JOIN t2 ON t1.id = t2.tid",
        "SELECT DISTINCT u.id AS uid FROM users u "
        "LEFT JOIN orders o ON u.id = o.uid "
        "WHERE u.age >= 21 AND o.total IN (10, 20) "
        "GROUP BY u.id HAVING u.id > 0 "
        "ORDER BY u.id DESC LIMIT 5 OFFSET 2",
    ],
}

HEADER = ("Captured from the production front end. `ast` is exactly what "
          "parse(query) returns. Normative; see docs/README.md.")


def main():
    p = SqlParserEngine()
    out_dir = TASK / "environment" / "samples" / "conformance"
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for name, queries in GROUPS.items():
        cases = [{"query": q, "ast": p.parse(q)} for q in queries]
        payload = {"_comment": HEADER, "cases": cases}
        (out_dir / f"{name}.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        n += len(cases)
    print(f"wrote {n} conformance cases to {out_dir}")

    rejects = TASK / "environment" / "samples" / "rejects.txt"
    bad = []
    for line in rejects.read_text(encoding="utf-8").splitlines():
        q = line.strip()
        if not q or q.startswith("#"):
            continue
        try:
            p.parse(q)
        except ParseError:
            continue
        bad.append(q)
    if bad:
        print("REJECTS THAT DID NOT RAISE:", *bad, sep="\n  ")
        return 1
    print("rejects.txt: all lines raise ParseError")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
