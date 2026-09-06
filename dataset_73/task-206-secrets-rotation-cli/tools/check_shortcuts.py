#!/usr/bin/env python3
"""Prove the corpus discriminates, rather than asserting that it does.

Every entry below is a plausible near-miss. For each one this asserts that it
still reproduces environment/samples/expected.json exactly, and that at least
one held-out session catches it.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_rotation as ref  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "sessions"


def m_dry_run_consumes_version(R):
    class M(R):
        def op_rotate(self, rec):
            if rec.get("dry_run"):
                self.highest += 1                     # burns a version number
                self._event("plan", version=self.highest,
                            envs=list(self.environments))
                return
            super().op_rotate(rec)
    return M


def m_dry_run_blocked_in_flight(R):
    class M(R):
        def op_rotate(self, rec):
            if rec.get("dry_run") and self.in_flight is not None:
                self.now = rec["t"]
                self._error("ROTATION_IN_FLIGHT", self.in_flight)
                return
            super().op_rotate(rec)
    return M


def m_rotate_restarts(R):
    class M(R):
        def op_rotate(self, rec):
            if not rec.get("dry_run") and self.in_flight is not None:
                self.now = rec["t"]
                self.highest += 1
                self.in_flight = self.highest
                self.completed = []
                self._begin_stage(0)                  # silently starts over
                return
            super().op_rotate(rec)
    return M


def m_sorted_env_order(R):
    class M(R):
        def __init__(self, config):
            super().__init__(config)
            self.environments = sorted(self.environments)
            self.healthy = {env: True for env in self.environments}
    return M


def m_empty_env_never_completes(R):
    class M(R):
        def _advance(self):
            while self.in_flight is not None:
                env = self.environments[self.stage_index]
                if not self.healthy[env]:
                    self._rollback(env)
                    return
                members = self._consumers_in(env)
                if not members:
                    return                            # waits for nobody, forever
                if any((c, self.in_flight) not in self.acks for c in members):
                    return
                self._event("complete", env=env, version=self.in_flight)
                self.completed.append(env)
                if self.stage_index + 1 < len(self.environments):
                    self._begin_stage(self.stage_index + 1)
                    continue
                self._finish()
                return
    return M


def m_early_acks_ignored(R):
    class M(R):
        def __init__(self, config):
            super().__init__(config)
            self._stage_started = {}

        def _begin_stage(self, index):
            super()._begin_stage(index)
            self._stage_started[self.environments[index]] = self.now

        def op_ack(self, rec):
            if rec["consumer"] in self.consumers:
                env = self.consumers[rec["consumer"]]
                started = self._stage_started.get(env)
                if started is None or rec["t"] < started:
                    self.now = rec["t"]
                    return                            # too early to count
            super().op_ack(rec)
    return M


def m_unknown_version_ack_errors(R):
    class M(R):
        def op_ack(self, rec):
            if rec["consumer"] in self.consumers and rec["version"] > self.highest \
                    and rec["version"] != self.in_flight:
                self.now = rec["t"]
                self._error("UNKNOWN_VERSION", rec["version"])
                return
            super().op_ack(rec)
    return M


def m_unknown_consumer_silent(R):
    class M(R):
        def op_ack(self, rec):
            self.now = rec["t"]
            if rec["consumer"] not in self.consumers:
                return                                # no error recorded
            self.acks.add((rec["consumer"], rec["version"]))
    return M


def m_unhealthy_skips(R):
    class M(R):
        def _advance(self):
            while self.in_flight is not None:
                env = self.environments[self.stage_index]
                if not self.healthy[env]:
                    self._event("complete", env=env, version=self.in_flight)
                    self.completed.append(env)        # skipped, not rolled back
                elif any((c, self.in_flight) not in self.acks
                         for c in self._consumers_in(env)):
                    return
                else:
                    self._event("complete", env=env, version=self.in_flight)
                    self.completed.append(env)
                if self.stage_index + 1 < len(self.environments):
                    self._begin_stage(self.stage_index + 1)
                    continue
                self._finish()
                return
    return M


def m_rollback_forward(R):
    class M(R):
        def _rollback(self, staging_env):
            version = self.in_flight
            for env in self.completed:                # rollout order, not reverse
                self._event("rollback", env=env, version=version)
            self._event("rollback", env=staging_env, version=version)
            self.acks = {(c, v) for (c, v) in self.acks if v != version}
            self.in_flight = None
            self.stage_index = None
            self.completed = []
    return M


def m_rollback_skips_staging_env(R):
    class M(R):
        def _rollback(self, staging_env):
            version = self.in_flight
            for env in reversed(self.completed):
                self._event("rollback", env=env, version=version)
            self.acks = {(c, v) for (c, v) in self.acks if v != version}
            self.in_flight = None
            self.stage_index = None
            self.completed = []
    return M


# Deliberately not listed as a shortcut. Acknowledgements are keyed by consumer
# and version, and rule 3.2 says a version number is never reused, so the
# acknowledgements of a discarded version can never be consulted again. Keeping
# them or forgetting them is unobservable, and pretending otherwise would mean
# writing a test that checks nothing. The clause stays in the specification
# because it tells an implementer what the intent is.
def m_rollback_keeps_acks(R):
    class M(R):
        def _rollback(self, staging_env):
            version = self.in_flight
            for env in reversed(self.completed):
                self._event("rollback", env=env, version=version)
            self._event("rollback", env=staging_env, version=version)
            self.in_flight = None                     # acks survive
            self.stage_index = None
            self.completed = []
    return M


def m_rollback_starts_grace(R):
    class M(R):
        def _rollback(self, staging_env):
            super()._rollback(staging_env)
            self.grace = (self.current, self.now, self.grace_seconds)
    return M


def m_version_reused_after_rollback(R):
    class M(R):
        def _rollback(self, staging_env):
            burnt = self.in_flight
            super()._rollback(staging_env)
            if self.highest == burnt:
                self.highest -= 1                     # hands the number back
    return M


def m_grace_exclusive(R):
    class M(R):
        def _sweep_grace(self):
            if self.grace is None:
                return
            version, started, window = self.grace
            if self.now - started > window:
                self.live.discard(version)
                self._event("revoked", version=version)
                self.grace = None
    return M


def m_grace_not_cut_short(R):
    class M(R):
        def _finish(self):
            version = self.in_flight
            self._event("rotated", version=version)
            previous = self.current
            self.current = version
            self.live.add(version)
            self.grace = (previous, self.now, self.grace_seconds)  # lingers
            self.in_flight = None
            self.stage_index = None
            self.completed = []
    return M


def m_no_revoked_event(R):
    class M(R):
        def _sweep_grace(self):
            if self.grace is None:
                return
            version, started, window = self.grace
            if self.now - started >= window:
                self.live.discard(version)
                self.grace = None                     # revocation goes unrecorded
    return M


def m_live_keeps_revoked(R):
    class M(R):
        def _sweep_grace(self):
            if self.grace is None:
                return
            version, started, window = self.grace
            if self.now - started >= window:
                self._event("revoked", version=version)
                self.grace = None                     # but live never shrinks
    return M


def m_reregistration_clears_acks(R):
    class M(R):
        def op_consumer(self, rec):
            self.now = rec["t"]
            if rec["env"] not in self.healthy:
                self._error("UNKNOWN_ENV", rec["env"])
                return
            if rec["id"] in self.consumers:
                self.acks = {(c, v) for (c, v) in self.acks if c != rec["id"]}
            self.consumers[rec["id"]] = rec["env"]
    return M


def m_raw_t_clock(R):
    """`self.now = rec["t"]` - the line every implementer writes."""
    class M(R):
        def _at(self, rec):
            self.now = rec["t"]                   # rewinds on a merged record
    return M


def m_policy_retunes_countdown(R):
    """A policy change recomputes a deadline that is already counting down."""
    class M(R):
        def _sweep_grace(self):
            if self.grace is None:
                return
            version, started, _window = self.grace
            if self.now - started >= self.grace_seconds:   # the current policy
                self.live.discard(version)
                self._event("revoked", version=version)
                self.grace = None
    return M


def m_policy_ignored(R):
    """The `policy` record is parsed and thrown away."""
    class M(R):
        def op_policy(self, rec):
            self._at(rec)
    return M


def m_snapshot_membership(R):
    """The cohort is frozen when the stage begins, so later moves are unseen."""
    class M(R):
        def _begin_stage(self, index):
            super()._begin_stage(index)
            self._snapshot = R._consumers_in(self, self.environments[index])

        def _consumers_in(self, env):
            if (self.in_flight is not None and self.stage_index is not None
                    and env == self.environments[self.stage_index]):
                return list(self._snapshot)
            return super()._consumers_in(env)
    return M


SHORTCUTS = [
    ("a dry run consumes a version number", m_dry_run_consumes_version),
    ("a dry run during a rotation is refused", m_dry_run_blocked_in_flight),
    ("rotating during a rotation silently restarts it", m_rotate_restarts),
    ("environments are staged in sorted name order", m_sorted_env_order),
    ("an environment with no consumers never completes", m_empty_env_never_completes),
    ("an acknowledgement before its stage begins is ignored", m_early_acks_ignored),
    ("an acknowledgement for an unknown version is an error", m_unknown_version_ack_errors),
    ("an acknowledgement from an unknown consumer is silently dropped", m_unknown_consumer_silent),
    ("an unhealthy environment is skipped rather than rolled back", m_unhealthy_skips),
    ("rollback names environments in rollout order", m_rollback_forward),
    ("rollback omits the environment that was staging", m_rollback_skips_staging_env),
    ("rollback starts a grace period", m_rollback_starts_grace),
    ("a rolled-back version number is handed back", m_version_reused_after_rollback),
    ("the grace boundary is exclusive", m_grace_exclusive),
    ("a new rotation does not cut a grace period short", m_grace_not_cut_short),
    ("revocation is not recorded as an event", m_no_revoked_event),
    ("the live set never drops a revoked version", m_live_keeps_revoked),
    ("re-registering a consumer clears its acknowledgements", m_reregistration_clears_acks),
    ("the clock is copied from the record instead of clamped", m_raw_t_clock),
    ("a policy change recomputes a running countdown", m_policy_retunes_countdown),
    ("the policy record is ignored", m_policy_ignored),
    ("stage membership is snapshotted when the stage begins", m_snapshot_membership),
]


def run(cls, text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    rotator = cls(records[0])
    for record in records[1:]:
        if record["op"] == "end":
            break
        getattr(rotator, ref.HANDLERS[record["op"]])(record)
        rotator._advance()
        rotator._sweep_grace()
    return rotator.report()


def main():
    sample_files = sorted(SAMPLES.glob("*.session"))
    held_files = sorted(HELD_OUT.glob("*.session"))
    expected = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))

    for f in sample_files:
        assert ref.replay_text(f.read_text(encoding="utf-8")) == expected[f.stem], \
            "reference disagrees with expected.json on %s" % f.stem

    truth = {f.stem: ref.replay_text(f.read_text(encoding="utf-8")) for f in held_files}

    bad, uncaught, rows = [], [], []
    for label, make in SHORTCUTS:
        cls = make(ref.Rotator)
        ok = True
        for f in sample_files:
            try:
                if run(cls, f.read_text(encoding="utf-8")) != expected[f.stem]:
                    ok = False
                    break
            except Exception:
                ok = False
                break
        caught = []
        for f in held_files:
            try:
                if run(cls, f.read_text(encoding="utf-8")) != truth[f.stem]:
                    caught.append(f.stem)
            except Exception:
                caught.append(f.stem)
        rows.append((label, ok, caught))
        if not ok:
            bad.append(label)
        if not caught:
            uncaught.append(label)

    width = max(len(r[0]) for r in rows)
    print("%-*s  %-8s  %s" % (width, "shortcut", "samples", "caught by"))
    print("-" * (width + 30))
    for label, ok, caught in rows:
        shown = ",".join(caught[:4]) + ("..." if len(caught) > 4 else "")
        print("%-*s  %-8s  %s" % (width, label, "pass" if ok else "FAIL",
                                  ("%d: %s" % (len(caught), shown)) if caught else "NONE"))
    print()
    print("shortcuts          : %d" % len(rows))
    print("reproduce samples  : %d" % sum(1 for r in rows if r[1]))
    print("caught by held-out : %d" % sum(1 for r in rows if r[2]))

    if bad:
        print("\nAlready rejected by the visible samples, so not evidence of anything:")
        for lb in bad:
            print("  -", lb)
    if uncaught:
        print("\nHOLE IN THE CORPUS - these survive every held-out session:")
        for lb in uncaught:
            print("  -", lb)
    if bad or uncaught:
        sys.exit(1)
    print("\nOK: every shortcut reproduces the samples and every one is caught.")


if __name__ == "__main__":
    main()
