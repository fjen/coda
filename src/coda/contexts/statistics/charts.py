"""Groupings -> plotly figure JSON (plan §9).

Pure: takes Grouping values, returns the exact {data, layout, config} object
``Plotly.newPlot`` consumes, with one figure per dimension. Each figure shows
every measure of the dimension as its own colour-coded panel over the shared
entity axis, so counts and money stay directly comparable without sharing a
scale — and a server-side PDF renderer can reuse the same figures (plan §13).
Exact values are NOT here — the template renders the section table.
"""

from collections.abc import Callable, Sequence
from typing import Any

import plotly.graph_objects as go

from coda.contexts.statistics.aggregation import DEFAULT_TOP_N, group_by
from coda.contexts.statistics.dimensions import ZERO, Dimension
from coda.contexts.statistics.dto import (
    ChartKind,
    ChartSpec,
    ColumnSpec,
    Grouping,
    GroupRow,
    Headline,
    Measure,
    RequestFact,
    StatisticsReport,
)

MEASURE_LABELS: dict[Measure, str] = {
    Measure.PUBLICATIONS: "publications",
    Measure.PAID_OUT: "spend incl. tax",
    Measure.FUNDED_BY: "funded by incl. tax",
}

#: Okabe–Ito hues — colour-blind safe, one per measure.
MEASURE_COLORS: dict[Measure, str] = {
    Measure.PUBLICATIONS: "#0072B2",
    Measure.PAID_OUT: "#E69F00",
    Measure.FUNDED_BY: "#D55E00",
}

NON_ADDITIVE_NOTE = (
    "Totals for this column count each request once, so entities sharing a "
    "request are double-counted — sum the rows for a grand total (ADR-0007)."
)


def build_figure(grouping: Grouping, kind: ChartKind = ChartKind.SCATTER) -> dict[str, Any]:
    """Dispatch to the encoding the page asked for (evaluation demo: the same
    groupings, three encodings — scatter, bars, pies)."""
    builders: dict[ChartKind, Callable[[Grouping], dict[str, Any]]] = {
        ChartKind.SCATTER: _scatter_figure,
        ChartKind.BARS: _bars_figure,
        ChartKind.PIES: _pies_figure,
    }
    return builders[kind](grouping)


def _scatter_figure(grouping: Grouping) -> dict[str, Any]:
    """Scatter: one dot per entity, publications on x, spend on y — both
    dimensions in one plot, the entity named beside its dot. The measures
    keep separate axes with their own scales; nothing here implies the values
    sum to a whole, so ADR-0007 groupings stay honest."""
    measures = grouping.measures
    spend = next((m for m in measures if m is not Measure.PUBLICATIONS), None)
    labels = [row.label for row in grouping.rows]
    if spend is None:
        # Single-measure dimension: dot per entity on one value axis.
        measure = measures[0]
        return {
            "data": [
                {
                    "type": "scatter",
                    "mode": "markers+text",
                    "x": [_row_value(row, measure) for row in grouping.rows],
                    "y": list(range(len(grouping.rows))),
                    "text": labels,
                    "textposition": "middle right",
                    "marker": {"color": MEASURE_COLORS[measure], "size": 11},
                    "hovertemplate": "%{text}: %{x:,}<extra></extra>",
                }
            ],
            "layout": {
                "xaxis": {"title": {"text": MEASURE_LABELS[measure]}},
                "yaxis": {"visible": False, "autorange": "reversed"},
                "showlegend": False,
                "margin": {"l": 10, "r": 120, "t": 10, "b": 40},
            },
            "config": {"responsive": True},
        }
    publications = Measure.PUBLICATIONS
    return {
        "data": [
            {
                "type": "scatter",
                "mode": "markers+text",
                "x": [_row_value(row, publications) for row in grouping.rows],
                "y": [float(_row_value(row, spend)) for row in grouping.rows],
                "text": labels,
                "textposition": "middle right",
                "marker": {"color": MEASURE_COLORS[spend], "size": 11},
                "customdata": labels,
                "hovertemplate": ("%{customdata}: %{x:,} publications, %{y:,.2f} €<extra></extra>"),
            }
        ],
        "layout": {
            "xaxis": {"title": {"text": MEASURE_LABELS[publications]}},
            "yaxis": {"title": {"text": MEASURE_LABELS[spend]}, "automargin": True},
            "showlegend": False,
            "margin": {"l": 10, "r": 10, "t": 10, "b": 40},
        },
        "config": {"responsive": True},
    }


def _bars_figure(grouping: Grouping) -> dict[str, Any]:
    """Horizontal bars: one panel per measure, each on its own x-domain, the
    entity labels on the LEFT (one y axis, automargin-sized once). No sign
    tricks — a label column can't collide, a bar length stays exact."""
    measures = grouping.measures
    domains = [[0.0, 1.0]] if len(measures) == 1 else [[0.0, 0.42], [0.58, 1.0]]
    figure = go.Figure()
    axes: dict[str, Any] = {}
    for index, measure in enumerate(measures):
        figure.add_trace(
            go.Bar(
                x=[_row_value(row, measure) for row in grouping.rows],
                y=[row.label for row in grouping.rows],
                orientation="h",
                name=MEASURE_LABELS[measure],
                marker_color=MEASURE_COLORS[measure],
                xaxis="x" if index == 0 else f"x{index + 1}",
            )
        )
        axes["xaxis" if index == 0 else f"xaxis{index + 1}"] = {
            "domain": domains[index],
            "title_text": MEASURE_LABELS[measure],
        }
    figure.update_layout(
        **axes,
        yaxis={"autorange": "reversed", "automargin": True},
        showlegend=False,
        margin={"l": 10, "r": 10, "t": 10, "b": 40},
    )
    json: dict[str, Any] = figure.to_plotly_json()
    return json


