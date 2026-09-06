"""Behaviour tests for the W-shape flexural member selector.

Every expectation below is authored independently of the implementation under
test: the shape schedule is transcribed from environment/data/w_shapes.csv and
the expected selections are hand-checked against SDS-04 Revision B
(environment/docs/design_standard.md), the revision environment/docs/CHANGELOG.md
puts in force.
"""
import pytest

from engine.engine import SteelGaugePickEngine, NotFoundError, ValidationError

# Independently transcribed from environment/data/w_shapes.csv, in the mill
# schedule order that file uses:
#     designation -> (weight_plf, Sx in^3, Ix in^4, Lc ft, Lu ft)
CATALOG = {
    "W4x13": (13.0, 5.46, 11.3, 4.3, 15.6),
    "W6x9": (9.0, 6.20, 16.0, 4.2, 6.7),
    "W6x12": (12.0, 7.30, 22.0, 4.2, 8.6),
    "W6x16": (16.0, 9.50, 32.0, 4.3, 12.0),
    "W8x10": (10.0, 8.50, 30.0, 4.2, 4.7),
    "W8x13": (13.0, 9.70, 39.0, 4.2, 6.4),
    "W8x15": (15.0, 11.30, 48.0, 4.2, 7.2),
    "W8x18": (18.0, 13.40, 61.0, 5.2, 9.9),
    "W10x12": (12.0, 10.30, 53.0, 3.9, 4.3),
    "W10x15": (15.0, 12.00, 68.0, 4.2, 4.9),
    "W10x17": (17.0, 13.50, 81.0, 4.2, 6.1),
    "W10x19": (19.0, 15.00, 96.0, 4.2, 7.2),
    "W12x14": (14.0, 12.00, 88.0, 3.5, 4.2),
    "W12x16": (16.0, 13.40, 103.0, 4.1, 4.3),
    "W12x19": (19.0, 15.40, 130.0, 4.2, 5.3),
    "W12x22": (22.0, 17.40, 156.0, 4.3, 6.4),
    "W14x22": (22.0, 18.20, 199.0, 5.3, 5.6),
    "W14x26": (26.0, 21.40, 245.0, 5.3, 7.0),
    "W16x26": (26.0, 24.10, 301.0, 5.6, 6.0),
    "W18x35": (35.0, 33.20, 510.0, 6.0, 6.7),
}

WEIGHT = {name: props[0] for name, props in CATALOG.items()}
SX = {name: props[1] for name, props in CATALOG.items()}
IX = {name: props[2] for name, props in CATALOG.items()}
LU = {name: props[4] for name, props in CATALOG.items()}

DECK_BRACE_SPACING_FT = 6.0

GRID_SPANS = [5, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 33, 36, 40,
              44, 48]
GRID_SPACINGS = [2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0]


def _ids(value):
    """Parametrised-case ids without dots or spaces.

    The verifier counts test outcomes off pytest's ``-v`` progress lines with a
    word-character pattern, so a case id like ``[30-2.0-W10x19]`` would be
    skipped and the case would drop out of the score. Keeping ids in that
    character set means every case counts toward the pass ratio.
    """
    return (str(value).replace(".", "p").replace(" ", "")
            .replace("'", "").replace('"', ""))


def engine():
    return SteelGaugePickEngine()


# --------------------------------------------------------------------------
# Catalog membership and the shape of the return value
# --------------------------------------------------------------------------

def test_pick_returns_a_shape_from_the_schedule():
    """pick returns a designation that exists in the standard shape schedule,
    with that shape's own tabulated Sx and Ix."""
    e = engine()
    name, sx, ix = e.pick(10.0, 2.0)
    assert name in CATALOG
    assert sx == pytest.approx(SX[name])
    assert ix == pytest.approx(IX[name])


def test_returned_properties_are_rounded_as_specified():
    """Sx is rounded to 3 decimals and Ix to 2 decimals (instruction.md s2)."""
    e = engine()
    for span, spacing in [(10.0, 2.0), (22.0, 4.0), (33.0, 4.0), (40.0, 2.0)]:
        name, sx, ix = e.pick(span, spacing)
        assert sx == round(SX[name], 3)
        assert ix == round(IX[name], 2)


