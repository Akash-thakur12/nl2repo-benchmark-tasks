"""Behaviour tests for the IEC 60529 marking engine.

Every marking used here is held out of environment/samples/: the corpora teach
the rules, they are not an answer table.
"""
import datetime

import pytest

from engine.engine import IpRatingEngine

CURRENT_EDITION = "IEC 60529:1989+A2:2013"


def engine():
    return IpRatingEngine()


# ---------------------------------------------------------------- decoding


@pytest.mark.parametrize("mark,solid", [
    ("IP01", "none"),
    ("IP12", "solid-1"),
    ("IP21", "solid-2"),
    ("IP33", "solid-3"),
    ("IP40", "solid-4"),
    ("IP53", "dust-protected"),
    ("IP67", "dust-tight"),
])
def test_first_characteristic_numeral_table(mark, solid):
    """The first characteristic numeral decodes per the standards register."""
    assert engine().describe(mark)["solid"] == solid


@pytest.mark.parametrize("mark,liquid", [
    ("IP10", "none"),
    ("IP21", "drip"),
    ("IP32", "drip-15"),
    ("IP43", "spray"),
    ("IP54", "splash"),
    ("IP25", "jet"),
    ("IP36", "powerful-jet"),
    ("IP47", "immersion-1m"),
    ("IP58", "submerged"),
])
def test_second_characteristic_numeral_table(mark, liquid):
    """The second characteristic numeral decodes per the standards register."""
    assert engine().describe(mark)["liquid"] == liquid


def test_full_decode_contract():
    """describe returns exactly the documented keys with the documented types."""
    assert engine().describe("IP54") == {
        "solid": "dust-protected",
        "liquid": "splash",
        "dust_tight": False,
        "access": "wire",
        "supplementary": None,
        "codes": ["IP54"],
        "edition": CURRENT_EDITION,
    }


@pytest.mark.parametrize("mark,expected", [
    ("IP67", True),
    ("IP60", True),
    ("IP57", False),
    ("IPX8", False),
    ("IP48", False),
])
def test_dust_tight_flag(mark, expected):
    """dust_tight is set only by a first characteristic that is dust-tight."""
    assert engine().describe(mark)["dust_tight"] is expected


def test_ip_prefix_optional_and_case_insensitive():
    """The IP prefix may be omitted and case is not significant."""
    e = engine()
    assert e.describe("68") == e.describe("IP68")
    assert e.describe("ip21")["solid"] == "solid-2"
    assert e.describe("ipx7") == e.describe("IPX7")


@pytest.mark.parametrize("mark", ["IP 67", "ip-67", " IP67 ", "I P 6 7"])
def test_separators_are_not_significant(mark):
    """Spaces and hyphens inside a marking carry no meaning."""
    assert engine().describe(mark) == engine().describe("IP67")


def test_codes_lists_each_code_in_canonical_form():
    """codes reports the marking's codes normalised, one entry per code."""
    e = engine()
    assert e.describe("ip-54")["codes"] == ["IP54"]
    assert e.describe("IP54/IPX8")["codes"] == ["IP54", "IPX8"]
    assert e.describe("ip2xch")["codes"] == ["IP2XCH"]


def test_first_numeral_outside_the_table_is_unknown():
    """A numeral that is stated but has no table entry decodes as unknown."""
    result = engine().describe("IP70")
    assert result["solid"] == "unknown"
    assert result["liquid"] == "none"
    assert result["dust_tight"] is False


def test_describe_is_deterministic():
    """describe is a pure function of its arguments."""
    first = engine().describe("IP65/IPX7", tested_on="2016-01-01")
    for _ in range(3):
        assert engine().describe("IP65/IPX7", tested_on="2016-01-01") == first


def test_reset_and_configure_are_noops():
    """The engine is stateless: reset and configure change nothing."""
    e = engine()
    reference = e.describe("IP54")
    e.reset()
    assert e.describe("IP54") == reference
    e.configure({"anything": True})
    assert e.describe("IP54") == reference


