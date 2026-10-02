from decimal import Decimal

from coda.contexts.statistics import dimensions
from coda.contexts.statistics.aggregation import group_by
from coda.contexts.statistics.dto import Measure
from tests.contexts.statistics.factories import institution, make_fact


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
