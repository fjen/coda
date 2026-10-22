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
    assert "yaxis2" not in figure["layout"]
    assert figure["layout"]["height"] == 180


def test__timeline__comparison_stacks_two_panels() -> None:
    current = weekly_counts([make_fact()])  # one week, one request
    previous = [TimelinePoint(week_start=datetime.date(2026, 1, 5), count=3)]

    figure = timeline_figure(current, previous)

    # Previous panel on top (y2), current below (y); each keeps its own weeks.
    previous_trace, current_trace = figure["data"]
    assert previous_trace["yaxis"] == "y2"
    assert previous_trace["x"] == ["2026-01-05"]
    assert previous_trace["y"] == [3]
    assert previous_trace["marker"]["color"] == "#0072B266"  # muted current hue
    assert current_trace["yaxis"] == "y"
    assert current_trace["x"] == ["2026-04-27"]
    assert current_trace["y"] == [1]
    # Shared scale, two domains, each panel labels its own weeks.
    assert figure["layout"]["yaxis2"]["range"] == figure["layout"]["yaxis"]["range"]
    assert figure["layout"]["yaxis"]["domain"] == [0.0, 0.42]
    assert figure["layout"]["yaxis2"]["domain"] == [0.58, 1.0]
    # No axis sharing: the top panel carries its own week labels.
    assert "matches" not in figure["layout"]["xaxis2"]
    assert figure["layout"]["xaxis2"].get("showticklabels", True) is not False
    assert figure["layout"]["height"] == 340
    # Panel annotations name the periods (no legend).
    assert [a["text"] for a in figure["layout"]["annotations"]] == [
        "previous period",
        "current period",
    ]


def test__timeline__comparison_scale_spans_both_periods() -> None:
    current = weekly_counts([make_fact()])  # max 1
    previous = [TimelinePoint(week_start=datetime.date(2026, 1, 5), count=5)]

    figure = timeline_figure(current, previous)

    expected = [0, 5 * 1.15]
    assert figure["layout"]["yaxis"]["range"] == expected
    assert figure["layout"]["yaxis2"]["range"] == expected
