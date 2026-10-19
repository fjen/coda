"""Value objects of the statistics context (plan §5, §9).

Pure data: no Django, no ORM, no HTTP — that is what makes the layer unit-testable
and reusable by the PDF renderer later (plan §3).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any


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
    ``apps/reporting/dataset.py`` fills them (ADR-0001, ADR-0003).
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
    unconvertible_invoice_ids: tuple[int, ...]
    has_invoice: bool


class Measure(StrEnum):
    """What a chart or grouping counts; never mixed inside one series (ADR-0001, ADR-0008)."""

    PUBLICATIONS = "publications"
    PAID_OUT = "paid_out"
    FUNDED_BY = "funded_by"


class ChartKind(StrEnum):
    """Which figure the page renders per dimension (switchable per URL)."""

    BARS = "bars"  # vertical columns, one panel per measure, names on the x axis
    PIES = "pies"  # pie pair, labels left of the plots


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
    """The result of grouping facts by one dimension across its measures: one
    row per dimension value carrying every measure the dimension supports, so
    a facet renders one reconciling table and its charts share its row set."""

    dimension_id: str
    dimension_label: str
    measures: tuple[Measure, ...]
    non_additive: frozenset[Measure]
    rows: tuple[GroupRow, ...]

    def total(self, measure: Measure) -> Decimal | int | None:
        """The grand total for one measure, or None for a non-additive one.

        Rows of a non-additive measure deliberately sum to more than the
        request total, so no total may be shown (ADR-0007); the page shows
        the non-additive note instead.
        """
        if measure in self.non_additive:
            return None
        if measure is Measure.PUBLICATIONS:
            return sum(row.publications for row in self.rows)
        return sum((row.amount or Decimal(0) for row in self.rows), Decimal(0))


@dataclass(frozen=True, slots=True)
class Headline:
    """The headline row of the statistics page (plan §9)."""

    publications: int
    spend: Decimal
    requests_without_invoice: int
    requests_unconvertible: int


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    """One measure column of the dimension's table: its total, or the ADR-0007
    note where the measure is non-additive and no total may be shown."""

    measure: Measure
    total: Decimal | int | None
    note: str | None


@dataclass(frozen=True, slots=True)
class ChartSpec:
    """One dimension: the figure JSON ``Plotly.newPlot`` consumes — one dot
    per entity, publications on x, spend on y — and the exact values behind
    it, so the template renders the section table without plotly (§9)."""

    dimension_id: str
    title: str
    columns: tuple[ColumnSpec, ...]
    rows: tuple[GroupRow, ...]
    figure: dict[str, Any]


@dataclass(frozen=True, slots=True)
class StatisticsReport:
    """One statistics view end to end — the seam the PDF renderer reuses (plan §13)."""

    headline: Headline
    charts: tuple[ChartSpec, ...]
