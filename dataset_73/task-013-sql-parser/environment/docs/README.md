# SQL front-end: what is normative here

`samples/conformance/*.json` is the normative expectation for `parse()`. Each
entry is a `{"query": ..., "ast": ...}` pair captured from the production front
end; the `ast` value is the exact object `parse(query)` must return, key for key
and type for type. Where anything else in this repository disagrees with the
conformance corpus, the corpus wins.

`samples/rejects.txt` is the other half of the same contract: every line there
must raise `ParseError`.

`data/lexicon.tsv` is the word table the front end is built from. It splits the
vocabulary into two classes; the corpus shows what each class does in practice.

`docs/notes/` holds maintainer notes kept for history. They predate the
conformance corpus, they were never re-checked against it, and they are not
normative. Read them for context, not for answers.
