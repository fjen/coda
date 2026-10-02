import hashlib
from decimal import Decimal
from http import HTTPStatus
from types import SimpleNamespace
from typing import cast
from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.staticfiles.finders import find
from django.template.response import TemplateResponse
from django.test import Client
from django.test.html import parse_html
from django.urls import reverse
from django.utils import timezone

from coda.apps.fundingrequests.forms import FundingRequestListFilterForm
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.invoices.models import Invoice
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publications.models import PublicationAttachedConcept
from coda.apps.statistics.drilldown import facet_param_names
from coda.apps.statistics.views.page import ChartPanel, ChartRow
from coda.contexts.statistics import charts
from coda.contexts.statistics.dimensions import DIMENSIONS
from coda.contexts.statistics.dto import Measure
from coda.domain.money import Currency
from coda.domain.publication import License, OpenAccessType
from tests import modelfactory
from tests.filterdom import walk
from tests.statistics import helpers

PERIOD = {"start_date": "2026-01-01", "end_date": "2026-12-31"}


def seed() -> SimpleNamespace:
    """One fully funded request, one without an invoice, one without a rate.

    The funded request touches every dimension of the §7 registry; the other
    two drive the headline's provenance counters (ADR-0003).
    """
    institution = modelfactory.institution()
    funded = helpers.request("Funded paper")
    helpers.corresponding_author(funded, institution.pk)
    _subject_area_from_configured_vocabulary(funded)
    _named_publication_type(funded)
    publication = funded.publication
    publication.license = License.CC_BY.name
    publication.open_access_type = OpenAccessType.Gold.name
    publication.save()
    helpers.with_attached_contract(funded)
    position = helpers.position(publication.pk, Decimal("1000.00"), Decimal("0.20"))
    source = helpers.budget("Central Fund")
    position.assign_funding(source, Decimal("600.00"))
    helpers.invoice([position])

    helpers.request("Paper without invoice")
    unconvertible = helpers.request("Paper without rate")
    foreign = helpers.position(
        unconvertible.publication.pk,
        Decimal("500.00"),
        Decimal("0.19"),
        currency=Currency.USD,
    )
    unconvertible_invoice = helpers.invoice([foreign])

    journal = publication.article_journal
    attached = publication.attached_contracts.get()
    return SimpleNamespace(
        funded=funded,
        publication=publication,
        journal=journal,
        publisher=journal.publisher,
        institution=institution,
        source=source,
        contract=attached.contract,
        contract_year=attached.contract_year,
        funder=funded.external_funding.get().organization,
        subject_area=publication.subject_area,
        publication_type=publication.publication_type,
        unconvertible_invoice=unconvertible_invoice,
    )


def _subject_area_from_configured_vocabulary(funded: FundingRequest) -> None:
    """Attach a subject-area concept from the vocabulary the facet offers —
    only those are expressible as list filters, hence only those get links."""
    GlobalPreferences.get_subject_classification_vocabulary()  # ensures the default is set
    vocabulary = GlobalPreferences.objects.get().subject_classification_vocabulary
    assert vocabulary is not None
    concept = modelfactory.concept(vocabulary=vocabulary)
    funded.publication.subject_area = PublicationAttachedConcept.objects.create(
        name=concept.name, vocabulary=concept.vocabulary, entity_id=concept.entity_id
    )
    funded.publication.save()


def _named_publication_type(funded: FundingRequest) -> None:
    """Attach a publication-type concept from the vocabulary the facet offers —
    only those are expressible as list filters, hence only those get links."""
    GlobalPreferences.get_article_publication_type_vocabulary()  # ensures the default is set
    vocabulary = GlobalPreferences.objects.get().article_publication_type_vocabulary
    assert vocabulary is not None
    concept = modelfactory.concept(vocabulary=vocabulary)
    funded.publication.publication_type = PublicationAttachedConcept.objects.create(
        name=concept.name, vocabulary=vocabulary, entity_id=concept.entity_id
    )
    funded.publication.save()


def goto(client: Client, **query: str) -> object:
    return client.get(reverse("statistics:page"), data={**PERIOD, **query})


def sections_by_id(response: object) -> dict[str, object]:
    return {section.dimension_id: section for section in response.context["sections"]}


def amount_chart(section: object) -> object:
    return next(
        chart for chart in section.charts if chart.measure in (Measure.PAID_OUT, Measure.FUNDED_BY)
    )


def publications_chart(section: object) -> object:
    return next(chart for chart in section.charts if chart.measure is Measure.PUBLICATIONS)