def _pies_figure(grouping: Grouping) -> dict[str, Any]:
    """Pie pair as subplots: publications left, spend right, the shared
    legend's labels stacked along the LEFT side of the figure. Only honest
    where the grouping is additive — non-additive groupings fall back to
    bars, because pie grammar claims the slices complete the whole
    (ADR-0007)."""
    if grouping.non_additive:
        return _bars_figure(grouping)
    colors = _entity_colors(grouping.rows)
    traces: list[dict[str, Any]] = []
    for index, measure in enumerate(grouping.measures):
        values = [_row_value(row, measure) for row in grouping.rows]
        if not any(values):
            continue
        traces.append(
            {
                "type": "pie",
                "labels": [row.label for row in grouping.rows],
                "values": values,
                "name": MEASURE_LABELS[measure],
                "textinfo": "label+percent",
                "textposition": "inside",
                "hovertemplate": "%{label}: %{value:,} (%{percent})<extra></extra>",
                "domain": {"x": [0.18, 0.5] if index == 0 else [0.62, 0.94]},
                "marker": {"colors": colors, "line": {"color": "#fff", "width": 1}},
                "sort": False,
            }
        )
    if not traces:
        return _bars_figure(grouping)
    # One subtitle per subplot, centred over its pie: which measure is which.
    annotations = [
        {
            "text": MEASURE_LABELS[measure],
            "x": 0.34 if index == 0 else 0.78,
            "y": 1.0,
            "xref": "paper",
            "yref": "paper",
            "xanchor": "center",
            "yanchor": "bottom",
            "showarrow": False,
            "font": {"size": 13},
        }
        for index, measure in enumerate(grouping.measures)
        if any(_row_value(row, measure) for row in grouping.rows)
    ]
    return {
        "data": traces,
        "layout": {
            "showlegend": True,
            "legend": {
                # Labels stacked along the LEFT edge, one per entity.
                "x": 0.0,
                "xanchor": "left",
                "y": 0.5,
                "yanchor": "middle",
                "orientation": "v",
                "font": {"size": 11},
            },
            "annotations": annotations,
            "margin": {"l": 10, "r": 10, "t": 40, "b": 10},
        },
        "config": {"responsive": True},
    }


def _entity_colors(rows: Sequence[GroupRow]) -> list[str]:
    """One stable hue per entity across both pies (Okabe–Ito, cycled)."""
    palette = [
        "#4E79A7",
        "#F28E2B",
        "#59A14F",
        "#E15759",
        "#76B7B2",
        "#EDC948",
        "#B07AA1",
        "#FF9DA7",
        "#9C755F",
        "#BAB0AC",
    ]
    return [palette[index % len(palette)] for index in range(len(rows))]


def report(
    facts: Sequence[RequestFact],
    dimensions: Sequence[Dimension],
    *,
    top_n: int = DEFAULT_TOP_N,
    kind: ChartKind = ChartKind.SCATTER,
) -> StatisticsReport:
    """Headline plus one figure per dimension; dimensions without data omit
    their section entirely. ``kind`` selects the encoding (evaluation demo)."""
    charts: list[ChartSpec] = []
    for dimension in dimensions:
        grouping = group_by(facts, dimension, top_n=top_n)
        if not grouping.rows:
            continue
        charts.append(
            ChartSpec(
                dimension_id=dimension.id,
                title=_title(dimension.label, grouping.measures),
                columns=tuple(
                    ColumnSpec(
                        measure=measure,
                        total=grouping.total(measure),
                        note=(None if measure not in grouping.non_additive else NON_ADDITIVE_NOTE),
                    )
                    for measure in grouping.measures
                ),
                rows=grouping.rows,
                figure=build_figure(grouping, kind),
            )
        )
    return StatisticsReport(headline=_headline(facts), charts=tuple(charts))


def _title(dimension_label: str, measures: tuple[Measure, ...]) -> str:
    return f"{dimension_label} — {' & '.join(MEASURE_LABELS[m] for m in measures)}"


def _row_value(row: GroupRow, measure: Measure) -> int | float:
    if measure is Measure.PUBLICATIONS:
        return row.publications
    return float(row.amount if row.amount is not None else ZERO)


def _headline(facts: Sequence[RequestFact]) -> Headline:
    return Headline(
        publications=len(facts),
        spend=sum((fact.paid_out_total for fact in facts), ZERO),
        requests_without_invoice=sum(1 for fact in facts if not fact.has_invoice),
        requests_unconvertible=sum(1 for fact in facts if fact.invoices_without_rate > 0),
    )