@pytest.mark.parametrize("bad", [123, None, ["6", "8"], 6.8, b"68", ("6", "8")])
def test_non_string_marking_raises(bad):
    """A marking that is not a string is a ValueError, not a TypeError."""
    with pytest.raises(ValueError):
        engine().describe(bad)


# --------------------------------------------------- placeholder and letters


def test_x_in_the_first_position():
    """X in the first position means that characteristic was not stated."""
    result = engine().describe("IPX5")
    assert result["solid"] == "unspecified"
    assert result["liquid"] == "jet"
    assert result["dust_tight"] is False


def test_x_in_the_second_position():
    """X in the second position means that characteristic was not stated."""
    result = engine().describe("IP3X")
    assert result["solid"] == "solid-3"
    assert result["liquid"] == "unspecified"


def test_both_positions_may_be_x():
    """A marking may state neither characteristic and still be valid."""
    result = engine().describe("IPXXC")
    assert result["solid"] == "unspecified"
    assert result["liquid"] == "unspecified"


@pytest.mark.parametrize("mark,supplementary", [
    ("IP55H", "high-voltage"),
    ("IP23W", "weather-conditions"),
    ("IP41M", "motion-during-water-test"),
    ("IP20S", "stationary-during-water-test"),
])
def test_supplementary_letter_is_decoded(mark, supplementary):
    """A supplementary letter decodes per the register and does not disturb the numerals."""
    result = engine().describe(mark)
    assert result["supplementary"] == supplementary
    assert result["liquid"] == engine().describe(mark[:4])["liquid"]


def test_supplementary_is_none_when_absent():
    """supplementary is None when the marking carries no supplementary letter."""
    assert engine().describe("IP54")["supplementary"] is None


def test_additional_and_supplementary_letters_together():
    """Both letters may appear, additional first."""
    result = engine().describe("IP1XCH")
    assert result["solid"] == "solid-1"
    assert result["access"] == "tool"
    assert result["supplementary"] == "high-voltage"


@pytest.mark.parametrize("mark,solid,liquid,dust_tight", [
    ("IP54/IPX8", "dust-protected", "submerged", False),
    ("IP6X/IPX7", "dust-tight", "immersion-1m", True),
    ("IP20/IP44", "solid-4", "splash", False),
])
def test_dual_marking_takes_the_highest_numeral_in_each_position(
        mark, solid, liquid, dust_tight):
    """A dual marking is read position by position, not code by code."""
    result = engine().describe(mark)
    assert result["solid"] == solid
    assert result["liquid"] == liquid
    assert result["dust_tight"] is dust_tight


# ------------------------------------------------------------- refused marks


@pytest.mark.parametrize("bad", ["", "  ", "IP", "IP6", "X", "IPX", "7"])
def test_fewer_than_two_characteristic_positions_raises(bad):
    """Both characteristic positions must be present."""
    with pytest.raises(ValueError):
        engine().describe(bad)


@pytest.mark.parametrize("bad", ["6Q", "IPZ4", "IP*5", "IP5#", "IPQQ"])
def test_characteristic_that_is_neither_numeral_nor_x_raises(bad):
    """A characteristic position holds a numeral or the placeholder X."""
    with pytest.raises(ValueError):
        engine().describe(bad)


@pytest.mark.parametrize("bad", ["IP654", "IP6X5", "1234"])
def test_third_numeral_raises(bad):
    """There is no third characteristic numeral."""
    with pytest.raises(ValueError):
        engine().describe(bad)


@pytest.mark.parametrize("bad", ["IP30SB", "IP11Q", "IP2XBD", "IP33HW"])
def test_letter_grammar_is_enforced(bad):
    """Letters must be known, in the clause 4.1 order, and not repeated."""
    with pytest.raises(ValueError):
        engine().describe(bad)


