import datetime

from tests.contexts.statistics.factories import make_fact

from coda.contexts.statistics.timeline import TimelinePoint, timeline_figure, weekly_counts


def test__timeline__single_series_keeps_the_bare_figure() -> None:
    points = weekly_counts([make_fact(), make_fact()])

    figure = timeline_figure(points)

    assert len(figure["data"]) == 1
    trace = figure["data"][0]
    assert trace["name"] == "current period"
    assert trace["showlegend"] is False
    assert figure["layout"]["showlegend"] is False


def test__timeline__comparison_adds_muted_previous_series() -> None:
    current = weekly_counts([make_fact()])  # one week, one request
    previous = [TimelinePoint(week_start=datetime.date(2026, 1, 5), count=3)]

    figure = timeline_figure(current, previous)

    previous_trace, current_trace = figure["data"]
    assert previous_trace["name"] == "previous period"
    assert previous_trace["marker"]["color"] == "#0072B266"  # muted current hue
    assert previous_trace["showlegend"] is True
    assert current_trace["showlegend"] is True
    # Shared x axis (the current period's weeks); the previous week not in
    # the current range contributes 0 — a gap, not a missing column.
    assert previous_trace["x"] == current_trace["x"]
    assert previous_trace["y"] == [0]
    # Grouped bars, legend above the plot area.
    assert figure["layout"]["barmode"] == "group"
    assert figure["layout"]["showlegend"] is True
    assert figure["layout"]["margin"]["t"] == 52
    # The y scale spans both series.
    assert figure["layout"]["yaxis"]["range"] == [0, 3 * 1.15]


def test__timeline__comparison_counts_match_by_week() -> None:
    # Current span: the two weeks of 2026-04-27 and 2026-05-04.
    facts = [make_fact(), make_fact(request_date=datetime.date(2026, 5, 4))]
    # Comparison facts land on those same Mondays: two in the first week,
    # one in the second — the muted series mirrors them onto the shared axis.
    previous_facts = [
        make_fact(request_date=datetime.date(2026, 4, 27)),
        make_fact(request_date=datetime.date(2026, 4, 29)),
        make_fact(request_date=datetime.date(2026, 5, 4)),
    ]

    figure = timeline_figure(weekly_counts(facts), weekly_counts(previous_facts))

    # Figure order: previous series first, then current (matches the bars'
    # grouped pairs — "previous" reads first, earlier in time).
    previous_trace, current_trace = figure["data"][0], figure["data"][1]
    assert current_trace["y"] == [1, 1]
    assert previous_trace["y"] == [2, 1]