def test_spacing_defaults_to_two_feet():
    """spacing_ft defaults to 2.0 when the caller omits it."""
    e = engine()
    assert e.pick(24.0) == e.pick(24.0, 2.0)
    assert e.pick(24.0) != e.pick(24.0, 8.0)


# --------------------------------------------------------------------------
# Crux B - the selection rule is least weight_plf, not first schedule row
# --------------------------------------------------------------------------

@pytest.mark.parametrize("span", [5, 6, 8, 10, 12, 14, 16, 18], ids=_ids)
def test_short_span_plateau_selects_the_lightest_shape(span):
    """SDS-04 s5: the least-weight acceptable shape is selected. Across the
    short-span plateau that is W6x9 at 9.0 plf, not the heavier W4x13 that
    happens to head the mill-order schedule."""
    name, _, _ = engine().pick(float(span), 2.0)
    assert name == "W6x9"


@pytest.mark.parametrize("span,spacing,expected", [
    (10, 4.0, "W6x9"),
    (12, 8.0, "W6x12"),
    (16, 2.5, "W6x9"),
    (20, 2.0, "W6x12"),
    (22, 3.0, "W8x13"),
], ids=_ids)
def test_least_weight_beats_first_acceptable_schedule_row(span, spacing, expected):
    """SDS-04 s5: the schedule is in mill order (depth, then weight), which is
    not weight order, so the first acceptable row must not be returned."""
    name, _, _ = engine().pick(float(span), spacing)
    assert name == expected


@pytest.mark.parametrize("span,spacing", [
    (22, 8.0), (24, 6.0), (26, 5.0), (28, 5.0),
    (30, 4.0), (33, 3.0), (36, 2.5), (40, 2.0),
], ids=_ids)
def test_weight_tie_is_resolved_the_way_the_picks_log_records_it(span, spacing):
    """W14x26 and W16x26 both weigh 26.0 plf. Where both are acceptable the
    picks log (std_rev=B rows 21/8.0, 27/5.0, 31/4.0, 35/3.0, 42/2.0) records
    W14x26."""
    name, _, _ = engine().pick(float(span), spacing)
    assert name == "W14x26"


# --------------------------------------------------------------------------
# Crux H - three limit states on three different load cases
# --------------------------------------------------------------------------

@pytest.mark.parametrize("span,spacing,expected", [
    (22, 6.0, "W12x22"),
    (24, 6.0, "W14x26"),
    (26, 6.0, "W16x26"),
    (28, 6.0, "W18x35"),
    (33, 3.0, "W14x26"),
    (40, 3.0, "W18x35"),
], ids=_ids)
def test_dead_load_includes_member_self_weight(span, spacing, expected):
    """SDS-04 s2: the dead load includes the tabulated weight_plf of the member
    being checked, so the load depends on the candidate. Dropping self-weight
    under-designs each of these bays by one shape."""
    name, _, _ = engine().pick(float(span), spacing)
    assert name == expected


@pytest.mark.parametrize("span,spacing,expected", [
    (12, 6.0, "W6x9"),
    (14, 4.0, "W6x9"),
    (16, 3.0, "W6x9"),
    (18, 2.0, "W6x9"),
    (16, 8.0, "W8x15"),
    (14, 5.0, "W6x9"),
], ids=_ids)
def test_live_deflection_check_uses_the_live_load_alone(span, spacing, expected):
    """SDS-04 s3.2: the L/360 limit applies to the live load by itself. Running
    it on the total load over-designs each of these bays."""
    name, _, _ = engine().pick(float(span), spacing)
    assert name == expected


@pytest.mark.parametrize("span,spacing,expected", [
    (30, 2.5, "W10x19"),
    (30, 3.0, "W12x22"),
], ids=_ids)
def test_total_load_deflection_limit_is_enforced(span, spacing, expected):
    """SDS-04 s3.3: a separate L/240 limit applies to dead plus live. These two
    bays are governed by it and by nothing else."""
    name, _, _ = engine().pick(float(span), spacing)
    assert name == expected


