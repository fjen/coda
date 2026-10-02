"""Grouping facts by dimension (plan §4, §7; ADR-0007).

Pure: takes RequestFact values, returns Grouping values. Repeated dimensions count a
fact in full under every one of its values; the additive flag on the result tells the
page it must not print a total for such rows.
"""

from decimal import Decimal
from typing import Sequence
from coda.contexts.statistics.dimensions import UNKNOWN, ZERO, Dimension
from coda.contexts.statistics.dto import GroupRow, Grouping, Measure, RequestFact

DEFAULT_TOP_N = 15


def group_by(
    facts: Sequence[RequestFact],
    dimension: Dimension,
    *,
    measure: Measure,
    top_n: int = DEFAULT_TOP_N,
) -> Grouping:
    if measure not in dimension.measures():
        raise ValueError(f"dimension {dimension.id!r} has no {measure!r} measure")

    counts: dict[str, int] = {}
    amounts: dict[str, Decimal] = {}
    for fact in facts:
        contributions = dimension.contributions(fact)
        for label in dict.fromkeys(contribution.label for contribution in contributions):
            counts[label] = counts.get(label, 0) + 1
        if measure is not Measure.PUBLICATIONS:
            for contribution in contributions:
                amounts[contribution.label] = (
                    amounts.get(contribution.label, ZERO) + contribution.amount
                )

    def value(label: str) -> Decimal:
        if measure is Measure.PUBLICATIONS:
            return Decimal(counts[label])
        return amounts[label]

    rows = tuple(
        GroupRow(
            label=label,
            publications=counts[label],
            amount=None if measure is Measure.PUBLICATIONS else amounts[label],
            is_unknown=label == UNKNOWN,
        )
        for label in sorted(counts, key=lambda label: (-value(label), label))
    )
    return Grouping(
        dimension_id=dimension.id,
        dimension_label=dimension.label,
        measure=measure,
        additive=dimension.is_additive(measure),
        rows=rows,
    )
