import pytest
from engine.engine import ContainerEscapeEngine


@pytest.fixture
def e():
    return ContainerEscapeEngine()


SAFE = {"capabilities": [], "user": "1000:1000", "no_new_privileges": True,
        "mounts": [], "network_mode": "bridge"}


def test_safe_spec_scores_one(e):
    r = e.audit(SAFE)
    assert r["safe"] is True and r["risks"] == [] and r["score"] == 1.0


def test_empty_spec_is_safe(e):
    assert e.audit({})["safe"] is True


@pytest.mark.parametrize("spec,marker", [
    ({"capabilities": ["CAP_SYS_ADMIN"]}, "dangerous_caps"),
    ({"privileged": True}, "privileged"),
    ({"mounts": [{"src": "/"}]}, "sensitive_mount"),
    ({"mounts": [{"src": "/var/run/docker.sock"}]}, "sensitive_mount"),
    ({"no_new_privileges": False}, "no_new_privileges_disabled"),
    ({"user": "root"}, "running_as_root"),
    ({"network_mode": "host"}, "host_network"),
    ({"pid_mode": "host"}, "host_pid"),
])
def test_each_risk_category(e, spec, marker):
    risks = e.audit(spec)["risks"]
    assert any(marker in r for r in risks)
    assert e.audit(spec)["safe"] is False


def test_score_decreases_with_more_risks(e):
    one = e.audit({"privileged": True})["score"]
    two = e.audit({"privileged": True, "network_mode": "host"})["score"]
    assert two < one
    assert e.audit({"privileged": True, "network_mode": "host", "pid_mode": "host",
                    "capabilities": ["CAP_SYS_ADMIN"], "no_new_privileges": False,
                    "mounts": [{"src": "/"}]})["score"] == 0.0


def test_privileged_root_not_double_counted(e):
    # running_as_root only fires when NOT privileged
    risks = e.audit({"privileged": True, "user": "root"})["risks"]
    assert not any("running_as_root" in r for r in risks)


def test_harden_removes_dangerous_caps_and_flags(e):
    spec = {"capabilities": ["CAP_SYS_ADMIN", "CAP_NET_BIND_SERVICE"],
            "privileged": True, "user": "root", "no_new_privileges": False,
            "mounts": [{"src": "/"}, {"src": "/var/run/docker.sock"}, {"src": "/data"}],
            "network_mode": "host"}
    h = e.harden(spec)
    assert "CAP_SYS_ADMIN" not in h["capabilities"]
    assert "CAP_NET_BIND_SERVICE" in h["capabilities"]
    assert h["privileged"] is False and h["no_new_privileges"] is True
    assert h["user"] == "1000:1000"
    assert {m["src"] for m in h["mounts"]} == {"/data"}
    assert h["network_mode"] == "bridge"
    assert h["seccomp"] == "runtime/default"
    assert h["apparmor"] == "docker-default"


def test_harden_replaces_unset_user(e):
    bad = {"capabilities": [], "privileged": False}  # no "user" key at all
    h = e.harden(bad)
    assert h["user"] == "1000:1000"


def test_harden_replaces_empty_user(e):
    bad = {"capabilities": [], "user": "", "privileged": False}
    h = e.harden(bad)
    assert h["user"] == "1000:1000"


def test_harden_output_passes_audit(e):
    bad = {"capabilities": ["CAP_SYS_ADMIN"], "privileged": True, "user": "root",
           "no_new_privileges": False, "mounts": [{"src": "/proc"}],
           "network_mode": "host", "pid_mode": "host"}
    assert e.audit(e.harden(bad))["safe"] is True


def test_harden_is_idempotent(e):
    bad = {"capabilities": ["CAP_SYS_ADMIN"], "privileged": True,
           "mounts": [{"src": "/"}]}
    once = e.harden(bad)
    assert e.harden(once) == once


def test_reset_and_configure(e):
    ref = e.audit(SAFE)
    e.reset()
    assert e.audit(SAFE) == ref
    e.configure({})
    assert e.audit(SAFE) == ref