@pytest.mark.parametrize("bad", ["IP65/", "/IP65", "IP65//IP68"])
def test_empty_code_in_a_dual_marking_raises(bad):
    """Every code of a dual marking must itself be a marking."""
    with pytest.raises(ValueError):
        engine().describe(bad)


# ----------------------------------------------------------- access to parts


@pytest.mark.parametrize("mark,access", [
    ("IP01", "none"),
    ("IP12", "back-of-hand"),
    ("IP21", "finger"),
    ("IP33", "tool"),
    ("IP40", "wire"),
    ("IP53", "wire"),
    ("IP67", "wire"),
])
def test_access_is_derived_from_the_first_numeral(mark, access):
    """With no additional letter the first numeral itself fixes access protection."""
    assert engine().describe(mark)["access"] == access


def test_access_is_unspecified_without_a_numeral_or_a_letter():
    """X in the first position and no letter establishes no access protection."""
    assert engine().describe("IPX5")["access"] == "unspecified"


def test_access_is_unknown_for_a_numeral_outside_the_table():
    """A first numeral with no table entry leaves access unknown, not unspecified."""
    assert engine().describe("IP70")["access"] == "unknown"


@pytest.mark.parametrize("mark,access", [
    ("IP1XC", "tool"),
    ("IPXXB", "finger"),
    ("IP0XA", "back-of-hand"),
    ("IP2XD", "wire"),
])
def test_additional_letter_reports_access(mark, access):
    """When present the additional letter is the access protection."""
    assert engine().describe(mark)["access"] == access


@pytest.mark.parametrize("bad", ["IP53C", "IP4XB", "IP2XA", "IP66C", "IP65C"])
def test_additional_letter_below_the_implied_access_is_refused(bad):
    """A letter ranking below the access implied by the first numeral is a contradiction."""
    with pytest.raises(ValueError):
        engine().describe(bad)


@pytest.mark.parametrize("mark,access", [("IP53D", "wire"), ("IP2XB", "finger")])
def test_additional_letter_equal_to_the_implied_access_is_accepted(mark, access):
    """A letter that merely restates the implied access is redundant, not invalid."""
    assert engine().describe(mark)["access"] == access


def test_dual_marking_access_takes_the_highest_established():
    """Access over a dual marking is the best any of its codes establishes."""
    assert engine().describe("IPX7/IP4X")["access"] == "wire"


# ---------------------------------------------------------------- editions


def test_numeral_nine_has_no_meaning_before_the_amendment():
    """A mark tested before A2:2013 is read against the edition then in force."""
    assert engine().describe("IP59", tested_on="2010-06-01")["liquid"] == "unknown"


def test_numeral_nine_decodes_after_the_amendment():
    """A mark tested after A2:2013 is read against the amended table."""
    result = engine().describe("IP59", tested_on="2015-02-20")
    assert result["liquid"] == "high-pressure-jet"


def test_numeral_nine_decodes_when_no_test_date_is_given():
    """With no test date the current edition governs."""
    assert engine().describe("IP59")["liquid"] == "high-pressure-jet"


@pytest.mark.parametrize("day,liquid", [
    ("2013-07-31", "unknown"),
    ("2013-08-01", "high-pressure-jet"),
    ("2013-08-02", "high-pressure-jet"),
])
def test_amendment_takes_effect_on_its_effective_date(day, liquid):
    """The edition in force on the test date includes one effective that day."""
    assert engine().describe("IP59", tested_on=day)["liquid"] == liquid


@pytest.mark.parametrize("day,edition", [
    ("1990-01-01", "IEC 60529:1989"),
    ("1999-10-31", "IEC 60529:1989"),
    ("1999-11-01", "IEC 60529:1989+A1:1999"),
    ("2005-06-15", "IEC 60529:1989+A1:1999"),
    ("2020-01-01", "IEC 60529:1989+A2:2013"),
    (None, "IEC 60529:1989+A2:2013"),
])
def test_edition_reported_is_the_one_in_force(day, edition):
    """describe reports which register entry the marking was read against."""
    assert engine().describe("IP54", tested_on=day)["edition"] == edition