def row_by_label(chart: object, label: str) -> object:
    return next(row for row in chart.rows if row.label == label)


def query_params(url: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(url).query)


def funded_journal_pk() -> int:
    from coda.apps.publications.models import Publication

    return Publication.objects.get(title="Funded paper").article_journal_id


@pytest.mark.django_db
def test__statistics_page__anonymous__redirects_to_login(client: Client) -> None:
    response = client.get(reverse("statistics:page"))

    assert response.status_code == HTTPStatus.FOUND
    assert response.headers["Location"].startswith(reverse("login"))


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__statistics_page__bare_get__redirects_to_current_year_period(client: Client) -> None:
    year = timezone.localdate().year

    response = client.get(reverse("statistics:page"))

    assert response.status_code == HTTPStatus.FOUND
    assert query_params(response.headers["Location"]) == {
        "start_date": [f"{year}-01-01"],
        "end_date": [f"{year}-12-31"],
    }


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__statistics_page__bare_get_with_filters__redirect_preserves_them(client: Client) -> None:
    year = timezone.localdate().year

    response = client.get(reverse("statistics:page"), data={"license": License.CC_BY.value})

    assert response.status_code == HTTPStatus.FOUND
    assert query_params(response.headers["Location"]) == {
        "license": [License.CC_BY.value],
        "start_date": [f"{year}-01-01"],
        "end_date": [f"{year}-12-31"],
    }


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__statistics_page__explicit_period__renders(client: Client) -> None:
    seed()

    response = goto(client)

    assert response.status_code == HTTPStatus.OK


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__statistics_page__renders_a_section_per_registered_dimension(client: Client) -> None:
    seed()

    response = goto(client)

    assert {section.dimension_id for section in response.context["sections"]} == {
        dimension.id for dimension in DIMENSIONS
    }


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__statistics_page__every_chart_renders_a_plotly_mount_and_json_script(
    client: Client,
) -> None:
    seed()

    html = goto(client).content.decode()
    dom = parse_html(html)

    charts = [
        element
        for element in walk(dom)
        if element.name == "div" and (dict(element.attributes).get("data-chart") or "")
    ]
    scripts = [
        element
        for element in walk(dom)
        if element.name == "script" and dict(element.attributes).get("type") == "application/json"
    ]
    mounted = {str(dict(element.attributes).get("data-chart")) for element in charts}
    script_ids = {str(dict(element.attributes).get("id", "")) for element in scripts}

    # Every registered dimension+measure pairs one mount with one figure payload.
    expected = {
        f"chart-{dimension.id}-{measure.value}"
        for dimension in DIMENSIONS
        for measure in dimension.measures()
    }
    assert mounted == expected
    assert mounted <= script_ids


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__statistics_page__headline__counts_publications_spend_and_provenance(
    client: Client,
) -> None:
    seed()

    headline = goto(client).context["headline"]

    assert headline.publications == 3
    assert headline.spend == Decimal("1200.00")
    assert headline.requests_without_invoice == 1
    assert headline.requests_unconvertible == 1


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__statistics_page__currency_incomplete_notice__counts_requests_and_links_invoices(
    client: Client,
) -> None:
    """The page states how many requests lost amounts and links each one's
    invoices (plan §9, §10 Q21)."""
    fixture = seed()

    response = goto(client)

    number = Invoice.objects.get(pk=fixture.unconvertible_invoice).number
    assert [(i.pk, i.number) for i in response.context["incomplete_invoices"]] == [
        (fixture.unconvertible_invoice, number)
    ]

    html = " ".join(response.content.decode().split())
    assert reverse("invoices:detail", args=[fixture.unconvertible_invoice]) in html
    assert number in html
    assert "1 request with excluded amounts" in html
    assert "Requests with excluded amounts" in html


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__statistics_page__additive_dimension__shows_total(client: Client) -> None:
    seed()

    response = goto(client)

    chart = amount_chart(sections_by_id(response)["subject_area"])
    assert chart.note is None
    assert chart.total == Decimal("1200.00")


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__statistics_page__non_additive_dimension__shows_note_instead_of_total(
    client: Client,
) -> None:
    seed()

    response = goto(client)

    chart = publications_chart(sections_by_id(response)["institution"])
    assert chart.total is None
    assert chart.note is not None
    assert "ADR-0007" in chart.note


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__statistics_page__chart_rows__drill_down_to_the_filtered_request_list(
    client: Client,
) -> None:
    fixture = seed()

    response = goto(client)
    sections = sections_by_id(response)
    list_url = reverse("fundingrequests:list")

    expected: dict[str, tuple[object, str, str, str]] = {
        "journal": (
            amount_chart(sections["journal"]),
            fixture.journal.title,
            "journal",
            str(fixture.journal.pk),
        ),
        "publisher": (
            amount_chart(sections["publisher"]),
            fixture.publisher.name,
            "publisher",
            str(fixture.publisher.pk),
        ),
        "institution": (
            amount_chart(sections["institution"]),
            fixture.institution.name,
            "institution",
            str(fixture.institution.pk),
        ),
        "funder": (
            publications_chart(sections["funder"]),
            fixture.funder.name,
            "funder",
            str(fixture.funder.pk),
        ),
        "subject_area": (
            publications_chart(sections["subject_area"]),
            fixture.subject_area.name,
            "subject_area",
            str(fixture.subject_area.entity_id),
        ),
        "publication_type": (
            publications_chart(sections["publication_type"]),
            fixture.publication_type.name,
            "publication_type_concept",
            str(fixture.publication_type.entity_id),
        ),
        "license": (
            publications_chart(sections["license"]),
            License.CC_BY.name,
            "license",
            License.CC_BY.value,
        ),
        "open_access_type": (
            publications_chart(sections["open_access_type"]),
            OpenAccessType.Gold.name,
            "open_access_type",
            OpenAccessType.Gold.value,
        ),
        "publication_form": (
            publications_chart(sections["publication_form"]),
            "article",
            "publication_form",
            "article",
        ),
        "cost_type": (amount_chart(sections["cost_type"]), "gold-oa", "cost_type", "gold-oa"),
        "funding_source": (
            amount_chart(sections["funding_source"]),
            "Central Fund",
            "funding_source",
            str(fixture.source.id),
        ),
    }
    for dimension_id, (chart, label, param, value) in expected.items():
        row = row_by_label(chart, label)
        assert row.link is not None, dimension_id
        assert row.link.startswith(list_url), dimension_id
        params = query_params(row.link)
        assert params[param] == [value], dimension_id
        assert params["start_date"] == ["2026-01-01"], dimension_id
        assert params["end_date"] == ["2026-12-31"], dimension_id

    contract_chart = publications_chart(sections["contract"])
    contract_row = row_by_label(
        contract_chart, f"{fixture.contract.name} ({fixture.contract_year})"
    )
    contract_params = query_params(contract_row.link)
    assert contract_params["contract_name"] == [str(fixture.contract.pk)]
    assert contract_params["contract_year"] == [str(fixture.contract_year)]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__statistics_page__unassigned_and_unknown_rows__have_no_drill_down(
    client: Client,
) -> None:
    seed()

    response = goto(client)
    sections = sections_by_id(response)

    unassigned = row_by_label(amount_chart(sections["funding_source"]), "Unassigned")
    assert unassigned.link is None
    unknown = row_by_label(publications_chart(sections["institution"]), "Unknown")
    assert unknown.link is None


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__statistics_page__publication_without_journal_or_publisher__forms_unknown_row_without_facet(
    client: Client,
) -> None:
    """§2 #7: the "Unknown" form row has no facet value behind it —
    ``PublicationFormCriteria`` matches neither form — so it carries no
    drill-down, and the article/monograph facets both exclude the request."""
    seed()
    formless = helpers.request("Formless paper")
    formless.publication.article_journal = None
    formless.publication.save()

    chart = cast(ChartPanel, publications_chart(sections_by_id(goto(client))["publication_form"]))
    assert [(row.label, row.publications) for row in chart.rows] == [
        ("article", 3),
        ("Unknown", 1),
    ]
    assert cast(ChartRow, row_by_label(chart, "Unknown")).link is None

    articles = cast(
        TemplateResponse,
        client.get(reverse("fundingrequests:list"), {**PERIOD, "publication_form": "article"}),
    )
    titles = {str(item.publication_title) for item in articles.context["entities"]}
    assert titles == {"Funded paper", "Paper without invoice", "Paper without rate"}

    monographs = cast(
        TemplateResponse,
        client.get(reverse("fundingrequests:list"), {**PERIOD, "publication_form": "monograph"}),
    )
    assert list(monographs.context["entities"]) == []


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__statistics_page__active_filters__narrow_every_chart_and_survive_in_drill_downs(
    client: Client,
) -> None:
    seed()

    response = goto(client, license=License.CC_BY.value)
    sections = sections_by_id(response)

    # Only the CC-BY request remains, so the additive totals reflect exactly it.
    assert amount_chart(sections["subject_area"]).total == Decimal("1200.00")
    assert publications_chart(sections["journal"]).rows[0].publications == 1

    link_params = query_params(amount_chart(sections["journal"]).rows[0].link)
    assert link_params["license"] == [License.CC_BY.value]
    assert link_params["journal"] == [str(funded_journal_pk())]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__statistics_page__drill_down_links__reproduce_their_chart_sets_in_the_list(
    client: Client,
) -> None:
    """Round-trip (§2 #7, plan §11): loading a row's link as the list view
    yields exactly the requests the chart row counted, per facet."""
    fixture = seed()
    sections = sections_by_id(goto(client))

    cases: dict[str, tuple[object, str, str, str]] = {
        "institution": (
            amount_chart(sections["institution"]),
            fixture.institution.name,
            "institution",
            str(fixture.institution.pk),
        ),
        "license": (
            publications_chart(sections["license"]),
            License.CC_BY.name,
            "license",
            License.CC_BY.value,
        ),
        "journal": (
            publications_chart(sections["journal"]),
            fixture.journal.title,
            "journal",
            str(fixture.journal.pk),
        ),
        "publisher": (
            amount_chart(sections["publisher"]),
            fixture.publisher.name,
            "publisher",
            str(fixture.publisher.pk),
        ),
        "funding_source": (
            amount_chart(sections["funding_source"]),
            "Central Fund",
            "funding_source",
            str(fixture.source.id),
        ),
    }

    for dimension_id, (chart, label, param, value) in cases.items():
        link = row_by_label(chart, label).link
        assert link is not None, dimension_id
        assert query_params(link)[param] == [value], dimension_id

        list_response = client.get(link)

        assert list_response.status_code == HTTPStatus.OK, dimension_id
        titles = {str(item.publication_title) for item in list_response.context["entities"]}
        assert titles == {"Funded paper"}, dimension_id


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__statistics_page__every_dimension__section_measures_and_facet_round_out_the_registry(
    client: Client,
) -> None:
    """§7 completeness: every registry dimension gets its section, one chart per
    supported measure with the shared measure label, additive charts a total and
    non-additive ones the ADR-0007 note — and every dimension has a facet whose
    params the shared form actually accepts (§2 #7 lockstep)."""
    seed()
    form_fields = set(FundingRequestListFilterForm().fields)
    sections = sections_by_id(goto(client))

    for dimension in DIMENSIONS:
        assert dimension.id in sections, dimension.id
        section = sections[dimension.id]
        assert section.label == dimension.label, dimension.id

        panels = {chart.measure: chart for chart in section.charts}
        assert set(panels) == set(dimension.measures()), dimension.id
        for measure, panel in panels.items():
            assert panel.measure_label == charts.MEASURE_LABELS[measure], dimension.id
            if dimension.is_additive(measure):
                assert panel.total is not None, (dimension.id, measure)
                assert panel.note is None, (dimension.id, measure)
            else:
                assert panel.total is None, (dimension.id, measure)
                assert panel.note == charts.NON_ADDITIVE_NOTE, (dimension.id, measure)

        facet_params = facet_param_names(dimension.id)
        assert facet_params, dimension.id
        assert set(facet_params) <= form_fields, dimension.id


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__statistics_region__swaps_sidebar_toolbar_count_and_sections(
    client: Client,
) -> None:
    seed()

    response = client.get(reverse("statistics:region"), data=PERIOD, headers={"hx-request": "true"})

    html = response.content.decode()
    assert 'hx-swap-oob="innerHTML:#filter-sidebar-form"' in html
    assert 'data-chart="chart-subject_area-publications"' in html
    assert response["HX-Push-Url"].startswith(reverse("statistics:page"))


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__plotly_asset__matches_the_installed_plotly_bundle() -> None:
    path = find("js/vendor/plotly.min.js")
    assert path is not None

    import plotly.offline

    with open(path, "rb") as asset:
        vendored = hashlib.sha256(asset.read()).hexdigest()
    bundled = hashlib.sha256(plotly.offline.get_plotlyjs().encode("utf-8")).hexdigest()
    assert vendored == bundled


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__statistics_page__nav__entry_links_to_statistics(client: Client) -> None:
    html = client.get(reverse("home")).content.decode()

    assert reverse("statistics:page") in html
    assert "Statistics" in html


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__export_home__offers_a_statistics_card(client: Client) -> None:
    html = client.get(reverse("exports:export_home")).content.decode()

    assert reverse("statistics:page") in html
    assert "Statistics" in html


@pytest.mark.django_db
def test__statistics_urls__resolve() -> None:
    assert reverse("statistics:page") == "/statistics/"
    assert reverse("statistics:region") == "/statistics/region/"
