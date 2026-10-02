from decimal import Decimal

from tests.contexts.statistics.factories import institution, make_fact

from coda.contexts.statistics import dimensions
from coda.contexts.statistics.aggregation import group_by
from coda.contexts.statistics.charts import NON_ADDITIVE_NOTE, build_figure, report
from coda.contexts.statistics.dto import Measure, StatisticsReport

PUBLISHER_FACTS = (
    make_fact(publisher="Elsevier", paid_out_total=Decimal("100.00")),
    make_fact(publisher="Elsevier", paid_out_total=Decimal("50.00")),
    make_fact(publisher="Springer", paid_out_total=Decimal("20.00")),
)


def _charts_by_key(the_report: StatisticsReport) -> dict[tuple[str, Measure], object]:
    return {(c.dimension_id, c.measure): c for c in the_report.charts}


def test__report__builds_a_horizontal_bar_figure_of_the_grouping() -> None:
    grouping = group_by(PUBLISHER_FACTS, dimensions.by_id("publisher"))

    figure = build_figure(grouping, Measure.PAID_OUT)

    assert [trace["type"] for trace in figure["data"]] == ["bar"]
    trace = figure["data"][0]
    assert trace["orientation"] == "h"
    assert list(trace["y"]) == ["Elsevier", "Springer"]
    assert [float(v) for v in trace["x"]] == [150.0, 20.0]


def test__report__figures_of_a_dimension_share_rows_and_sort_by_their_measure() -> None:
    grouping = group_by(PUBLISHER_FACTS, dimensions.by_id("publisher"))

    spend = build_figure(grouping, Measure.PAID_OUT)["data"][0]
    publications = build_figure(grouping, Measure.PUBLICATIONS)["data"][0]

    assert set(spend["y"]) == set(publications["y"]) == {"Elsevier", "Springer"}
    assert list(spend["y"]) == ["Elsevier", "Springer"]
    assert [float(v) for v in spend["x"]] == [150.0, 20.0]
    assert list(publications["y"]) == ["Elsevier", "Springer"]
    assert [float(v) for v in publications["x"]] == [2.0, 1.0]


def test__report__titles_state_measure_and_dimension() -> None:
    the_report = report(PUBLISHER_FACTS, (dimensions.by_id("publisher"),))

    spend = _charts_by_key(the_report)[("publisher", Measure.PAID_OUT)]
    publications = _charts_by_key(the_report)[("publisher", Measure.PUBLICATIONS)]

    assert spend.title == "Publisher — spend incl. tax"  # type: ignore[attr-defined]
    assert publications.title == "Publisher — publications"  # type: ignore[attr-defined]


def test__report__omits_measures_the_dimension_does_not_support() -> None:
    facts = (
        make_fact(
            publisher="Elsevier",
            paid_out_by_cost_type={"apc": Decimal("100.00")},
            paid_out_total=Decimal("100.00"),
            funders=("DFG",),
        ),
    )

    the_report = report(facts, dimensions.DIMENSIONS)

    keys = {(c.dimension_id, c.measure) for c in the_report.charts}
    assert ("cost_type", Measure.PUBLICATIONS) not in keys
    assert ("cost_type", Measure.PAID_OUT) in keys
    assert ("funder", Measure.PUBLICATIONS) in keys
    assert ("funder", Measure.PAID_OUT) not in keys
    assert all(
        trace["type"] == "bar" for chart in the_report.charts for trace in chart.figure["data"]
    )


def test__report__labels_non_additive_charts_and_hides_their_total() -> None:
    facts = (
        make_fact(
            institutions=(institution("TU Berlin"), institution("Humboldt")),
            paid_out_total=Decimal("100.00"),
        ),
    )

    the_report = report(facts, (dimensions.by_id("institution"),))
    for chart in the_report.charts:
        assert not chart.additive
        assert chart.note == NON_ADDITIVE_NOTE
        assert chart.total is None

    publisher_report = report(PUBLISHER_FACTS, (dimensions.by_id("publisher"),))
    for chart in publisher_report.charts:
        assert chart.additive
        assert chart.note is None
        assert chart.total is not None


def test__report__headline_counts_publications_spend_and_gaps() -> None:
    facts = (
        make_fact(paid_out_total=Decimal("100.00"), has_invoice=True),
        make_fact(paid_out_total=Decimal("50.00"), has_invoice=False),
        make_fact(paid_out_total=Decimal(0), has_invoice=True, invoices_without_rate=2),
    )

    headline = report(facts, dimensions.DIMENSIONS).headline

    assert headline.publications == 3
    assert headline.spend == Decimal("150.00")
    assert headline.requests_without_invoice == 1
    assert headline.requests_unconvertible == 1


def test__report__on_empty_facts_yields_no_charts_and_a_zero_headline() -> None:
    the_report = report((), dimensions.DIMENSIONS)

    assert the_report.charts == ()
    assert the_report.headline.publications == 0
    assert the_report.headline.spend == Decimal(0)
