"""Weekly request counts for the timeline (DASHBOARD.md §timeline).

Pure: takes RequestFact values and returns one point per ISO week between the
earliest and latest request date, zero-filled — a gap in the data is a week
with no requests, not a missing column. Weeks are ISO weeks (Monday-based);
the label is the Monday's date, which the chart renders as the week tick.
"""

import datetime
from collections.abc import Sequence
from dataclasses import dataclass

from coda.contexts.statistics.dto import RequestFact


@dataclass(frozen=True, slots=True)
class TimelinePoint:
    """One week of the timeline: the Monday that starts it and the number of
    funding requests whose request_date falls into that week."""

    week_start: datetime.date
    count: int


def _monday_of(day: datetime.date) -> datetime.date:
    return day - datetime.timedelta(days=day.weekday())


def weekly_counts(facts: Sequence[RequestFact]) -> list[TimelinePoint]:
    """One TimelinePoint per week spanning the facts' request dates.

    Facts always carry a request date (the dataset fills it from the
    request); the None guard keeps the pure layer total.
    """
    dated = [fact.request_date for fact in facts if fact.request_date is not None]
    if not dated:
        return []
    first, last = _monday_of(min(dated)), _monday_of(max(dated))
    counts: dict[datetime.date, int] = {}
    for day in dated:
        counts[_monday_of(day)] = counts.get(_monday_of(day), 0) + 1

    points: list[TimelinePoint] = []
    week = first
    while week <= last:
        points.append(TimelinePoint(week_start=week, count=counts.get(week, 0)))
        week += datetime.timedelta(days=7)
    return points


def timeline_figure(
    points: Sequence[TimelinePoint],
    comparison: Sequence[TimelinePoint] | None = None,
) -> dict[str, object]:
    """The plotly figure JSON for the weekly timeline: one bar per week.

    Follows the charts module's contract — {data, layout, config} exactly as
    ``Plotly.newPlot`` consumes it. The x axis is categorical (the weeks'
    Mondays) so nothing interpolates between weeks; the bar count scales the
    figure height like the other figures do.

    With ``comparison`` (the prior period's weekly counts), one grouped pair
    per week: the previous series renders muted (the charts module's
    _muted convention — same hue washed out) and sits left of the current
    bar; a shared legend above names the two series.
    """
    if not points:
        return {"data": [], "layout": {"height": 160}, "config": {"responsive": True}}
    max_count = max(point.count for point in points)
    if comparison:
        max_count = max(max_count, max((p.count for p in comparison), default=0))
    x = [point.week_start.isoformat() for point in points]
    data: list[dict[str, object]] = []
    if comparison:
        comparison_by_week = {point.week_start: point.count for point in comparison}
        data.append(
            {
                "type": "bar",
                "x": x,
                "y": [comparison_by_week.get(point.week_start, 0) for point in points],
                "name": "previous period",
                "marker": {"color": "#0072B266"},
                "hovertemplate": "week of %{x}: %{y} request(s)<extra>previous period</extra>",
                "showlegend": True,
            }
        )
    data.append(
        {
            "type": "bar",
            "x": x,
            "y": [point.count for point in points],
            "name": "current period",
            "marker": {"color": "#0072B2"},
            "hovertemplate": "week of %{x}: %{y} request(s)<extra></extra>",
            "showlegend": bool(comparison),
        }
    )
    layout: dict[str, object] = {
        "height": 180,
        "margin": {"l": 40, "r": 10, "t": 10, "b": 30},
        "xaxis": {
            "type": "category",
            "tickangle": -45,
            "automargin": True,
            "tickformat": "%d.%m.",
            "nticks": min(len(points), 26),
        },
        "yaxis": {
            "title": {"text": "requests / week"},
            "rangemode": "nonnegative",
            "range": [0, max_count * 1.15] if max_count else [0, 1],
        },
        "bargap": 0.15,
        "showlegend": False,
    }
    if comparison:
        layout |= {
            "barmode": "group",
            "bargap": 0.25,
            "bargroupgap": 0.05,
            "showlegend": True,
            "legend": {
                "orientation": "h",
                "xanchor": "right",
                "x": 1.0,
                "yanchor": "bottom",
                "y": 1.0,
                "font": {"size": 11},
            },
            "margin": {"l": 40, "r": 10, "t": 52, "b": 30},
        }
    return {"data": data, "layout": layout, "config": {"responsive": True}}
