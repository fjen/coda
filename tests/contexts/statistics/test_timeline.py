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
    assert figure["layout"]["height"] == 180


def test__timeline__comparison_adds_muted_previous_series() -> None:
    current = weekly_counts([make_fact()])  # one week, one request
    previous = [TimelinePoint(week_start=datetime.date(2026, 1, 5), count=3)]

    figure = timeline_figure(current, previous)

    previous_trace, current_trace = figure["data"]
    assert previous_trace["name"] == "previous period"
    assert previous_trace["marker"]["color"] == "#0072B266"  # muted current hue
    assert previous_trace["showlegend"] is True
    assert current_trace["showlegend"] is True
    # One shared axis over the union of both periods' weeks; the two series
    # occupy disjoint stretches (previous week, current week).
    assert previous_trace["x"] == current_trace["x"] == ["2026-01-05", "2026-04-27"]
    assert previous_trace["y"] == [3, 0]
    assert current_trace["y"] == [0, 1]
    # Legend above the plot area names the two series.
    assert figure["layout"]["showlegend"] is True
    assert figure["layout"]["legend"]["xanchor"] == "right"
    assert figure["layout"]["yaxis"]["range"] == [0, 3 * 1.15]


def test__timeline__comparison_scale_spans_both_periods() -> None:
    current = weekly_counts([make_fact()])  # max 1
    previous = [TimelinePoint(week_start=datetime.date(2026, 1, 5), count=5)]

    figure = timeline_figure(current, previous)

    assert figure["layout"]["yaxis"]["range"] == [0, 5 * 1.15]


def test__timeline__weeks_do_not_interleave() -> None:
    # The axis is chronological across the whole span: the previous period's
    # weeks all precede the current period's (the prior window ends before
    # the current starts), so the muted bars occupy the left stretch.
    facts = [make_fact(), make_fact(request_date=datetime.date(2026, 5, 4))]
    previous_facts = [
        make_fact(request_date=datetime.date(2026, 4, 20)),
        make_fact(request_date=datetime.date(2026, 4, 22)),
        make_fact(request_date=datetime.date(2026, 4, 27)),
    ]

    figure = timeline_figure(weekly_counts(facts), weekly_counts(previous_facts))

    previous_trace, current_trace = figure["data"]
    assert previous_trace["x"] == ["2026-04-20", "2026-04-27", "2026-05-04"]
    assert previous_trace["y"] == [2, 1, 0]
    assert current_trace["y"] == [0, 1, 1]
