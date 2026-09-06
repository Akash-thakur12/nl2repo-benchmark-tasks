"""The migration catalog and its checksums (spec section 1)."""
import hashlib

CR_LF = "\r\n"
CR = "\r"
LF = "\n"


def normalize(body):
    """The form a body is stored in, which is the form that gets digested.

    1.3 says the runner digests the bodies as it stores them, not as they were
    typed, and points at samples/checksums.json for what that means. Row by row
    that file pins: CRLF and a lone CR become LF; spaces and tabs are stripped
    from the end of every line; trailing blank lines are dropped; leading and
    interior whitespace, case and content are left exactly as they are.

    This is why a Windows checkout, or an editor that trims on save, does not
    make a looked-after repository look drifted.
    """
    if not body:
        return ""
    text = body.replace(CR_LF, LF).replace(CR, LF)
    lines = [line.rstrip(" \t") for line in text.split(LF)]
    while lines and lines[-1] == "":
        lines.pop()
    return LF.join(lines)


def checksum(up, down=None):
    """1.3: normalize each body, then concatenate the two normalized bodies
    with no separator and take the lower-case hex sha256 of the result.

    Normalizing each body *before* concatenating is not the same as
    normalizing the concatenation. checksums.json ships two rows that pin the
    order - up ending in trailing spaces, and up ending in a newline - both of
    which must hash as though the bodies had been trimmed first.
    """
    material = normalize(up) + normalize(down)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class Migration:
    __slots__ = ("version", "name", "up", "down", "transactional", "fails")

    def __init__(self, record):
        self.version = record.get("version")
        self.name = record.get("name")
        self.up = record.get("up")
        self.down = record.get("down")
        self.transactional = record.get("transactional", True)
        self.fails = record.get("fails", False)

    @property
    def checksum(self):
        return checksum(self.up, self.down)

    @property
    def reversible(self):
        return self.down is not None


class Catalog:
    """Versioned migrations keyed by integer version, repeatables keyed by name."""

    def __init__(self):
        self.versioned = {}
        self.repeatable = {}

    def define(self, record):
        migration = Migration(record)
        if migration.version is None:              # 1.2
            self.repeatable[migration.name] = migration
        else:
            self.versioned[migration.version] = migration   # 1.5 replaces
        return migration

    def undefine(self, version):
        self.versioned.pop(version, None)

    def get(self, version):
        return self.versioned.get(version)

    def versions(self):
        # 1.4 ordered by the integer, so 10 follows 9
        return sorted(self.versioned)

    def repeatable_names(self):
        return sorted(self.repeatable)             # 6.1 ascending name order
