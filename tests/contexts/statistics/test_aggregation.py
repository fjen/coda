from decimal import Decimal

import pytest

from coda.contexts.statistics import dimensions
from coda.contexts.statistics.aggregation import group_by
from coda.contexts.statistics.dto import Measure
from tests.contexts.statistics.factories import institution, make_fact, source


def test__group_by_publisher__counts_each_request_under_its_own_value() -> None:
    facts = (
        make_fact(publisher="Elsevier", paid_out_total=Decimal("100.00")),
        make_fact(publisher="Elsevier", paid_out_total=Decimal("50.00")),
        make_fact(publisher="Springer", paid_out_total=Decimal("20.00")),
    )

    grouping = group_by(facts, dimensions.by_id("publisher"), measure=Measure.PUBLICATIONS)

    assert [(r.label, r.publications) for r in grouping.rows] == [
        ("Elsevier", 2),
        ("Springer", 1),
    ]
    assert grouping.additive
    assert grouping.total() == 3


def test__group_by_publisher__spend_measure_sums_the_gross_amounts_per_value() -> None:
    facts = (
        make_fact(publisher="Elsevier", paid_out_total=Decimal("100.00")),
        make_fact(publisher="Elsevier", paid_out_total=Decimal("50.00")),
        make_fact(publisher="Springer", paid_out_total=Decimal("20.00")),
    )

    grouping = group_by(facts, dimensions.by_id("publisher"), measure=Measure.PAID_OUT)

    assert [(r.label, r.amount) for r in grouping.rows] == [
        ("Elsevier", Decimal("150.00")),
        ("Springer", Decimal("20.00")),
    ]
    assert grouping.additive
    assert grouping.total() == Decimal("170.00")


def test__group_by_repeated_dimension__counts_the_request_in_full_under_every_value() -> None:
    facts = (
        make_fact(
            institutions=(institution("TU Berlin"), institution("Humboldt University")),
            paid_out_total=Decimal("100.00"),
        ),
    )

    publications = group_by(facts, dimensions.by_id("institution"), measure=Measure.PUBLICATIONS)
    spend = group_by(facts, dimensions.by_id("institution"), measure=Measure.PAID_OUT)

    assert [(r.label, r.publications) for r in publications.rows] == [
        ("Humboldt University", 1),
        ("TU Berlin", 1),
    ]
    assert [(r.label, r.amount) for r in spend.rows] == [
        ("Humboldt University", Decimal("100.00")),
        ("TU Berlin", Decimal("100.00")),
    ]
    assert not publications.additive
    assert not spend.additive
    assert publications.total() is None
    assert spend.total() is None


def test__group_by_single_dimension__groups_a_missing_value_as_unknown() -> None:
    facts = (
        make_fact(publisher="Elsevier", paid_out_total=Decimal("20.00")),
        make_fact(publisher=None, paid_out_total=Decimal("10.00")),
    )

    grouping = group_by(facts, dimensions.by_id("publisher"), measure=Measure.PUBLICATIONS)

    assert [(r.label, r.publications, r.is_unknown) for r in grouping.rows] == [
        ("Elsevier", 1, False),
        ("Unknown", 1, True),
    ]


def test__group_by_empty_input__yields_no_rows_and_a_zero_total() -> None:
    grouping = group_by((), dimensions.by_id("publisher"), measure=Measure.PUBLICATIONS)

    assert grouping.rows == ()
    assert grouping.total() == 0


def test__group_by_cost_type__splits_spend_across_the_positions_cost_types() -> None:
    facts = (
        make_fact(
            paid_out_by_cost_type={"apc": Decimal("100.00"), "vat": Decimal("19.00")},
            paid_out_total=Decimal("119.00"),
        ),
        make_fact(paid_out_by_cost_type={"apc": Decimal("50.00")}, paid_out_total=Decimal("50.00")),
    )

    spend = group_by(facts, dimensions.by_id("cost_type"), measure=Measure.PAID_OUT)

    assert [(r.label, r.amount) for r in spend.rows] == [
        ("apc", Decimal("150.00")),
        ("vat", Decimal("19.00")),
    ]
    assert spend.additive
    assert spend.total() == Decimal("169.00")


def test__group_by_cost_type__rejects_the_publication_measure_as_double_counting() -> None:
    facts = (make_fact(paid_out_by_cost_type={"apc": Decimal("100.00")}),)

    with pytest.raises(ValueError, match="cost_type"):
        group_by(facts, dimensions.by_id("cost_type"), measure=Measure.PUBLICATIONS)


