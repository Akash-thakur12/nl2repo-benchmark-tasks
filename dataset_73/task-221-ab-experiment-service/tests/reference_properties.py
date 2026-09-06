"""The properties a report must hold, derived from the brief.

An ambiguous task has no single correct report, so there is nothing to diff
against. What there is instead is a set of statements the brief actually makes,
each written here as a check over a capture and the report produced for it.

Every check returns a list of complaints; an empty list means it held. Nothing
here assumes anything the brief leaves open: not the hash, not the bucketing,
not whether traffic is gated before or after exclusivity, not the repository
layout.

This module is deleted before the candidate is invoked, exactly as a reference
model would be for a clear specification.
"""
import json

REASONS = ("ASSIGNED", "EXCLUDED", "NOT_IN_TRAFFIC", "STOPPED", "NOT_STARTED",
           "MUTUALLY_EXCLUDED", "UNKNOWN_EXPERIMENT")

#: 8. how thin a variant's share may get before it counts as never chosen
MINIMUM_SHARE = 0.05


def read_capture(text):
    """The capture as the checks need it: experiments in order, requests in
    order."""
    experiments = []
    by_key = {}
    requests = []
    for line in text.splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record["op"] == "experiment":
            experiments.append(record)
            by_key[record["key"]] = record
        elif record["op"] == "assign":
            requests.append(record)
    return {"experiments": experiments, "by_key": by_key, "requests": requests}


# ------------------------------------------------------------------- shape
def check_shape(capture, report):
    """2. One entry per request, in request order, and only what is documented."""
    complaints = []
    if sorted(report) != ["assignments", "errors", "summary"]:
        return ["the report does not have exactly the three documented keys"]

    assignments = report["assignments"]
    if not isinstance(assignments, list):
        return ["assignments is not an array"]
    if len(assignments) != len(capture["requests"]):
        complaints.append("%d assignments for %d requests"
                          % (len(assignments), len(capture["requests"])))
        return complaints
    for entry, request in zip(assignments, capture["requests"]):
        if not isinstance(entry, dict) or sorted(entry) != ["experiment", "reason",
                                                            "user", "variant"]:
            complaints.append("an assignment does not have the four documented fields")
            break
        if entry["user"] != request["user"] or \
                entry["experiment"] != request["experiment"]:
            complaints.append("the assignments are not in request order")
            break
        if entry["reason"] not in REASONS:
            complaints.append("undocumented reason %r" % (entry["reason"],))
            break

    for entry in report.get("errors", []):
        if not isinstance(entry, dict) or sorted(entry) != ["code", "detail"]:
            complaints.append("an error does not have exactly code and detail")
            break
        if entry["code"] != "UNKNOWN_EXPERIMENT":
            complaints.append("undocumented error code %r" % (entry["code"],))
            break
    return complaints


def check_variants_are_declared(capture, report):
    """3. Only a declared variant, and no variant without a reason to have one."""
    complaints = []
    for entry in report["assignments"]:
        experiment = capture["by_key"].get(entry["experiment"])
        if entry["variant"] is None:
            if entry["reason"] == "ASSIGNED":
                complaints.append("%s/%s is ASSIGNED with no variant"
                                  % (entry["user"], entry["experiment"]))
            continue
        if entry["reason"] != "ASSIGNED":
            complaints.append("%s/%s has a variant but reason %s"
                              % (entry["user"], entry["experiment"], entry["reason"]))
        if experiment is None:
            complaints.append("%s was given a variant of an experiment that does "
                              "not exist" % (entry["user"],))
            continue
        names = [variant["name"] for variant in experiment["variants"]]
        if entry["variant"] not in names:
            complaints.append("%s/%s was given %r, which is not one of its variants"
                              % (entry["user"], entry["experiment"], entry["variant"]))
    return complaints


def check_stability(capture, report):
    """4. The same person, the same experiment, the same answer."""
    complaints = []
    seen = {}
    for entry in report["assignments"]:
        key = (entry["user"], entry["experiment"])
        answer = (entry["variant"], entry["reason"])
        if key in seen and seen[key] != answer:
            complaints.append("%s/%s was answered two different ways: %r then %r"
                              % (key[0], key[1], seen[key], answer))
        seen.setdefault(key, answer)
    return complaints


def check_not_running(capture, report):
    """5. Stopped, draft and zero traffic assign nobody; full traffic assigns
    everybody who is eligible."""
    complaints = []
    for entry in report["assignments"]:
        experiment = capture["by_key"].get(entry["experiment"])
        if experiment is None:
            continue
        if experiment["state"] == "stopped" and entry["variant"] is not None:
            complaints.append("%s got a variant from stopped %s"
                              % (entry["user"], entry["experiment"]))
        if experiment["state"] == "draft" and entry["variant"] is not None:
            complaints.append("%s got a variant from draft %s"
                              % (entry["user"], entry["experiment"]))
        if experiment["traffic"] == 0 and entry["variant"] is not None:
            complaints.append("%s got a variant from %s at zero traffic"
                              % (entry["user"], entry["experiment"]))
        if experiment["state"] == "running" and experiment["traffic"] == 100 \
                and not experiment.get("exclusion_group") \
                and entry["user"] not in (experiment.get("exclude") or []) \
                and entry["variant"] is None:
            complaints.append("%s got nothing from %s, which is running at full "
                              "traffic" % (entry["user"], entry["experiment"]))
    return complaints