def test_amendment_inherits_the_tables_it_does_not_change():
    """An amendment entry is a delta, not a replacement table."""
    result = engine().describe("IP54", tested_on="2020-03-03")
    assert result["solid"] == "dust-protected"
    assert result["liquid"] == "splash"
    assert result["access"] == "wire"


def test_tested_on_accepts_date_objects():
    """The test date may be a date or a datetime as well as an ISO string."""
    e = engine()
    reference = e.describe("IP59", tested_on="2011-04-02")
    assert e.describe("IP59", tested_on=datetime.date(2011, 4, 2)) == reference
    assert e.describe("IP59",
                      tested_on=datetime.datetime(2011, 4, 2, 9, 30)) == reference


@pytest.mark.parametrize("bad_date", ["1980-01-01", "not-a-date", "2013-13-01"])
def test_test_date_the_register_does_not_cover_raises(bad_date):
    """A date with no edition in force, or which is not a date, is a ValueError."""
    with pytest.raises(ValueError):
        engine().describe("IP54", tested_on=bad_date)


def test_numerals_outside_the_table_on_an_old_date():
    """Both positions report unknown when neither is in the governing table."""
    result = engine().describe("79", tested_on="2005-01-01")
    assert result["solid"] == "unknown"
    assert result["liquid"] == "unknown"


# ------------------------------------------------------- meeting a spec


@pytest.mark.parametrize("mark,requirement,expected", [
    ("IP53", "IP31", True),
    ("IP31", "IP53", False),
    ("IP6X", "IP4X", True),
    ("IP4X", "IP6X", False),
    ("IP3X", "IP3X", True),
    ("IP3X", "IP4X", False),
])
def test_object_protection_is_a_cumulative_ladder(mark, requirement, expected):
    """A first numeral meets every lower first-numeral requirement."""
    assert engine().satisfies(mark, requirement) is expected


@pytest.mark.parametrize("mark,requirement,expected", [
    ("IPX6", "IPX5", True),
    ("IPX5", "IPX3", True),
    ("IPX4", "IPX0", True),
    ("IPX5", "IPX6", False),
])
def test_liquid_protection_is_cumulative_through_the_jet_tests(
        mark, requirement, expected):
    """Second numerals up to the jet tests form one cumulative ladder."""
    assert engine().satisfies(mark, requirement) is expected


@pytest.mark.parametrize("mark,requirement", [
    ("IPX7", "IPX5"),
    ("IPX7", "IPX6"),
    ("IP68", "IP66"),
    ("IP58", "IP55"),
])
def test_immersion_does_not_cover_the_jet_tests(mark, requirement):
    """An immersion rating is not a jet rating; that needs a dual code."""
    assert engine().satisfies(mark, requirement) is False


@pytest.mark.parametrize("mark,requirement", [
    ("IPX7", "IPX4"),
    ("IP58", "IP53"),
    ("IPX8", "IPX1"),
])
def test_immersion_still_covers_the_lower_series(mark, requirement):
    """The immersion numerals still meet the 0-4 requirements."""
    assert engine().satisfies(mark, requirement) is True


def test_eight_covers_seven_but_not_the_reverse():
    """Continuous immersion is the same test taken deeper."""
    e = engine()
    assert e.satisfies("IPX8", "IPX7") is True
    assert e.satisfies("IPX7", "IPX8") is False


@pytest.mark.parametrize("requirement,expected", [
    ("IPX4", True),
    ("IPX5", False),
    ("IPX6", False),
    ("IPX7", False),
])
def test_high_pressure_jet_is_its_own_test_method(requirement, expected):
    """Numeral 9 is a different apparatus, not the top of the jet ladder."""
    assert engine().satisfies("IPX9", requirement) is expected


@pytest.mark.parametrize("requirement", ["IPXX", "IPX1", "IP4X"])
def test_x_in_a_requirement_asks_for_nothing(requirement):
    """A requirement position filled with X places no demand."""
    assert engine().satisfies("IP41", requirement) is True


