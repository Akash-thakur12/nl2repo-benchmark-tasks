"""Subjects, versions and the operations on them (spec sections 3 to 6)."""
import json

from .schema import can_read, identity

LEVELS = ("NONE", "BACKWARD", "FORWARD", "FULL",
          "BACKWARD_TRANSITIVE", "FORWARD_TRANSITIVE", "FULL_TRANSITIVE")

TRANSITIVE = "_TRANSITIVE"


class Version:
    def __init__(self, number, schema, schema_id):
        self.number = number
        self.schema = schema
        self.id = schema_id
        self.gone = False

    def brief(self):
        return {"version": self.number, "id": self.id}


class Subject:
    def __init__(self, name, level):
        self.name = name
        self.level = level
        self.all = []
        self.counter = 0            # 4.5 numbers are never reused

    def remaining(self):
        return [version for version in self.all if not version.gone]   # 3.4

    def holding(self, mark):
        """4.3 the same schema, among the versions that are still there."""
        for version in self.remaining():
            if identity(version.schema) == mark:
                return version
        return None

    def add(self, schema, schema_id):
        self.counter += 1
        version = Version(self.counter, schema, schema_id)
        self.all.append(version)
        return version


class Service:
    def __init__(self, config):
        self.fallback_level = config["default_compatibility"]
        self.subjects = {}
        self.seen = []              # subject names, in first appearance order
        self.catalogue = {}         # schema identity -> id, registry wide (4.6)
        self.results = []
        self.errors = []

    # -------------------------------------------------------------- helpers
    def _fail(self, code, detail):
        self.errors.append({"code": code, "detail": detail})           # 6.3

    def _open(self, name):
        """4.1, 4.2 the subject, made if this is the first anyone hears of it."""
        subject = self.subjects.get(name)
        if subject is None:
            subject = Subject(name, self.fallback_level)
            self.subjects[name] = subject
            self.seen.append(name)
        return subject

    def _identify(self, schema):
        mark = identity(schema)
        if mark not in self.catalogue:                                 # 4.6
            self.catalogue[mark] = len(self.catalogue) + 1
        return self.catalogue[mark]

    def _accepts(self, subject, schema):
        """Section 3."""
        level = subject.level
        if level == "NONE":                                            # 3.1
            return True
        against = subject.remaining()                                  # 3.4
        if not against:                                                # 3.5
            return True
        transitive = level.endswith(TRANSITIVE)
        if not transitive:
            against = against[-1:]                                     # 3.3
            direction = level
        else:
            direction = level[: -len(TRANSITIVE)]                      # 3.2
        for version in against:
            if direction in ("BACKWARD", "FULL") and \
                    not can_read(schema, version.schema):
                return False
            if direction in ("FORWARD", "FULL") and \
                    not can_read(version.schema, schema):
                return False
        return True

    # ----------------------------------------------------------- operations
    def register(self, record):
        subject = self._open(record["subject"])
        schema = record["schema"]

        already = subject.holding(identity(schema))
        if already is not None:                                        # 4.3
            self._result("register", subject.name, version=already.number,
                         id=already.id, created=False)
            return
        if not self._accepts(subject, schema):                         # 4.4
            self._fail("INCOMPATIBLE", subject.name)
            self._result("register", subject.name, version=None, id=None,
                         created=False)
            return
        version = subject.add(schema, self._identify(schema))           # 4.5
        self._result("register", subject.name, version=version.number,
                     id=version.id, created=True)

    def check(self, record):
        subject = self.subjects.get(record["subject"])                 # 5.2
        verdict = True if subject is None else self._accepts(subject,
                                                             record["schema"])
        self._result("check", record["subject"], compatible=verdict)

    def lookup(self, record):
        subject = self.subjects.get(record["subject"])
        if subject is None:                                            # 5.3
            self._fail("UNKNOWN_SUBJECT", record["subject"])
            self._result("lookup", record["subject"], version=None, id=None)
            return
        found = subject.holding(identity(record["schema"]))
        self._result("lookup", subject.name,
                     version=found.number if found else None,
                     id=found.id if found else None)

    def delete_version(self, record):
        subject = self.subjects.get(record["subject"])
        if subject is None:                                            # 5.4
            self._fail("UNKNOWN_SUBJECT", record["subject"])
            self._result("delete_version", record["subject"], version=None)
            return
        for version in subject.remaining():
            if version.number == record["version"]:
                version.gone = True
                self._result("delete_version", subject.name,
                             version=version.number)
                return
        self._fail("UNKNOWN_VERSION", str(record["version"]))
        self._result("delete_version", subject.name, version=None)

    def set_compatibility(self, record):
        subject = self._open(record["subject"])                        # 5.5
        if record["level"] in LEVELS:
            subject.level = record["level"]
        else:
            self._fail("INVALID_LEVEL", record["level"])
        self._result("set_compatibility", subject.name, level=subject.level)

    def _result(self, op, subject, **rest):
        entry = {"op": op, "subject": subject}
        entry.update(rest)
        self.results.append(entry)                                     # 6.1

    # --------------------------------------------------------------- report
    def report(self):
        return {
            "results": self.results,                                   # 6.1
            "subjects": [{"name": name,
                          "compatibility": self.subjects[name].level,
                          "versions": [v.brief()
                                       for v in self.subjects[name].remaining()]}
                         for name in self.seen],                       # 6.2
            "errors": self.errors,                                     # 6.3
        }


OPERATIONS = ("register", "check", "lookup", "delete_version",
              "set_compatibility")


def replay_text(text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or records[0].get("op") != "config":
        raise ValueError("registry must begin with a config record")
    service = Service(records[0])
    for record in records[1:]:
        if record["op"] == "end":
            break
        if record["op"] not in OPERATIONS:
            raise ValueError("unknown op %r" % (record["op"],))
        getattr(service, record["op"])(record)
    return service.report()
