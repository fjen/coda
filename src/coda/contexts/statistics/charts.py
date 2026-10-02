"""Groupings -> plotly figure JSON (plan §9).

Pure: takes Grouping values, returns the exact {data, layout, config} object
``Plotly.newPlot`` consumes, with one figure per dimension. Each figure shows
every measure of the dimension as its own colour-coded panel over the shared
entity axis, so counts and money stay directly comparable without sharing a
scale — and a server-side PDF renderer can reuse the same figures (plan §13).
Exact values are NOT here — the template renders the section table.
"""

from collections.abc import Sequence
from typing import Any

import plotly.graph_objects as go

from coda.contexts.statistics.aggregation import DEFAULT_TOP_N, group_by
from coda.contexts.statistics.dimensions import ZERO, Dimension
from coda.contexts.statistics.dto import (
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


def build_figure(grouping: Grouping) -> dict[str, Any]:
    """Horizontal bars: one panel per measure, each on its own x-domain, all
    panels sharing the entity axis in the table's row order (fold row last).
    The per-panel axis title is the measure label."""
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


def report(
    facts: Sequence[RequestFact],
    dimensions: Sequence[Dimension],
    *,
    top_n: int = DEFAULT_TOP_N,
) -> StatisticsReport:
    """Headline plus one figure per dimension; dimensions without data omit
    their section entirely."""
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
                figure=build_figure(grouping),
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
