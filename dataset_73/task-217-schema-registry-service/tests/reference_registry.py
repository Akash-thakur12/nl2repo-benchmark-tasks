"""Reference model for the schema registry, following docs/registry-spec.md
literally. Section numbers in comments refer to that document. This is the
authority for expected output; nothing is hardcoded.
"""
import json

# 2.1 what a value written as the key may be read as
PROMOTIONS = {
    "int": {"int", "long", "float", "double"},
    "long": {"long", "float", "double"},
    "float": {"float", "double"},
    "double": {"double"},
    "string": {"string", "bytes"},
    "bytes": {"bytes", "string"},
    "boolean": {"boolean"},
}

LEVELS = ("NONE", "BACKWARD", "FORWARD", "FULL",
          "BACKWARD_TRANSITIVE", "FORWARD_TRANSITIVE", "FULL_TRANSITIVE")

MISSING = object()


def fingerprint(schema):
    """1.3, 1.4 the schema's identity: fields in order, with defaults."""
    return tuple((field["name"], field["type"],
                  json.dumps(field["default"], sort_keys=True)
                  if "default" in field else None,
                  "default" in field)
                 for field in schema)


def promotes(written, read):
    return read in PROMOTIONS.get(written, set())                  # 2.1


def can_read(reader, writer):
    """2.2, 2.3 can `reader` read data written with `writer`?"""
    written = {field["name"]: field for field in writer}
    for field in reader:
        other = written.get(field["name"])
        if other is None:
            if "default" not in field:                             # 2.2 second
                return False
            continue
        if not promotes(other["type"], field["type"]):             # 2.2 first
            return False
    return True


class Version:
    def __init__(self, number, schema, schema_id):
        self.number = number
        self.schema = schema
        self.id = schema_id
        self.deleted = False


class Subject:
    def __init__(self, name, level):
        self.name = name
        self.level = level
        self.versions = []
        self.next_number = 1                                       # 4.5

    def live(self):
        return [v for v in self.versions if not v.deleted]          # 3.4

    def find(self, print_):
        for version in self.live():                                 # 4.3
            if fingerprint(version.schema) == print_:
                return version
        return None


class Registry:
    def __init__(self, config):
        self.default_level = config["default_compatibility"]
        self.subjects = {}
        self.order = []
        self.ids = {}            # fingerprint -> id, global (4.6)
        self.results = []
        self.errors = []

    # -------------------------------------------------------------- helpers
    def _error(self, code, detail):
        self.errors.append({"code": code, "detail": detail})        # 6.3

    def _subject(self, name, create):
        subject = self.subjects.get(name)
        if subject is None and create:
            subject = Subject(name, self.default_level)             # 4.1, 4.2
            self.subjects[name] = subject
            self.order.append(name)
        return subject

    def _id_for(self, schema):
        print_ = fingerprint(schema)
        if print_ not in self.ids:                                  # 4.6
            self.ids[print_] = len(self.ids) + 1
        return self.ids[print_]

    def _targets(self, subject):
        """3.3, 3.4 what a new schema is checked against."""
        live = subject.live()
        if subject.level == "NONE" or not live:
            return []
        if subject.level.endswith("_TRANSITIVE"):
            return live
        return [live[-1]]

    def _compatible(self, subject, schema):
        level = subject.level
        if level == "NONE":                                         # 3.1
            return True
        base = level[: -len("_TRANSITIVE")] if level.endswith("_TRANSITIVE") \
            else level
        for version in self._targets(subject):                      # 3.3
            if base in ("BACKWARD", "FULL") and \
                    not can_read(schema, version.schema):
                return False
            if base in ("FORWARD", "FULL") and \
                    not can_read(version.schema, schema):
                return False
        return True                                                 # 3.5

    # ----------------------------------------------------------- operations
    def op_register(self, record):
        subject = self._subject(record["subject"], create=True)
        schema = record["schema"]

        existing = subject.find(fingerprint(schema))
        if existing is not None:                                    # 4.3
            self.results.append({"op": "register", "subject": subject.name,
                                 "version": existing.number, "id": existing.id,
                                 "created": False})
            return

        if not self._compatible(subject, schema):                   # 4.4
            self._error("INCOMPATIBLE", subject.name)
            self.results.append({"op": "register", "subject": subject.name,
                                 "version": None, "id": None, "created": False})
            return

        version = Version(subject.next_number, schema,              # 4.5, 4.6
                          self._id_for(schema))
        subject.next_number += 1
        subject.versions.append(version)
        self.results.append({"op": "register", "subject": subject.name,
                             "version": version.number, "id": version.id,
                             "created": True})

    def op_check(self, record):
        subject = self.subjects.get(record["subject"])
        compatible = True if subject is None else \
            self._compatible(subject, record["schema"])             # 5.2
        self.results.append({"op": "check", "subject": record["subject"],
                             "compatible": compatible})

    def op_lookup(self, record):
        subject = self.subjects.get(record["subject"])
        if subject is None:                                         # 5.3
            self._error("UNKNOWN_SUBJECT", record["subject"])
            self.results.append({"op": "lookup", "subject": record["subject"],
                                 "version": None, "id": None})
            return
        found = subject.find(fingerprint(record["schema"]))
        self.results.append({"op": "lookup", "subject": subject.name,
                             "version": found.number if found else None,
                             "id": found.id if found else None})

    def op_delete_version(self, record):
        subject = self.subjects.get(record["subject"])
        if subject is None:                                         # 5.4
            self._error("UNKNOWN_SUBJECT", record["subject"])
            self.results.append({"op": "delete_version",
                                 "subject": record["subject"], "version": None})
            return
        wanted = record["version"]
        for version in subject.versions:
            if version.number == wanted and not version.deleted:
                version.deleted = True
                self.results.append({"op": "delete_version",
                                     "subject": subject.name,
                                     "version": version.number})
                return
        self._error("UNKNOWN_VERSION", str(wanted))
        self.results.append({"op": "delete_version", "subject": subject.name,
                             "version": None})

    def op_set_compatibility(self, record):
        subject = self._subject(record["subject"], create=True)     # 5.5
        level = record["level"]
        if level not in LEVELS:
            self._error("INVALID_LEVEL", level)
        else:
            subject.level = level
        self.results.append({"op": "set_compatibility", "subject": subject.name,
                             "level": subject.level})

    # -------------------------------------------------------------- report
    def report(self):
        return {
            "results": self.results,                                # 6.1
            "subjects": [{"name": name,
                          "compatibility": self.subjects[name].level,
                          "versions": [{"version": v.number, "id": v.id}
                                       for v in self.subjects[name].live()]}
                         for name in self.order],                   # 6.2
            "errors": self.errors,                                  # 6.3
        }


HANDLERS = {"register": "op_register", "check": "op_check",
            "lookup": "op_lookup", "delete_version": "op_delete_version",
            "set_compatibility": "op_set_compatibility"}


def replay(records):
    registry = Registry(records[0])
    for record in records[1:]:
        if record["op"] == "end":
            break
        handler = HANDLERS.get(record["op"])
        if handler is None:
            raise ValueError("unknown op %r" % (record["op"],))
        getattr(registry, handler)(record)
    return registry.report()


def replay_text(text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or records[0].get("op") != "config":
        raise ValueError("registry must begin with a config record")
    return replay(records)
