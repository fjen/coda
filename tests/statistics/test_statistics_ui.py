"""Browser check (plan §11 last bullet): a real browser paints the server's
figure JSON — one svg per [data-chart] mount — and a drill-down click lands on
the funding-request list filtered to exactly the clicked chart row's set."""

from urllib.parse import urlencode

import pytest
from django.urls import reverse
from playwright.sync_api import Page, expect
from pytest_django.live_server_helper import LiveServer

from coda.apps.publications.models import LinkType
from coda.contexts.statistics.dimensions import DIMENSIONS
from tests.page_objects import filter_ui_selectors
from tests.statistics.test_page import PERIOD, seed


@pytest.fixture
def link_types() -> None:
    """LinkTypes the request factory attaches; transactional tests truncate the
    session fixture's rows, so they must be recreated here."""
    LinkType.objects.get_or_create(name="DOI")
    LinkType.objects.get_or_create(name="ISBN")


def _goto_statistics(page: Page, live_server: LiveServer) -> None:
    # Desktop width like the other filter-rail UI tests; the period goes into
    # the URL so the page renders immediately — no redirect in front of charts.
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(f"{live_server.url}{reverse('statistics:page')}?{urlencode(PERIOD)}")
    page.wait_for_function("() => typeof Plotly !== 'undefined'")


def _wait_for_charts(page: Page) -> None:
    page.wait_for_function(
        "() => [...document.querySelectorAll('[data-chart]')]"
        ".every((el) => el.dataset.plotlyRendered === 'true')"
    )


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__statistics_page__plotly__renders_one_svg_per_chart_mount(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    seed()
    _goto_statistics(coda_page, live_server)
    _wait_for_charts(coda_page)

    expected = sum(len(dimension.measures()) for dimension in DIMENSIONS)
    expect(coda_page.locator("[data-chart]")).to_have_count(expected)

    painted = coda_page.eval_on_selector_all(
        "[data-chart]", "els => els.filter((el) => el.querySelector('svg')).length"
    )
    assert painted == expected


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__statistics_page__drill_down__click_lands_on_the_filtered_list(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    fixture = seed()
    _goto_statistics(coda_page, live_server)
    _wait_for_charts(coda_page)

    coda_page.locator("#statistics-journal").get_by_role(
        "link", name=fixture.journal.title
    ).first.click()

    coda_page.wait_for_url(lambda url: "/fundingrequests/list/" in url)
    assert f"journal={fixture.journal.pk}" in coda_page.url

    listing = coda_page.locator(filter_ui_selectors.FUNDINGREQUEST_LIST)
    expect(listing.get_by_text("Funded paper")).to_be_visible()
    expect(listing.get_by_text("Paper without invoice")).to_be_hidden()
    expect(listing.get_by_text("Paper without rate")).to_be_hidden()
