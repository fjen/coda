"""Browser check (plan §11 last bullet): a real browser paints the server's
figure JSON — one svg per [data-chart] mount — and a drill-down click lands on
the funding-request list filtered to exactly the clicked chart row's set."""

from urllib.parse import urlencode

import pytest
from django.urls import reverse
from playwright.sync_api import Page, expect
from pytest_django.live_server_helper import LiveServer

from coda.apps.fundingrequests.forms import _FACET_CHOICE_LIMIT
from coda.apps.publications.models import LinkType
from coda.contexts.statistics.dimensions import DIMENSIONS
from tests import modelfactory
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


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__journal_facet__typing__narrow_options_server_side(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    """The journal facet searches server-side (the registry is too large to
    enumerate): typing posts ``journal_q`` through the hidden input, and the
    re-rendered rail offers only the matches — focus and query text survive
    the swap."""
    seed()
    publisher = modelfactory.publisher(name="Shared publisher")
    for index in range(_FACET_CHOICE_LIMIT + 20):
        modelfactory.journal(publisher_id=publisher.pk, title=f"Facet {index:03d}")
    match = modelfactory.journal(publisher_id=publisher.pk, title="Qwertyuiop unique")
    _goto_statistics(coda_page, live_server)

    facet = coda_page.locator("search-select-multi#id_journal")
    search_box = facet.locator(".search-input")
    expect(search_box).to_be_visible()
    expect(facet.locator("option")).to_have_count(_FACET_CHOICE_LIMIT)

    search_box.fill("qwerty")

    expect(facet.locator('input[name="journal_q"]')).to_have_value("qwerty")
    expect(facet.locator("option")).to_have_count(1)
    expect(facet.locator("option")).to_have_text(match.title)
    active = coda_page.evaluate("() => document.activeElement?.shadowRoot?.activeElement?.value")
    assert active == "qwerty"


@pytest.mark.ui_test
@pytest.mark.django_db(transaction=True)
def test__journal_facet__selecting_a_match__keeps_the_narrowed_list(
    link_types: None, coda_page: Page, live_server: LiveServer
) -> None:
    """Picking matches must not drop the searched term — multi-select under
    one term is the whole point of ``journal_q``: each selection's change
    event serializes the queued typing term (re-seeded from ``data-q`` after
    every swap), so the rail stays narrowed across *two consecutive picks*
    and the box restores the term. *Clear all* then genuinely clears
    everything — a stale search term must not resurrect itself."""
    seed()
    publisher = modelfactory.publisher(name="Shared publisher")
    for index in range(_FACET_CHOICE_LIMIT + 20):
        modelfactory.journal(publisher_id=publisher.pk, title=f"Facet {index:03d}")
    first = modelfactory.journal(publisher_id=publisher.pk, title="Qwertyuiop unique")
    second = modelfactory.journal(publisher_id=publisher.pk, title="Qwertyuiop second")
    _goto_statistics(coda_page, live_server)

    facet = coda_page.locator("search-select-multi#id_journal")
    search_box = facet.locator(".search-input")
    expect(search_box).to_be_visible()
    search_box.fill("qwerty")
    expect(facet.locator("option")).to_have_count(2)

    facet.locator(".dropdown .option", has_text=first.title).click()

    expect(facet.locator(".selected-tag span")).to_have_text([first.title])
    expect(
        coda_page.locator("#active-filters .active-filter").filter(has_text=first.title)
    ).to_be_visible()
    expect(facet.locator("option")).to_have_count(2)
    expect(facet.locator('input[name="journal_q"]')).to_have_value("qwerty")
    expect(search_box).to_have_value("qwerty")

    # The multi-select case: a second pick on the swapped-in element, whose
    # queued term can only come from the server's data-q.
    search_box.click()
    facet.locator(".dropdown .option", has_text=second.title).click()

    expect(facet.locator(".selected-tag span")).to_have_text([first.title, second.title])
    expect(
        coda_page.locator("#active-filters .active-filter").filter(has_text=second.title)
    ).to_be_visible()
    expect(facet.locator("option")).to_have_count(2)
    expect(facet.locator(f'option[value="{second.pk}"]')).to_be_attached()
    expect(facet.locator('input[name="journal_q"]')).to_have_value("qwerty")
    expect(search_box).to_have_value("qwerty")

    coda_page.locator(filter_ui_selectors.FILTER_CLEAR_ALL).click()

    expect(facet.locator("option")).to_have_count(_FACET_CHOICE_LIMIT)
    expect(facet.locator('input[name="journal_q"]')).to_have_value("")
    expect(search_box).to_have_value("")
    expect(facet.locator(".selected-tag")).to_have_count(0)
