"""Grouping[] -> plotly figure JSON (plan §9).

Server-built figures rendered by a dumb client: each figure is exactly the object
``Plotly.newPlot`` consumes and exactly the object a server-side PDF renderer can
reuse later (plan §13). Bars, horizontal, no pie; exact values are NOT here — the
template renders its value tables from ``ChartSpec.rows``.
"""

from typing import Any, Sequence

import plotly.graph_objects as go

from coda.contexts.statistics.aggregation import DEFAULT_TOP_N, group_by
from coda.contexts.statistics.dimensions import ZERO, Dimension
from coda.contexts.statistics.dto import (
    ChartSpec,
    Grouping,
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


def build_figure(grouping: Grouping) -> dict[str, Any]:
    """One horizontal bar figure: dimension rows, measure values, largest on top."""
    labels = [row.label for row in grouping.rows]
    figure = go.Figure(go.Bar(x=_row_values(grouping), y=labels, orientation="h"))
    figure.update_layout(
        title_text=_title(grouping.dimension_label, grouping.measure),
        yaxis={"autorange": "reversed"},
        margin={"l": 10, "r": 10, "t": 40, "b": 10},
    )
    return figure.to_plotly_json()


def report(
    facts: Sequence[RequestFact],
    dimensions: Sequence[Dimension],
    *,
    top_n: int = DEFAULT_TOP_N,
) -> StatisticsReport:
    """Headline plus one chart per supported dimension + measure; empty groups omit."""
    charts: list[ChartSpec] = []
    for dimension in dimensions:
        for measure in dimension.measures():
            grouping = group_by(facts, dimension, measure=measure, top_n=top_n)
            if not grouping.rows:
                continue
            charts.append(
                ChartSpec(
                    dimension_id=dimension.id,
                    measure=measure,
                    title=_title(dimension.label, measure),
                    additive=grouping.additive,
                    note=None if grouping.additive else NON_ADDITIVE_NOTE,
                    total=grouping.total(),
                    rows=grouping.rows,
                    figure=build_figure(grouping),
                )
            )
    return StatisticsReport(headline=_headline(facts), charts=tuple(charts))


def _title(dimension_label: str, measure: Measure) -> str:
    return f"{dimension_label} — {MEASURE_LABELS[measure]}"


def _row_values(grouping: Grouping) -> list[int | float]:
    if grouping.measure is Measure.PUBLICATIONS:
        return [row.publications for row in grouping.rows]
    return [float(row.amount or ZERO) for row in grouping.rows]


def _headline(facts: Sequence[RequestFact]) -> Headline:
    return Headline(
        publications=len(facts),
        spend=sum((fact.paid_out_total for fact in facts), ZERO),
        requests_without_invoice=sum(1 for fact in facts if not fact.has_invoice),
        requests_unconvertible=sum(1 for fact in facts if fact.invoices_without_rate > 0),
    )
