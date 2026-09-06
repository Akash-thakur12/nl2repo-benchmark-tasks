#!/usr/bin/env python3
"""bin1check -- legacy BIN1 blob validator.

Written in 2019 against the then-current reader, kept because the hexdump and
header summary are still handy for triage. It has NOT been updated for the
2021-03 wire format revision; treat its diagnoses as hints, not verdicts.

    python tools/bin1check.py samples/intern-firstref-02.bin
    python tools/bin1check.py --hexdump samples/rev6-archive-06.bin
"""
import argparse
import struct
import sys

MAGIC = b"BIN1"


def hexdump(data, width=16):
    for offset in range(0, len(data), width):
        chunk = data[offset:offset + width]
        text = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print("%08x  %-*s  |%s|"
              % (offset, width * 3, chunk.hex(" "), text))


def check(path, dump=False):
    data = open(path, "rb").read()
    print("== %s (%d bytes)" % (path, len(data)))
    if dump:
        hexdump(data)
    if data[:4] != MAGIC:
        print("ERROR: bad magic %r" % (data[:4],))
        return 1
    if len(data) < 6:
        print("ERROR: truncated header")
        return 1
    count = struct.unpack("<H", data[4:6])[0]
    print("header: magic=BIN1 count=%d" % count)

    offset = 6
    problems = 0
    for index in range(count):
        if offset + 3 > len(data):
            print("ERROR record %d: truncated record header" % index)
            return 1
        tag = data[offset]
        name_len = struct.unpack("<H", data[offset + 1:offset + 3]) [0]
        offset += 3
        remaining = len(data) - offset
        if name_len + 4 > remaining:
            print("ERROR record %d: name_len=%d exceeds remaining buffer "
                  "(%d bytes); blob is truncated or was written by a "
                  "big-endian host (see docs/attic/2019-endianness.md)"
                  % (index, name_len, remaining))
            return 1
        name = data[offset:offset + name_len]
        offset += name_len
        value = struct.unpack("<I", data[offset:offset + 4])[0]
        offset += 4
        try:
            shown = name.decode("utf-8")
        except UnicodeDecodeError:
            shown = repr(name)
            problems += 1
            print("WARN record %d: name is not valid UTF-8" % index)
        print("  [%3d] tag=0x%02x name=%-16s value=%d"
              % (index, tag, shown, value))
    if offset != len(data):
        print("WARN: %d trailing bytes after the last record"
              % (len(data) - offset))
        problems += 1
    return 1 if problems else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("blob", nargs="+")
    parser.add_argument("--hexdump", action="store_true")
    args = parser.parse_args()
    status = 0
    for path in args.blob:
        status |= check(path, args.hexdump)
    return status


if __name__ == "__main__":
    sys.exit(main())
