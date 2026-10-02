"""The dimension registry (plan §7).

Adding a dimension is one entry here — plus, if it needs one, a query criterion in
``apps/statistics``. Each entry says how a fact contributes to the dimension's values
and which measures it supports; the kind and the additive flags carry the ADR-0007
semantics that keep non-additive charts honest.
"""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from coda.contexts.statistics.dto import Measure, RequestFact

UNKNOWN = "Unknown"
OTHER = "Other"
UNASSIGNED = "Unassigned"

ZERO = Decimal(0)


class DimensionKind(StrEnum):
    """How a request relates to a dimension's values."""

    SINGLE = "single"  # at most one value per request — the values partition the requests
    REPEATED = "repeated"  # a request counts in full under every value (ADR-0007)
    PARTITION = "partition"  # the values partition the request's money, not the request


@dataclass(frozen=True, slots=True)
class Contribution:
    """One fact's contribution to one value of a dimension.

    ``amount`` is gross, expressed in the dimension's money notion; dimensions with no
    spend measure contribute zero amounts.
    """

    label: str
    amount: Decimal


Contributions = Callable[[RequestFact], tuple[Contribution, ...]]


@dataclass(frozen=True, slots=True)
class Dimension:
    id: str
    label: str
    kind: DimensionKind
    has_publications: bool
    additive_publications: bool
    money: Measure | None  # Measure.PAID_OUT | Measure.FUNDED_BY | None
    additive_spend: bool
    contributions: Contributions

    def measures(self) -> tuple[Measure, ...]:
        result = [Measure.PUBLICATIONS] if self.has_publications else []
        if self.money is not None:
            result.append(self.money)
        return tuple(result)

    def is_additive(self, measure: Measure) -> bool:
        if measure is Measure.PUBLICATIONS:
            return self.additive_publications
        return self.additive_spend


def _known(value: str | None) -> str:
    """A missing single-valued attribute groups as "Unknown", never disappears."""
    return value if value is not None else UNKNOWN


def _paid_out_under_each(labels: tuple[str, ...], fact: RequestFact) -> tuple[Contribution, ...]:
    """Repeated dimensions count the whole paid-out amount under every value (ADR-0007)."""
    return tuple(Contribution(label, fact.paid_out_total) for label in labels)


def _single_value_paid_out(
    dimension_id: str, label: str, value: Callable[[RequestFact], str | None]
) -> Dimension:
    """A single-valued publication attribute partitions requests: both measures add up."""
    return Dimension(
        id=dimension_id,
        label=label,
        kind=DimensionKind.SINGLE,
        has_publications=True,
        additive_publications=True,
        money=Measure.PAID_OUT,
        additive_spend=True,
        contributions=lambda fact: (Contribution(_known(value(fact)), fact.paid_out_total),),
    )


SUBJECT_AREA = _single_value_paid_out(
    "subject_area", "Subject area", lambda fact: fact.subject_area
)
PUBLICATION_TYPE = _single_value_paid_out(
    "publication_type", "Publication type", lambda fact: fact.publication_type
)
PUBLICATION_FORM = _single_value_paid_out(
    "publication_form", "Publication form", lambda fact: fact.publication_form
)
LICENSE = _single_value_paid_out("license", "License", lambda fact: fact.license)
OPEN_ACCESS_TYPE = _single_value_paid_out(
    "open_access_type", "Open access type", lambda fact: fact.open_access_type
)
JOURNAL = _single_value_paid_out("journal", "Journal", lambda fact: fact.journal)
PUBLISHER = _single_value_paid_out("publisher", "Publisher", lambda fact: fact.publisher)

INSTITUTION = Dimension(
    id="institution",
    label="Institution (corresponding author)",
    kind=DimensionKind.REPEATED,
    has_publications=True,
    additive_publications=False,
    money=Measure.PAID_OUT,
    additive_spend=False,
    contributions=lambda fact: _paid_out_under_each(
        tuple(ref.name for ref in fact.institutions) or (UNKNOWN,), fact
    ),
)

CONTRACT = Dimension(
    id="contract",
    label="Contract",
    kind=DimensionKind.REPEATED,
    has_publications=True,
    additive_publications=False,
    money=Measure.PAID_OUT,
    additive_spend=False,
    contributions=lambda fact: _paid_out_under_each(fact.contracts, fact),
)

COST_TYPE = Dimension(
    id="cost_type",
    label="Cost type",
    kind=DimensionKind.PARTITION,
    has_publications=False,
    additive_publications=False,
    money=Measure.PAID_OUT,
    additive_spend=True,
    contributions=lambda fact: tuple(
        Contribution(cost_type, amount) for cost_type, amount in fact.paid_out_by_cost_type.items()
    ),
)

FUNDER = Dimension(
    id="funder",
    label="Funder",
    kind=DimensionKind.REPEATED,
    has_publications=True,
    additive_publications=False,
    money=None,
    additive_spend=False,
    contributions=lambda fact: tuple(Contribution(name, ZERO) for name in fact.funders),
)

FUNDING_SOURCE = Dimension(
    id="funding_source",
    label="Funding source (cost splitting)",
    kind=DimensionKind.PARTITION,
    has_publications=True,
    additive_publications=False,
    money=Measure.FUNDED_BY,
    additive_spend=True,
    contributions=lambda fact: (
        tuple(Contribution(ref.name, amount) for ref, amount in fact.funded_by.items())
        + ((Contribution(UNASSIGNED, fact.unassigned),) if fact.unassigned != ZERO else ())
    ),
)

DIMENSIONS: tuple[Dimension, ...] = (
    INSTITUTION,
    SUBJECT_AREA,
    PUBLICATION_TYPE,
    PUBLICATION_FORM,
    LICENSE,
    OPEN_ACCESS_TYPE,
    JOURNAL,
    PUBLISHER,
    COST_TYPE,
    CONTRACT,
    FUNDER,
    FUNDING_SOURCE,
)

_BY_ID: dict[str, Dimension] = {dimension.id: dimension for dimension in DIMENSIONS}


def by_id(dimension_id: str) -> Dimension:
    try:
        return _BY_ID[dimension_id]
    except KeyError:
        raise KeyError(f"unknown statistics dimension: {dimension_id!r}") from None
