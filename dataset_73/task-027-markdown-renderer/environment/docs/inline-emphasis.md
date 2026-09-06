# Inline emphasis

Both `*` and `_` produce emphasis: a single run gives `<em>`, a doubled run
gives `<strong>`.

They are not interchangeable, and the difference is the one that matters in
practice, because our documentation is full of Python identifiers:

> A `*` run may open or close emphasis anywhere, including inside a word.
> A `_` run may not.

Stated precisely enough to implement: an `_` run that follows an alphanumeric
character cannot open emphasis, and an `_` run that is followed by an
alphanumeric character cannot close it. `*` runs carry no such restriction.

That single rule is what keeps `my_var_name`, `snake_case`, `a_b_c` and URL
paths containing underscores intact while `_italic_` and `__bold__` still work.

`../corpus/identifiers.md` and its `.html` sibling pin the behaviour case by
case. Note that an identifier written inside a code span is protected by the
code-span rule instead (see `rendering-style.md`), which is how `__init__` is
normally written in our prose.