@pytest.mark.parametrize("mark,requirement", [
    ("IP4X", "IP40"),
    ("IPX1", "IP01"),
    ("IPXX", "IP00"),
])
def test_x_on_a_nameplate_establishes_nothing(mark, requirement):
    """An unstated characteristic satisfies no requirement, not even the lowest."""
    assert engine().satisfies(mark, requirement) is False


@pytest.mark.parametrize("mark,requirement", [
    ("IPX8", "IPX5"),
    ("IP53", "IP31"),
    ("IP6X/IPX7", "IP67"),
])
def test_covers_is_an_alias_of_satisfies(mark, requirement):
    """covers answers exactly what satisfies answers."""
    e = engine()
    assert e.covers(mark, requirement) is e.satisfies(mark, requirement)


@pytest.mark.parametrize("mark,requirement", [
    ("IP6", "IP65"),
    ("IP65", "IPZ4"),
    (None, "IP65"),
    ("IP65", 65),
])
def test_satisfies_refuses_malformed_arguments(mark, requirement):
    """Both arguments go through the same grammar as describe."""
    with pytest.raises(ValueError):
        engine().satisfies(mark, requirement)


# ------------------------------------------- dual markings and access probes


@pytest.mark.parametrize("mark,requirement", [
    ("IP6X/IPX7", "IP67"),
    ("IP54/IPX8", "IP58"),
    ("IP2X/IPX5", "IP25"),
])
def test_dual_marking_meets_what_no_single_code_meets(mark, requirement):
    """A dual marking is unioned position by position, not evaluated code by code."""
    e = engine()
    assert e.satisfies(mark, requirement) is True
    assert not any(e.satisfies(code, requirement) for code in mark.split("/"))


def test_dual_marking_union_is_not_a_free_pass():
    """The union still only covers what its codes actually establish."""
    assert engine().satisfies("IP54/IPX8", "IP56") is False


@pytest.mark.parametrize("mark,expected", [
    ("IP3X", True),
    ("IP4X", True),
    ("IP1X", False),
])
def test_access_requirement_can_be_met_by_the_numeral_alone(mark, expected):
    """A numeral implies access protection, so it can meet an access-letter requirement."""
    assert engine().satisfies(mark, "IPXXC") is expected


def test_access_and_object_protection_are_not_interchangeable():
    """The implication runs one way: a numeral implies access, a letter implies no object test."""
    e = engine()
    assert e.satisfies("IP3X", "IPXXC") is True
    assert e.satisfies("IPXXC", "IP3X") is False


def test_access_letters_form_their_own_ladder():
    """A higher access letter meets a lower one, and not the other way round."""
    e = engine()
    assert e.satisfies("IPXXD", "IPXXB") is True
    assert e.satisfies("IPXXB", "IPXXD") is False
    assert e.satisfies("IPXXC", "IPXXB") is True
    assert e.satisfies("IPXXB", "IPXXC") is False


@pytest.mark.parametrize("mark,requirement", [
    ("IP55H", "IP55"),
    ("IP55", "IP55W"),
    ("IP55M", "IP55W"),
])
def test_supplementary_letters_play_no_part_in_the_comparison(mark, requirement):
    """The supplementary letter records test conditions, not a degree of protection."""
    assert engine().satisfies(mark, requirement) is True


# ------------------------------------------------ sharpened crux coverage
#
# Everything below is pinned by the shipped corpora: the liquid exclusions and
# the access-by-numeral decisions come from samples/acceptance_log.csv, the
# refusals and the dual-mark decodes from samples/nameplate_marks.csv, and the
# effective dates from docs/iec60529-editions.json.


@pytest.mark.parametrize("mark,requirement", [
    ("IP68", "IP65"),
    ("IPX8", "IPX6"),
    ("IP58", "IP56"),
])
def test_continuous_immersion_does_not_cover_the_jet_tests(mark, requirement):
    """Numeral 8 is an immersion test; it is not the top of the jet ladder."""
    assert engine().satisfies(mark, requirement) is False


