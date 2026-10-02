# tests/statistics/test_queries.py

from datetime import date

import pytest
from coda.apps.fundingrequests import fundingrequest_query
from coda.apps.statistics import queries
from coda.domain.date import DateRange
from tests import modelfactory


def _criteria(period_start: date, period_end: date) -> list[fundingrequest_query.FundingRequestSearchCriteria]:
    return fundingrequest_query.build_criteria(
        fundingrequest_query.FundingRequestSearchParams(
            date_range=DateRange(period_start, period_end),
        )
    )


@pytest.mark.django_db
def test__requests_outside_the_period__fetch_requests__returns_only_requests_in_the_period() -> (
    None
):
    fr_march = modelfactory.fundingrequest(title="March FR")
    fr_march.request_date = date(2026, 3, 15)
    fr_march.save()
    fr_april = modelfactory.fundingrequest(title="April FR")
    fr_april.request_date = date(2026, 4, 15)
    fr_april.save()

    results = list(queries.fetch_requests(_criteria(date(2026, 3, 1), date(2026, 3, 31))))

    assert results == [fr_march]
