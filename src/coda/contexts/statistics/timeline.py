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

    With ``comparison`` (the prior period's weekly counts), the figure
    becomes two stacked panels sharing the week axis: the previous period's
    weeks on top (muted — the charts module's washed-out convention), the
    current period's below (full hue). Each panel owns its own stretch of
    weeks, so the axis never stretches to cover a year of empty columns.
    """
    if not points:
        return {"data": [], "layout": {"height": 160}, "config": {"responsive": True}}

    def _trace(
        period_points: Sequence[TimelinePoint],
        *,
        color: str,
        name: str,
        yaxis: str,
        hover_suffix: str,
    ) -> dict[str, object]:
        return {
            "type": "bar",
            "x": [point.week_start.isoformat() for point in period_points],
            "y": [point.count for point in period_points],
            "name": name,
            "marker": {"color": color},
            "yaxis": yaxis,
            "hovertemplate": f"week of %{{x}}: %{{y}} request(s)<extra>{hover_suffix}</extra>",
            "showlegend": False,
        }

    max_count = max(point.count for point in points)
    if comparison:
        comparison_max = max((p.count for p in comparison), default=0)
        max_count = max(max_count, comparison_max)
        # Two independent stacked panels: previous on top (its own x/y2),
        # current below (its own x/y) — no axis sharing, each panel's week
        # labels render under it. Panel annotations name the periods.
        data = [
            _trace(
                comparison,
                color="#0072B266",
                name="previous period",
                yaxis="y2",
                hover_suffix="previous period",
            ),
            _trace(points, color="#0072B2", name="current period", yaxis="y", hover_suffix=""),
        ]
        layout = {
            "height": 340,
            "margin": {"l": 40, "r": 10, "t": 30, "b": 30},
            "xaxis": {
                "type": "category",
                "tickangle": -45,
                "automargin": True,
                "tickformat": "%d.%m.",
                "nticks": min(len(points), 26),
                "anchor": "y",
                "domain": [0.0, 1.0],
            },
            "xaxis2": {
                "type": "category",
                "tickangle": -45,
                "automargin": True,
                "tickformat": "%d.%m.",
                "nticks": min(len(comparison), 26),
                "anchor": "y2",
            },
            "yaxis": {
                "title": {"text": "requests / week"},
                "domain": [0.0, 0.42],
                "rangemode": "nonnegative",
                "range": [0, max_count * 1.15] if max_count else [0, 1],
            },
            "yaxis2": {
                "domain": [0.58, 1.0],
                "rangemode": "nonnegative",
                "range": [0, max_count * 1.15] if max_count else [0, 1],
            },
            "bargap": 0.15,
            "showlegend": False,
            "annotations": [
                {
                    "text": "previous period",
                    "x": 0.0,
                    "xref": "paper",
                    "y": 1.0,
                    "yref": "paper",
                    "yanchor": "bottom",
                    "xanchor": "left",
                    "showarrow": False,
                    "font": {"size": 12},
                },
                {
                    "text": "current period",
                    "x": 0.0,
                    "xref": "paper",
                    "y": 0.42,
                    "yref": "paper",
                    "yanchor": "bottom",
                    "xanchor": "left",
                    "showarrow": False,
                    "font": {"size": 12},
                },
            ],
        }
    else:
        data = [_trace(points, color="#0072B2", name="current period", yaxis="y", hover_suffix="")]
        layout = {
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
    return {"data": data, "layout": layout, "config": {"responsive": True}}