@pytest.mark.parametrize("requirement,expected", [
    ("IPX0", True),
    ("IPX3", True),
    ("IPX8", False),
    ("IPX9", True),
])
def test_numeral_nine_covers_only_the_low_series_and_itself(requirement, expected):
    """The high-pressure apparatus establishes the 0-4 series and nothing above it."""
    assert engine().satisfies("IPX9", requirement) is expected


@pytest.mark.parametrize("mark,requirement,expected", [
    ("IPX6/IPX8", "IPX6", True),
    ("IPX6/IPX8", "IPX8", True),
    ("IPX5/IPX8", "IPX6", False),
])
def test_a_dual_code_is_how_an_immersion_part_meets_a_jet_requirement(
        mark, requirement, expected):
    """The union covers what its codes were actually tested for, and no more."""
    assert engine().satisfies(mark, requirement) is expected


def test_decode_against_an_earlier_edition_keeps_the_unchanged_positions():
    """An older edition still decodes everything its tables do cover."""
    assert engine().describe("IP49", tested_on="2000-01-01") == {
        "solid": "solid-4",
        "liquid": "unknown",
        "dust_tight": False,
        "access": "wire",
        "supplementary": None,
        "codes": ["IP49"],
        "edition": "IEC 60529:1989+A1:1999",
    }


def test_the_base_edition_governs_from_the_day_it_came_into_force():
    """An entry is in force on its own effective date."""
    assert engine().describe(
        "IP54", tested_on="1989-11-15")["edition"] == "IEC 60529:1989"


def test_a_test_date_before_the_base_edition_raises():
    """The day before the base edition, no entry of the register is in force."""
    with pytest.raises(ValueError):
        engine().describe("IP54", tested_on="1989-11-14")


def test_a_dual_marking_is_read_against_the_edition_in_force():
    """Effective dating applies to every code of a dual marking."""
    result = engine().describe("IP65/IPX9", tested_on="2005-06-15")
    assert result["liquid"] == "unknown"
    assert result["edition"] == "IEC 60529:1989+A1:1999"


@pytest.mark.parametrize("bad", ["IP44C", "IP5XB", "IP6XA", "IP6XB", "IP55B",
                                 "IP4XC"])
def test_every_numeral_letter_contradiction_is_refused(bad):
    """The refusal is a rule about the pair, not a list of special cases."""
    with pytest.raises(ValueError):
        engine().describe(bad)


@pytest.mark.parametrize("mark,access", [
    ("IP44D", "wire"),
    ("IP1XA", "back-of-hand"),
    ("IP66D", "wire"),
])
def test_a_letter_restating_the_implied_access_is_accepted(mark, access):
    """Only a letter *below* the implied access is a contradiction."""
    assert engine().describe(mark)["access"] == access


@pytest.mark.parametrize("mark,requirement,expected", [
    ("IP5X", "IPXXD", True),
    ("IP6X", "IPXXD", True),
    ("IP3X", "IPXXD", False),
    ("IP2X", "IPXXC", False),
])
def test_an_access_requirement_is_answered_by_the_implied_access(
        mark, requirement, expected):
    """A bare first numeral answers an access-letter requirement up to what it implies."""
    assert engine().satisfies(mark, requirement) is expected


@pytest.mark.parametrize("mark,access", [
    ("IPXX/IP4X", "wire"),
    ("IPX8/IP2X", "finger"),
    ("IP2X/IPXXD", "wire"),
])
def test_dual_marking_access_comes_from_whichever_code_states_it(mark, access):
    """Access is unioned over the codes, not taken from the first one."""
    assert engine().describe(mark)["access"] == access


def test_dual_marking_solid_takes_the_highest_first_numeral():
    """The object position of a dual marking is the best any code establishes."""
    result = engine().describe("IP2X/IP4X")
    assert result["solid"] == "solid-4"
    assert result["dust_tight"] is False