def test_all_three_limit_states_bind_somewhere():
    """SDS-04 s3: strength, L/360 live and L/240 total each govern somewhere in
    the working range, so an implementation that omits any one of them differs
    from the reference on at least one bay in this set."""
    e = engine()
    governed = {
        (20, 8.0): "W12x22",    # strength, at the reduced allowable stress
        (18, 2.0): "W6x9",      # live-load L/360
        (30, 3.0): "W12x22",    # total-load L/240
    }
    for (span, spacing), expected in governed.items():
        assert e.pick(float(span), spacing)[0] == expected


# --------------------------------------------------------------------------
# Crux C - allowable stress depends on the unbraced length
# --------------------------------------------------------------------------

@pytest.mark.parametrize("span,spacing,expected", [
    (16, 8.0, "W8x15"),
    (20, 8.0, "W12x22"),
    (24, 6.0, "W14x26"),
    (33, 4.0, "W16x26"),
    (36, 2.5, "W14x26"),
], ids=_ids)
def test_allowable_stress_drops_between_lc_and_lu(span, spacing, expected):
    """SDS-04 s4: Fb is 21,600 psi, not 24,000 psi, when Lc < Lb <= Lu. A flat
    24,000 psi over-rates the shape and picks a lighter one on each of these."""
    name, _, _ = engine().pick(float(span), spacing)
    assert name == expected


@pytest.mark.parametrize("span,spacing,expected", [
    (12, 8.0, "W6x12"),
    (14, 6.0, "W6x12"),
    (16, 4.0, "W6x12"),
    (18, 5.0, "W8x13"),
    (20, 4.0, "W8x13"),
], ids=_ids)
def test_shapes_with_lu_shorter_than_lb_are_excluded(span, spacing, expected):
    """SDS-04 s4: a shape whose tabulated Lu is shorter than the unbraced length
    may not be used at all. Without that screen the light deep shapes (W8x10,
    W10x12, W12x14 ...) win these bays on weight."""
    name, _, _ = engine().pick(float(span), spacing)
    assert name == expected


@pytest.mark.parametrize("span,spacing,expected", [
    (28, 8.0, "W18x35"),
    (33, 4.0, "W16x26"),
    (44, 2.0, "W16x26"),
], ids=_ids)
def test_bracing_limits_are_inclusive(span, spacing, expected):
    """SDS-04 s4: Lc and Lu are inclusive at the 6.0 ft deck bracing. W18x35
    (Lc = 6.0) keeps the 24,000 psi allowable there and W16x26 (Lu = 6.0)
    stays eligible there; reading either limit as exclusive loses these bays."""
    name, _, _ = engine().pick(float(span), spacing)
    assert name == expected


def test_no_returned_shape_ever_violates_its_bracing_limit():
    """SDS-04 s4, as a grid-wide invariant: the selected shape always has
    Lu >= Lb, where Lb is the lesser of 6.0 ft and the span."""
    e = engine()
    for span in GRID_SPANS:
        unbraced = min(DECK_BRACE_SPACING_FT, float(span))
        for spacing in GRID_SPACINGS:
            try:
                name, _, _ = e.pick(float(span), spacing)
            except NotFoundError:
                continue
            assert LU[name] >= unbraced, (
                "%s (Lu=%s) returned at span=%s, spacing=%s where Lb=%s"
                % (name, LU[name], span, spacing, unbraced))


# --------------------------------------------------------------------------
# Crux I - only the revision in force is ground truth
# --------------------------------------------------------------------------

@pytest.mark.parametrize("span,spacing,expected", [
    (7, 2.0, "W6x9"),
    (13, 8.0, "W6x12"),
    (17, 8.0, "W10x17"),
    (19, 6.0, "W8x15"),
    (21, 8.0, "W14x26"),
    (23, 6.0, "W12x22"),
    (27, 6.0, "W16x26"),
    (31, 5.0, "W18x35"),
    (35, 2.0, "W12x22"),
    (38, 3.0, "W18x35"),
    (42, 2.0, "W14x26"),
], ids=_ids)
def test_reproduces_the_in_force_picks_log(span, spacing, expected):
    """CHANGELOG.md: the std_rev=B rows of legacy_picks.csv were recorded under
    the standard now in force and must be reproduced exactly."""
    name, _, _ = engine().pick(float(span), spacing)
    assert name == expected


