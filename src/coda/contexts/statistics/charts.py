"""Groupings -> plotly figure JSON (plan §9).

Pure: takes Grouping values, returns the exact {data, layout, config} object
``Plotly.newPlot`` consumes, with one figure per dimension. Each figure shows
every measure of the dimension as its own colour-coded panel over the shared
entity axis, so counts and money stay directly comparable without sharing a
scale — and a server-side PDF renderer can reuse the same figures (plan §13).
Exact values are NOT here — the template renders the section table.
"""

import math
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
    "request are double-counted — sum the rows for a grand total."
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
    """Vertical columns: one full-width panel per measure, stacked, the entity
    names under the columns on the shared X axis (rendered once, under the
    bottom panel). The figure width never depends on label length, so sections
    don't jump horizontally when filters change. Long names rotate 45°, the
    exact value sits at each column tip, and the value scale keeps headroom
    for those labels."""
    measures = grouping.measures
    domains = [[0.0, 1.0]] if len(measures) == 1 else [[0.0, 0.45], [0.55, 1.0]]
    figure = go.Figure()
    axes: dict[str, Any] = {}
    annotations: list[dict[str, Any]] = []
    for index, measure in enumerate(measures):
        values = [_row_value(row, measure) for row in grouping.rows]
        figure.add_trace(
            go.Bar(
                x=[row.label for row in grouping.rows],
                y=values,
                name=MEASURE_LABELS[measure],
                marker_color=MEASURE_COLORS[measure],
                yaxis="y" if index == 0 else f"y{index + 1}",
                text=[_bar_label(measure, value) for value in values],
                textposition="outside",
                cliponaxis=False,
                hovertemplate="%{x}: %{y:,.2f}<extra></extra>",
            )
        )
        axis_name = "yaxis" if index == 0 else f"yaxis{index + 1}"
        axes[axis_name] = {
            "domain": domains[index],
            "tickformat": _tick_format(measure),
            # All-zero data must not autorange below zero.
            "range": [
                0,
                _label_headroom(measure, max(values)) if max(values, default=0) > 0 else 1,
            ],
        }
        # Axis titles of stacked panels would overlap at the shared left edge;
        # a paper annotation above each panel names it in reading direction.
        annotations.append(
            {
                "x": 0,
                "xref": "paper",
                "xanchor": "left",
                "y": domains[index][1] - 0.012,
                "yref": "paper",
                "yanchor": "bottom",
                "text": MEASURE_LABELS[measure],
                "showarrow": False,
                "font": {"size": 12},
            }
        )
    # Cap the rendered bar thickness: with few categories plotly stretches
    # each bar over its whole slot (a one-row figure draws a 1100px bar).
    # bargap is the empty fraction of a slot, so a slot of slot_px px yields
    # bars of (1 - bargap) * slot_px px.
    MAX_BAR_PX = 90
    rows = len(grouping.rows)
    panel_px = 1100  # typical plot width; bargap only needs to be close
    bargap = max(0.3, 1.0 - MAX_BAR_PX / (panel_px / max(rows, 1)))
    # The plot area — not the figure — is the fixed quantity: the rotated
    # label band gets its own margin sized from the longest label, so
    # tick-label length changes figure height but never squeezes the chart.
    # Single-measure figures render one panel, so they get half the plot.
    PLOT_HEIGHT = 330  # px of combined bar panels (two-measure figures)
    TOP_MARGIN = 22  # px, holds the topmost panel's label
    plot = PLOT_HEIGHT if len(measures) > 1 else PLOT_HEIGHT // 2
    label_band = _label_band_px([row.label for row in grouping.rows])
    figure.update_layout(
        **axes,
        xaxis={
            "automargin": False,
            "tickangle": -45,
            "type": "category",
            "domain": [0.0, 1.0],
        },
        height=plot + label_band + TOP_MARGIN,
        bargap=bargap,
        annotations=annotations,
        showlegend=False,
        margin={"l": 10, "r": 10, "t": TOP_MARGIN, "b": label_band},
    )
    json: dict[str, Any] = figure.to_plotly_json()
    return json


def _label_band_px(labels: Sequence[str]) -> int:
    """Bottom margin for the -45° tick labels, from the longest one.

    At -45° a label of L px rendered width needs about L·sin(45°) ≈ 0.7·L of
    vertical band. 7px per character is close enough for system-ui 12px; the
    14px base covers the axis line and tick marks.
    """
    longest = max((len(label) for label in labels), default=0)
    return 14 + int(longest * 7 * 0.7)


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


def _bar_label(measure: Measure, value: float) -> str:
    """The exact value at the bar tip, compact. Money rounds UP to k€, so a
    label never understates what was spent; the exact figure is in the table
    below the chart."""
    if not value:
        return ""  # no label on zero-height bars: nothing to annotate
    if measure is Measure.PUBLICATIONS:
        return f"{value:,}"
    thousands = float(value) / 1000
    rounded = math.ceil(round(thousands, 6))
    return f"{rounded:,.0f} k€"


def _label_headroom(measure: Measure, max_value: float) -> float:
    """X-range so the outside label at the longest bar still fits."""
    headroom = 1.18 if measure is Measure.PUBLICATIONS else 1.30
    return max_value * headroom


def _tick_format(measure: Measure) -> str:
    """SI ticks (50k, 150k) for money; plain numbers for counts."""
    return "~s" if measure is not Measure.PUBLICATIONS else ","


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
