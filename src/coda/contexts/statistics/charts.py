"""Grouping[] -> plotly figure JSON (plan §9).

Server-built figures rendered by a dumb client: each figure is exactly the object
``Plotly.newPlot`` consumes and exactly the object a server-side PDF renderer can
reuse later (plan §13). Bars, horizontal, no pie; exact values are NOT here — the
template renders its value tables from ``ChartSpec.rows``.
"""

from collections.abc import Sequence
from typing import Any

import plotly.graph_objects as go

from coda.contexts.statistics.aggregation import DEFAULT_TOP_N, group_by
from coda.contexts.statistics.dimensions import ZERO, Dimension
from coda.contexts.statistics.dto import (
    ChartSpec,
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

NON_ADDITIVE_NOTE = (
    "Non-additive: a request with several values is counted in full under every one "
    "of them, so these rows add up to more than the total (ADR-0007)."
)


def build_figure(grouping: Grouping, measure: Measure) -> dict[str, Any]:
    """One horizontal bar figure per measure: the grouping's rows, bars largest
    first for that measure, the fold row last. Every figure of a dimension uses
    the same row set as the section table."""
    bars = sorted(
        (row for row in grouping.rows if not row.is_other),
        key=lambda row: (-_row_value(row, measure), row.label),
    )
    bars += [row for row in grouping.rows if row.is_other]
    figure = go.Figure(
        go.Bar(
            x=[_row_value(row, measure) for row in bars],
            y=[row.label for row in bars],
            orientation="h",
        )
    )
    figure.update_layout(
        title_text=_title(grouping.dimension_label, measure),
        yaxis={"autorange": "reversed"},
        margin={"l": 10, "r": 10, "t": 40, "b": 10},
    )
    json: dict[str, Any] = figure.to_plotly_json()
    return json


def report(
    facts: Sequence[RequestFact],
    dimensions: Sequence[Dimension],
    *,
    top_n: int = DEFAULT_TOP_N,
) -> StatisticsReport:
    """Headline plus one grouping per dimension; one chart per supported
    measure, all sharing the grouping's rows; empty dimensions omit."""
    charts: list[ChartSpec] = []
    for dimension in dimensions:
        grouping = group_by(facts, dimension, top_n=top_n)
        if not grouping.rows:
            continue
        for measure in dimension.measures():
            additive = measure not in grouping.non_additive
            charts.append(
                ChartSpec(
                    dimension_id=dimension.id,
                    measure=measure,
                    title=_title(dimension.label, measure),
                    additive=additive,
                    note=None if additive else NON_ADDITIVE_NOTE,
                    total=grouping.total(measure),
                    rows=grouping.rows,
                    figure=build_figure(grouping, measure),
                )
            )
    return StatisticsReport(headline=_headline(facts), charts=tuple(charts))


def _title(dimension_label: str, measure: Measure) -> str:
    return f"{dimension_label} — {MEASURE_LABELS[measure]}"


def _row_value(row: GroupRow, measure: Measure) -> int | float:
    if measure is Measure.PUBLICATIONS:
        return row.publications
    return float(row.amount or ZERO)


def _headline(facts: Sequence[RequestFact]) -> Headline:
    return Headline(
        publications=len(facts),
        spend=sum((fact.paid_out_total for fact in facts), ZERO),
        requests_without_invoice=sum(1 for fact in facts if not fact.has_invoice),
        requests_unconvertible=sum(1 for fact in facts if fact.invoices_without_rate > 0),
    )