@pytest.mark.parametrize("span,spacing,superseded", [
    (13, 8.0, "W6x16"),
    (21, 8.0, "W12x19"),
    (23, 3.0, "W8x18"),
    (27, 6.0, "W14x22"),
    (31, 5.0, "W14x26"),
    (35, 2.0, "W12x19"),
], ids=_ids)
def test_does_not_reproduce_the_superseded_picks_log(span, spacing, superseded):
    """CHANGELOG.md: std_rev=A rows are retained for audit only and must not be
    reproduced. These six bays appear under both revisions with different
    designations; the Revision A answer is the wrong one."""
    name, _, _ = engine().pick(float(span), spacing)
    assert name != superseded


def test_superseded_shapes_are_never_selected():
    """CHANGELOG.md / SDS-04 s4: the shapes whose Lu is shorter than the 6.0 ft
    deck bracing (W8x10, W10x12, W10x15, W12x14, W12x16, W12x19, W14x22) appear
    in Revision A picks and in no Revision B pick. None may be returned for any
    span of 6 ft or more."""
    forbidden = {name for name, lu in LU.items() if lu < DECK_BRACE_SPACING_FT}
    assert forbidden == {"W8x10", "W10x12", "W10x15", "W12x14", "W12x16",
                         "W12x19", "W14x22"}
    e = engine()
    for span in [s for s in GRID_SPANS if s >= DECK_BRACE_SPACING_FT]:
        for spacing in GRID_SPACINGS:
            try:
                name, _, _ = e.pick(float(span), spacing)
            except NotFoundError:
                continue
            assert name not in forbidden, (
                "%s returned at span=%s, spacing=%s" % (name, span, spacing))


# --------------------------------------------------------------------------
# Selection matrix across the working range
# --------------------------------------------------------------------------

@pytest.mark.parametrize("span,expected", [
    (8, "W6x9"), (14, "W6x9"), (18, "W6x9"), (20, "W6x12"),
    (24, "W8x13"), (26, "W8x15"), (30, "W10x17"), (36, "W12x22"),
    (44, "W16x26"), (48, "W18x35"),
], ids=_ids)
def test_selection_matrix_at_two_foot_spacing(span, expected):
    """End-to-end selection at 2.0 ft spacing."""
    name, sx, ix = engine().pick(float(span), 2.0)
    assert name == expected
    assert sx > 0 and ix > 0


@pytest.mark.parametrize("span,expected", [
    (10, "W6x9"), (16, "W6x12"), (18, "W8x13"), (22, "W10x17"),
    (26, "W10x19"), (28, "W12x22"), (30, "W14x26"), (33, "W16x26"),
    (36, "W18x35"),
], ids=_ids)
def test_selection_matrix_at_four_foot_spacing(span, expected):
    """End-to-end selection at 4.0 ft spacing."""
    name, _, _ = engine().pick(float(span), 4.0)
    assert name == expected


@pytest.mark.parametrize("span,expected", [
    (8, "W6x9"), (12, "W6x12"), (14, "W8x13"), (16, "W8x15"),
    (18, "W10x17"), (20, "W12x22"), (22, "W14x26"), (24, "W16x26"),
    (26, "W18x35"),
], ids=_ids)
def test_selection_matrix_at_eight_foot_spacing(span, expected):
    """End-to-end selection at 8.0 ft spacing."""
    name, _, _ = engine().pick(float(span), 8.0)
    assert name == expected


def test_longer_span_needs_a_stronger_section():
    """A longer span at the same spacing never selects a weaker section."""
    e = engine()
    n1, _, _ = e.pick(10.0, 2.0)
    n2, _, _ = e.pick(30.0, 2.0)
    assert SX[n2] > SX[n1]


