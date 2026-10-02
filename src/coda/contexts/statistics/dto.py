"""Value objects of the statistics context (plan §5, §9).

Pure data: no Django, no ORM, no HTTP — that is what makes the layer unit-testable
and reusable by the PDF renderer later (plan §3).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Mapping


@dataclass(frozen=True, slots=True)
class InstitutionRef:
    """An institution exactly as recorded on a corresponding author (ADR-0006)."""

    name: str


@dataclass(frozen=True, slots=True)
class FundingSourceRef:
    """A cost-splitting funding source, the institution-kind one that pays (ADR-0008)."""

    name: str


@dataclass(frozen=True, slots=True)
class RequestFact:
    """One funding request — the grain of the whole statistics view (plan §5).

    Money fields hold gross amounts already converted to the report currency;
    ``apps/statistics/dataset.py`` fills them (ADR-0001, ADR-0003).
    """

    request_id: int
    publication_id: int
    request_date: date
    title: str
    # single-valued dimensions; None groups as "Unknown"
    subject_area: str | None
    publication_type: str | None
    publication_form: str
    license: str
    open_access_type: str
    journal: str | None
    publisher: str | None
    # repeated dimensions (ADR-0007)
    contracts: tuple[str, ...]
    funders: tuple[str, ...]
    institutions: tuple[InstitutionRef, ...]
    no_corresponding_author: bool
    # position-level money, two notions that are never added (ADR-0008)
    paid_out_by_cost_type: Mapping[str, Decimal]
    paid_out_total: Decimal
    funded_by: Mapping[FundingSourceRef, Decimal]
    unassigned: Decimal
    # provenance (ADR-0003)
    invoices_without_rate: int
    has_invoice: bool


class Measure(StrEnum):
    """What a chart or grouping counts; never mixed inside one series (ADR-0001, ADR-0008)."""

    PUBLICATIONS = "publications"
    PAID_OUT = "paid_out"
    FUNDED_BY = "funded_by"


@dataclass(frozen=True, slots=True)
class GroupRow:
    """One row of a grouping: a dimension value and the measures under it."""

    label: str
    publications: int
    amount: Decimal | None
    is_unknown: bool = False
    is_other: bool = False
    is_unassigned: bool = False


@dataclass(frozen=True, slots=True)
class Grouping:
    """The result of grouping facts by one dimension for one measure."""

    dimension_id: str
    dimension_label: str
    measure: Measure
    additive: bool
    rows: tuple[GroupRow, ...]

    def total(self) -> Decimal | int | None:
        """The grand total, or None for non-additive dimensions.

        Rows of a non-additive grouping deliberately sum to more than the request
        total, so no total may be shown (ADR-0007); the page shows the non-additive
        note instead.
        """
        if not self.additive:
            return None
        if self.measure is Measure.PUBLICATIONS:
            return sum(row.publications for row in self.rows)
        return sum((row.amount or Decimal("0") for row in self.rows), Decimal("0"))
