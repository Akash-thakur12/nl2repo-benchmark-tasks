"""RFC 4180 reader (spec section 1)."""

BOM = "﻿"
LF = "\n"
CR = "\r"


def read(body):
    """Split a drop body into records.

    Returns a list of (line, fields) pairs, where `line` is the 1-based physical
    line of the body the record BEGINS on. A quoted field may hold line breaks
    (1.2), so one record can cover several physical lines and a record's ordinal
    is not its line. The partner reads the file they sent us, so the line we
    quote back has to be the line they would scroll to.

    Blank lines survive as [""] so the caller can skip them (1.6) while the
    numbering stays tied to the file.
    """
    if body.startswith(BOM):            # 1.4
        body = body[len(BOM):]

    records = []
    field = []
    row = []
    in_quotes = False
    field_was_quoted = False
    index = 0
    end = len(body)
    line = 1                            # physical line we are reading
    start_line = 1                      # physical line the record began on

    while index < end:
        char = body[index]

        if in_quotes:
            if char == '"':
                if index + 1 < end and body[index + 1] == '"':
                    field.append('"')   # 1.2 an escaped quote
                    index += 2
                    continue
                in_quotes = False
                index += 1
                continue
            if char == LF:              # a physical line ends inside the field
                line += 1
            field.append(char)
            index += 1
            continue

        # 1.3 a quote only opens a field at the very start of that field
        if char == '"' and not field and not field_was_quoted:
            in_quotes = True
            field_was_quoted = True
            index += 1
            continue

        if char == ",":
            row.append("".join(field))
            field = []
            field_was_quoted = False
            index += 1
            continue

        # 1.1 both LF and CRLF terminate a record
        if char == LF or (char == CR and index + 1 < end and body[index + 1] == LF):
            row.append("".join(field))
            records.append((start_line, row))
            field = []
            row = []
            field_was_quoted = False
            index += 2 if char == CR else 1
            line += 1
            start_line = line
            continue

        field.append(char)
        index += 1

    # 1.5 a trailing terminator does not invent an extra record
    if field or row or field_was_quoted:
        row.append("".join(field))
        records.append((start_line, row))
    return records


def is_blank(record):
    return record == [""]
