# IEC 60529 IP (Ingress Protection) marking decoder

## 1. Overview

Incoming inspection decides IP ratings by eye today, and it gets them wrong.
Build the engine behind the replacement tool. It has two jobs:

1. decode a marking as it appears on a nameplate into a structured description,
   read against the edition of the standard that was in force when the part was
   tested; and
2. answer the question inspection actually asks - *does this part's marking meet
   our purchasing requirement?*

Standard library only; code in `engine/`.

## 2. Reference material

Everything the engine has to know about the standard already ships in this
repository (at `/app/...` in the image). Read it before you write code - the
rules are in there, not in this file.

| path | what it is |
| --- | --- |
| `docs/ip-marking-guide.md` | the house guide to IEC 60529 marking: element order, the letters, the coverage principle, and how editions are handled |
| `docs/iec60529-editions.json` | export of the standards register: one entry per edition or amendment, each with the date it came into force, the entry it extends, and the tables it defines |
| `samples/nameplate_marks.csv` | export of markings the certification database has already decoded, and of markings it refused, with the refusal reason. **Normative** for what is accepted, what it decodes to, and what raises `ValueError`. |
| `samples/acceptance_log.csv` | export of incoming-inspection decisions: requirement, part marking, accept/reject, reviewer note. **Normative** for the comparison rules. |
| `tools/ip_lint.py` | an older internal linter. Read it if you like; it is not the specification. |

`engine/` must be self-contained: those files are inputs for you, the
implementer, not runtime inputs. The engine must not read them (or anything
else) at run time.

## 3. Public API - `engine/engine.py`

### `class IpRatingEngine`

- `__init__(self, config=None)` - `config` accepted and ignored.

- `describe(self, code, tested_on=None) -> dict`

  `code` is a marking as it appears on a nameplate.
  `samples/nameplate_marks.csv` is an export of markings the certification
  database has already decoded, and of markings it refused; it is normative for
  what is accepted and what raises `ValueError`.

  `tested_on` is the date the part was tested, as an ISO `YYYY-MM-DD` string or
  a `datetime.date`. `None` means no test date is on file.

  Returns a dict with exactly these keys:

  | key | type | meaning |
  | --- | --- | --- |
  | `solid` | `str` | what the first characteristic position says |
  | `liquid` | `str` | what the second characteristic position says |
  | `dust_tight` | `bool` | whether the enclosure is dust-tight |
  | `access` | `str` | protection against access to hazardous parts |
  | `supplementary` | `str` or `None` | the decoded supplementary letter, `None` when the marking carries none |
  | `codes` | `list[str]` | the codes the marking is made of, each in canonical form: `IP`, the two characteristic positions, then any letters, upper-case, separators removed |
  | `edition` | `str` | the `id` of the register entry the marking was read against |

  The words used in `solid`, `liquid`, `access` and `supplementary` are the ones
  the certification database uses - see the register and the sample export.

  Raises `ValueError` if `code` is not a string, if the marking is one the
  database refuses, or if `tested_on` is not a date the register covers.

- `satisfies(self, mark: str, requirement: str) -> bool`

  True when a part whose nameplate reads `mark` may be accepted against a
  purchasing requirement written as `requirement`. Both are markings in the same
  notation `describe` takes, and both raise `ValueError` when malformed.
  `samples/acceptance_log.csv` is normative for this comparison.

- `covers(self, mark: str, requirement: str) -> bool` - documented alias of
  `satisfies`, same result for the same arguments.

- `reset(self)` / `configure(self, options)` - no-ops (the engine is stateless).

## 4. Examples

```python
e = IpRatingEngine()

e.describe("IP54")["solid"]                 # -> what the register says for 5
e.describe("IP54")["dust_tight"]            # -> False
e.describe("IP69", tested_on="2011-04-02")  # -> read against the 2011 edition
e.satisfies("IP65/IP68", "IP65")            # -> True
e.satisfies("IPX7", "IPX5")                 # -> see samples/acceptance_log.csv
```

## 5. Determinism

`describe` and `satisfies` are pure functions of their arguments. Two engines
constructed the same way always agree, and `reset` / `configure` change nothing.

## 6. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0. The tests
use markings that are not in the sample exports, so the corpora have to be
understood rather than memorised.
