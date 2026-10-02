"""Grouping facts by dimension (plan §4, §7; ADR-0007).

Pure: takes RequestFact values, returns Grouping values. Repeated dimensions count a
fact in full under every one of its values; the additive flag on the result tells the
page it must not print a total for such rows.
"""

from collections.abc import Sequence
from decimal import Decimal

from coda.contexts.statistics.dimensions import OTHER, UNASSIGNED, UNKNOWN, ZERO, Dimension
from coda.contexts.statistics.dto import Grouping, GroupRow, Measure, RequestFact

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
    sources: dict[str, set[int]] = {}
    for fact in facts:
        contributions = dimension.contributions(fact)
        for label in dict.fromkeys(contribution.label for contribution in contributions):
            counts[label] = counts.get(label, 0) + 1
            sources.setdefault(label, set()).add(fact.request_id)
        if measure is not Measure.PUBLICATIONS:
            for contribution in contributions:
                amounts[contribution.label] = (
                    amounts.get(contribution.label, ZERO) + contribution.amount
                )

    def value(label: str) -> Decimal:
        if measure is Measure.PUBLICATIONS:
            return Decimal(counts[label])
        return amounts[label]

    def row(label: str) -> GroupRow:
        return GroupRow(
            label=label,
            publications=counts[label],
            amount=None if measure is Measure.PUBLICATIONS else amounts[label],
            is_unknown=label == UNKNOWN,
            is_unassigned=label == UNASSIGNED,
        )

    ordered = sorted(counts, key=lambda label: (-value(label), label))
    rows = [row(label) for label in ordered[:top_n]]
    folded = ordered[top_n:]
    if folded:
        rows.append(
            GroupRow(
                label=OTHER,
                publications=len({rid for label in folded for rid in sources[label]}),
                amount=(
                    None
                    if measure is Measure.PUBLICATIONS
                    else sum((amounts[label] for label in folded), ZERO)
                ),
                is_other=True,
            )
        )
    return Grouping(
        dimension_id=dimension.id,
        dimension_label=dimension.label,
        measure=measure,
        additive=dimension.is_additive(measure),
        rows=tuple(rows),
    )