# --------------------------------------------------------------------------
# Mechanism invariants
# --------------------------------------------------------------------------

def test_selected_weight_is_monotone_non_decreasing_in_span():
    """At a fixed spacing, increasing the span never selects a lighter shape."""
    e = engine()
    for spacing in GRID_SPACINGS:
        previous = None
        for span in GRID_SPANS:
            try:
                name, _, _ = e.pick(float(span), spacing)
            except NotFoundError:
                break
            if previous is not None:
                assert WEIGHT[name] >= WEIGHT[previous], (
                    "spacing=%s: span %s picked %s (%s plf) after %s (%s plf)"
                    % (spacing, span, name, WEIGHT[name], previous,
                       WEIGHT[previous]))
            previous = name


def test_selected_weight_is_monotone_non_decreasing_in_spacing():
    """At a fixed span, increasing the spacing never selects a lighter shape."""
    e = engine()
    for span in GRID_SPANS:
        previous = None
        for spacing in GRID_SPACINGS:
            try:
                name, _, _ = e.pick(float(span), spacing)
            except NotFoundError:
                break
            if previous is not None:
                assert WEIGHT[name] >= WEIGHT[previous], (
                    "span=%s: spacing %s picked %s (%s plf) after %s (%s plf)"
                    % (span, spacing, name, WEIGHT[name], previous,
                       WEIGHT[previous]))
            previous = name


# --------------------------------------------------------------------------
# No acceptable shape
# --------------------------------------------------------------------------

@pytest.mark.parametrize("span,spacing", [
    (500.0, 2.0), (30.0, 8.0), (44.0, 4.0), (48.0, 3.0), (36.0, 6.0),
], ids=_ids)
def test_no_acceptable_shape_raises_not_found(span, spacing):
    """SDS-04 s6: when the schedule admits nothing, the engine reports it as an
    error rather than falling back to the largest shape."""
    with pytest.raises(NotFoundError):
        engine().pick(span, spacing)


def test_not_found_boundary_is_tight():
    """SDS-04 s2 + s6: the boundary sits between 6.0 ft and 8.0 ft spacing at a
    30 ft span. It only lands there once self-weight is carried in the dead
    load; without it W18x35 appears to pass at 8.0 ft."""
    e = engine()
    assert e.pick(30.0, 6.0)[0] == "W18x35"
    with pytest.raises(NotFoundError):
        e.pick(30.0, 8.0)


# --------------------------------------------------------------------------
# Validation and determinism
# --------------------------------------------------------------------------

@pytest.mark.parametrize("length_ft,spacing_ft", [
    (0, 2.0), (-5, 2.0), (10.0, 0), (10.0, -1),
    ("10", 2.0), (None, 2.0), (10.0, "2"), ([10.0], 2.0),
], ids=_ids)
def test_invalid_inputs_raise_validation_error(length_ft, spacing_ft):
    """instruction.md s2: non-real or non-positive arguments raise
    ValidationError."""
    with pytest.raises(ValidationError):
        engine().pick(length_ft, spacing_ft)


@pytest.mark.parametrize("length_ft,spacing_ft", [
    (True, 2.0), (False, 2.0), (10.0, True),
], ids=_ids)
def test_bool_arguments_are_rejected(length_ft, spacing_ft):
    """instruction.md s2: bool is rejected even though it is an int subclass."""
    with pytest.raises(ValidationError):
        engine().pick(length_ft, spacing_ft)


def test_reset_and_configure_preserve_determinism():
    """instruction.md s3: pick is a pure function of its arguments; reset() and
    configure() do not change what it returns."""
    e = engine()
    first = e.pick(22.0, 4.0)
    assert e.pick(22.0, 4.0) == first
    e.reset()
    assert e.pick(22.0, 4.0) == first
    e.configure({})
    assert e.pick(22.0, 4.0) == first
    e.configure()
    assert e.pick(22.0, 4.0) == first
    assert SteelGaugePickEngine({"anything": 1}).pick(22.0, 4.0) == first
