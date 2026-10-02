# tests/statistics/test_dataset.py

from datetime import date
from decimal import Decimal

import pytest

from coda.apps.fundingrequests import fundingrequest_query
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.invoices import funding_source_repository
from coda.apps.statistics import dataset, queries
from coda.contexts.finance.services import invoice_service
from coda.contexts.statistics.dto import FundingSourceRef, RequestFact
from coda.domain.date import DateRange
from coda.domain.finance import invoice_positions
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.invoice import CreditorId
from coda.domain.finance.invoice_positions import Position, PublicationItem
from coda.domain.finance.funding_sources import Budget
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency, Money
from coda.domain.publication.publication import PublicationId
from tests import domainfactory, modelfactory

PERIOD_START = date(2026, 3, 1)
PERIOD_END = date(2026, 3, 31)


def _facts(*, report_currency: Currency = Currency.EUR) -> tuple[RequestFact, ...]:
    """The dataset half of the real pipeline: fetch_requests -> build_facts."""
    criteria = fundingrequest_query.build_criteria(
        fundingrequest_query.FundingRequestSearchParams(
            date_range=DateRange(PERIOD_START, PERIOD_END),
        )
    )
    return dataset.build_facts(queries.fetch_requests(criteria), report_currency)


def _request(title: str) -> FundingRequest:
    fr = modelfactory.fundingrequest(title=title)
    fr.request_date = date(2026, 3, 15)
    fr.save()
    return fr


def _position(
    publication_id: int,
    amount: Decimal,
    tax_rate: Decimal,
    cost_type: str = "gold-oa",
    currency: Currency = Currency.EUR,
) -> Position:
    return invoice_positions.create(
        item=PublicationItem(
            PublicationId(publication_id), PublicationCostType(cost_type)
        ),
        cost=Money(amount, currency),
        tax_rate=TaxRate(tax_rate),
        external_position_id="",
    )


def _budget(name: str) -> Budget:
    source = Budget(None, name)
    source.id = funding_source_repository.create(source)
    return source


def _invoice(
    positions: list[Position],
    conversions: dict[Currency, Decimal] | None = None,
) -> None:
    creditor = modelfactory.creditor()
    invoice = domainfactory.invoice(creditor=CreditorId(creditor.pk), positions=positions)
    for currency, rate in (conversions or {}).items():
        invoice.add_conversion(rate, currency)
    invoice.id = invoice_service.save(invoice)


@pytest.mark.django_db
def test__request_with_two_positions_one_assignment_each__build_facts__sums_spend_and_counts_one_publication() -> (
    None
):
    fr = _request("Two positions")
    publisher_budget = _budget("Publisher Budget")
    library_fund = _budget("Library Fund")
    position_a = _position(fr.publication_id, Decimal("1000.00"), Decimal("0.19"))
    position_a.assign_funding(publisher_budget, Decimal("1000.00"))
    position_b = _position(
        fr.publication_id, Decimal("500.00"), Decimal("0.00"), cost_type="other"
    )
    position_b.assign_funding(library_fund, Decimal("500.00"))
    _invoice([position_a, position_b])

    facts = _facts()

    assert len(facts) == 1
    fact = facts[0]
    assert fact.request_id == fr.pk
    assert fact.publication_id == fr.publication_id
    assert fact.paid_out_total == Decimal("1690.00")
    assert dict(fact.paid_out_by_cost_type) == {
        "gold-oa": Decimal("1190.00"),
        "other": Decimal("500.00"),
    }
    assert dict(fact.funded_by) == {
        FundingSourceRef("Publisher Budget"): Decimal("1190.00"),
        FundingSourceRef("Library Fund"): Decimal("500.00"),
    }
    assert fact.unassigned == Decimal("0.00")
    assert fact.has_invoice is True
    assert fact.invoices_without_rate == 0
