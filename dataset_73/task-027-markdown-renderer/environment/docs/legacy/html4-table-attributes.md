# Table alignment attributes (HTML4 house style)

Status: SUPERSEDED 2025-11-04. Replaced by `rendering-style.md` v3.
Do not implement; retained for archive only.

----

House style for pipe tables is the HTML4 presentational attribute. When the
separator row carries alignment colons, put an `align` attribute on the header
cell. Body cells inherit visually from the column header in every browser we
support, so they are left bare — emitting the attribute on each `<td>` as well
just bloats the document.

Worked example:

    | Name | Qty |
    | :--- | --: |
    | nut  | 12  |

renders as

    <table><thead><tr><th align="left">Name</th><th align="right">Qty</th></tr></thead>
    <tbody><tr><td>nut</td><td>12</td></tr></tbody></table>

A column with a plain `---` separator gets `align="left"`, which is the HTML4
default for a data cell.