def check_exclusions(capture, report):
    """6. An excluded user is excluded."""
    complaints = []
    for entry in report["assignments"]:
        experiment = capture["by_key"].get(entry["experiment"])
        if experiment is None:
            continue
        if entry["user"] in (experiment.get("exclude") or []) \
                and entry["variant"] is not None:
            complaints.append("%s is excluded from %s but was given %r"
                              % (entry["user"], entry["experiment"],
                                 entry["variant"]))
    return complaints


def check_exclusion_groups(capture, report):
    """7. One variant per user per exclusion group."""
    complaints = []
    held = {}
    for entry in report["assignments"]:
        experiment = capture["by_key"].get(entry["experiment"])
        if experiment is None or entry["variant"] is None:
            continue
        group = experiment.get("exclusion_group")
        if group is None:
            continue
        key = (entry["user"], group)
        if key in held and held[key] != entry["experiment"]:
            complaints.append("%s holds a variant of both %s and %s, which share "
                              "exclusion group %s"
                              % (entry["user"], held[key], entry["experiment"],
                                 group))
        held.setdefault(key, entry["experiment"])
    return complaints


def check_spread(capture, report):
    """8. Equal weights at full traffic reach every variant, and a variant
    weighted zero reaches nobody."""
    complaints = []
    for experiment in capture["experiments"]:
        empty = {variant["name"] for variant in experiment["variants"]
                 if variant["weight"] == 0}
        for entry in report["assignments"]:
            if entry["experiment"] == experiment["key"] and entry["variant"] in empty:
                complaints.append("%s put %s in %s, which is weighted zero"
                                  % (experiment["key"], entry["user"],
                                     entry["variant"]))
    for experiment in capture["experiments"]:
        weights = {variant["weight"] for variant in experiment["variants"]}
        if experiment["state"] != "running" or experiment["traffic"] != 100 \
                or len(weights) != 1 or len(experiment["variants"]) < 2:
            continue
        chosen = [entry["variant"] for entry in report["assignments"]
                  if entry["experiment"] == experiment["key"]
                  and entry["variant"] is not None]
        if len(chosen) < 200:
            continue
        for variant in experiment["variants"]:
            share = chosen.count(variant["name"]) / len(chosen)
            if share < MINIMUM_SHARE:
                complaints.append("%s put %.1f%% of %d users in %s"
                                  % (experiment["key"], 100 * share, len(chosen),
                                     variant["name"]))
    return complaints


def check_summary(capture, report):
    """9. The summary is the assignments, counted."""
    complaints = []
    summary = report["summary"]
    if not isinstance(summary, list):
        return ["summary is not an array"]
    if [row.get("experiment") for row in summary] != \
            [experiment["key"] for experiment in capture["experiments"]]:
        return ["the summary does not list every declared experiment in order"]

    for row, experiment in zip(summary, capture["experiments"]):
        if sorted(row) != ["experiment", "unassigned", "variants"]:
            complaints.append("%s: a summary row does not have the three "
                              "documented fields" % experiment["key"])
            continue
        names = [variant["name"] for variant in experiment["variants"]]
        if [item.get("variant") for item in row["variants"]] != names:
            complaints.append("%s: the summary does not count every declared "
                              "variant in order" % experiment["key"])
            continue
        for item in row["variants"]:
            counted = sum(1 for entry in report["assignments"]
                          if entry["experiment"] == experiment["key"]
                          and entry["variant"] == item["variant"])
            if item.get("count") != counted:
                complaints.append("%s/%s is counted %r but listed %d times"
                                  % (experiment["key"], item["variant"],
                                     item.get("count"), counted))
        unassigned = sum(1 for entry in report["assignments"]
                         if entry["experiment"] == experiment["key"]
                         and entry["variant"] is None)
        if row.get("unassigned") != unassigned:
            complaints.append("%s: unassigned is %r but %d requests got nothing"
                              % (experiment["key"], row.get("unassigned"),
                                 unassigned))
    return complaints


def check_unknown_experiments(capture, report):
    """10. A request for an experiment nobody declared is reported, not fatal."""
    complaints = []
    wanted = [request["experiment"] for request in capture["requests"]
              if request["experiment"] not in capture["by_key"]]
    for entry in report["assignments"]:
        if entry["experiment"] in capture["by_key"]:
            continue
        if entry["variant"] is not None or entry["reason"] != "UNKNOWN_EXPERIMENT":
            complaints.append("%s/%s should be an unknown experiment"
                              % (entry["user"], entry["experiment"]))
    reported = [error["detail"] for error in report.get("errors", [])
                if error.get("code") == "UNKNOWN_EXPERIMENT"]
    for key in set(wanted):
        if key not in reported:
            complaints.append("%s was asked for but never reported as unknown"
                              % (key,))
    return complaints


CHECKS = (
    ("shape", check_shape),
    ("variants", check_variants_are_declared),
    ("stability", check_stability),
    ("not_running", check_not_running),
    ("exclusions", check_exclusions),
    ("exclusion_groups", check_exclusion_groups),
    ("spread", check_spread),
    ("summary", check_summary),
    ("unknown", check_unknown_experiments),
)


def check_all(capture_text, report):
    """Every check, as {name: [complaints]} for the ones that had any."""
    capture = read_capture(capture_text)
    failures = {}
    for name, check in CHECKS:
        try:
            complaints = check(capture, report)
        except Exception as failure:
            complaints = ["%s: %s" % (type(failure).__name__, failure)]
        if complaints:
            failures[name] = complaints
    return failures