def test__group_by_funder__counts_publications_in_full_but_offers_no_spend_measure() -> None:
    facts = (
        make_fact(funders=("DFG", "Wellcome Trust")),
        make_fact(funders=("DFG",)),
    )

    publications = group_by(facts, dimensions.by_id("funder"), measure=Measure.PUBLICATIONS)

    assert [(r.label, r.publications) for r in publications.rows] == [
        ("DFG", 2),
        ("Wellcome Trust", 1),
    ]
    assert not publications.additive
    assert publications.total() is None
    with pytest.raises(ValueError, match="funder"):
        group_by(facts, dimensions.by_id("funder"), measure=Measure.PAID_OUT)


def test__group_by_funding_source__shows_the_unassigned_remainder_as_its_own_row() -> None:
    facts = (
        make_fact(
            funded_by={
                source("Budget A"): Decimal("60.00"),
                source("Budget B"): Decimal("20.00"),
            },
            unassigned=Decimal("20.00"),
            paid_out_total=Decimal("100.00"),
        ),
        make_fact(
            funded_by={source("Budget A"): Decimal("50.00")},
            paid_out_total=Decimal("50.00"),
        ),
    )

    spend = group_by(facts, dimensions.by_id("funding_source"), measure=Measure.FUNDED_BY)

    assert [(r.label, r.amount) for r in spend.rows] == [
        ("Budget A", Decimal("110.00")),
        ("Budget B", Decimal("20.00")),
        ("Unassigned", Decimal("20.00")),
    ]
    assert spend.additive
    assert spend.total() == Decimal("150.00")


def test__group_by_funding_source__counts_publications_non_additively() -> None:
    facts = (
        make_fact(
            funded_by={
                source("Budget A"): Decimal("60.00"),
                source("Budget B"): Decimal("20.00"),
            },
            unassigned=Decimal("20.00"),
            paid_out_total=Decimal("100.00"),
        ),
        make_fact(
            funded_by={source("Budget A"): Decimal("50.00")},
            paid_out_total=Decimal("50.00"),
        ),
    )

    publications = group_by(facts, dimensions.by_id("funding_source"), measure=Measure.PUBLICATIONS)

    assert [(r.label, r.publications) for r in publications.rows] == [
        ("Budget A", 2),
        ("Budget B", 1),
        ("Unassigned", 1),
    ]
    assert not publications.additive
    assert publications.total() is None


def test__group_by__folds_rows_beyond_the_top_n_into_an_other_row() -> None:
    facts = tuple(make_fact(publisher=f"p{i:02d}") for i in range(1, 14))

    grouping = group_by(facts, dimensions.by_id("publisher"), measure=Measure.PUBLICATIONS, top_n=3)

    assert [(r.label, r.publications, r.is_other) for r in grouping.rows] == [
        ("p01", 1, False),
        ("p02", 1, False),
        ("p03", 1, False),
        ("Other", 10, True),
    ]
    assert grouping.total() == 13


def test__group_by__sums_amounts_in_the_other_row() -> None:
    facts = tuple(
        make_fact(publisher=publisher, paid_out_total=Decimal(f"{(i + 1)}.00"))
        for i, publisher in enumerate(["a", "b", "c", "d", "e"])
    )

    grouping = group_by(facts, dimensions.by_id("publisher"), measure=Measure.PAID_OUT, top_n=2)

    assert [(r.label, r.amount, r.is_other) for r in grouping.rows] == [
        ("e", Decimal("5.00"), False),
        ("d", Decimal("4.00"), False),
        ("Other", Decimal("6.00"), True),
    ]
    assert grouping.total() == Decimal("15.00")


def test__group_by_non_additive__other_row_counts_each_request_once() -> None:
    facts = (
        make_fact(institutions=(institution("A"), institution("B"))),
        make_fact(institutions=(institution("B"), institution("C"))),
        make_fact(institutions=(institution("C"),)),
    )

    grouping = group_by(
        facts, dimensions.by_id("institution"), measure=Measure.PUBLICATIONS, top_n=1
    )

    assert [(r.label, r.publications, r.is_other) for r in grouping.rows] == [
        ("B", 2, False),
        ("Other", 3, True),
    ]
    assert not grouping.additive
    assert grouping.total() is None
