"""Criteria tests for the statistics-aligned filter facets (spec §8).

Each facet gets one criteria test, in the style of
``tests/fundingrequests/test_fundingrequest_repository.py``: arrange models,
run ``fundingrequest_query.search`` with a single criterion, assert the set.
"""

import uuid
from typing import Any

import pytest
from django.utils.datastructures import MultiValueDict

from coda.apps.fundingrequests import fundingrequest_query
from coda.apps.fundingrequests import fundingrequest_query as fq
from coda.apps.fundingrequests.forms import FundingRequestListFilterForm
from coda.apps.fundingrequests.fundingrequest_query import (
    CostTypeCriteria,
    FunderCriteria,
    FundingSourcesCriteria,
    InstitutionCriteria,
    JournalCriteria,
    LicenseCriteria,
    OpenAccessTypeCriteria,
    PublisherCriteria,
    SubjectAreaCriteria,
)
from coda.apps.fundingrequests.models import ExternalFunding
from coda.apps.institutions.models import Institution
from coda.apps.preferences.models import GlobalPreferences
from coda.contexts.finance.services import invoice_service
from coda.domain.author import InstitutionId, Role
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.invoice import CreditorId, FundingSourceId
from coda.domain.publication import Authors
from coda.domain.publication.publication import License, OpenAccessType, PublicationId
from tests import domainfactory, modelfactory


@pytest.mark.django_db
def test__searching_by_institution__returns_requests_whose_corresponding_authors_affiliate_in_the_subtree() -> (
    None
):
    parent = modelfactory.institution()
    child = Institution.objects.create(name="Child University", parent=parent)

    matching = modelfactory.fundingrequest(
        "Subtree corresponding author paper",
        authors=Authors(
            [domainfactory.author(InstitutionId(child.pk), role=Role.CORRESPONDING_AUTHOR)]
        ),
    )
    # Non-corresponding roles never match, even inside the subtree.
    _ = modelfactory.fundingrequest(
        "Subtree co-author paper",
        authors=Authors([domainfactory.author(InstitutionId(child.pk), role=Role.CO_AUTHOR)]),
    )
    # Affiliations outside the selected subtree never match.
    _ = modelfactory.fundingrequest(
        "Elsewhere corresponding author paper",
        authors=Authors(
            [
                domainfactory.author(
                    InstitutionId(modelfactory.institution().pk),
                    role=Role.SUBMITTING_CORRESPONDING_AUTHOR,
                )
            ]
        ),
    )

    results = fundingrequest_query.search(
        fundingrequest_query.InstitutionCriteria(institutions=[InstitutionId(parent.pk)])
    )

    assert list(results) == [matching]


@pytest.mark.django_db
def test__searching_by_publisher__returns_articles_of_the_journal_publisher_and_monographs_of_that_publisher() -> (
    None
):
    article_publisher = modelfactory.publisher(name="Article Publisher")
    monograph_publisher = modelfactory.publisher(name="Monograph Publisher")
    other_publisher = modelfactory.publisher(name="Other Publisher")

    article = modelfactory.fundingrequest("Article via Article Publisher")
    article.publication.article_journal = modelfactory.journal(publisher_id=article_publisher.pk)
    article.publication.save()

    monograph = modelfactory.fundingrequest("Monograph of Monograph Publisher")
    monograph.publication.article_journal = None
    monograph.publication.monograph_publisher = monograph_publisher
    monograph.publication.save()

    _ = modelfactory.fundingrequest("Article via Other Publisher")
    other = modelfactory.journal(publisher_id=other_publisher.pk)
    _.publication.article_journal = other
    _.publication.save()

    results = fundingrequest_query.search(
        fundingrequest_query.PublisherCriteria(
            publishers=[article_publisher.pk, monograph_publisher.pk]
        )
    )

    assert sorted(r.pk for r in results) == sorted([article.pk, monograph.pk])


@pytest.mark.django_db
def test__searching_by_journal__returns_only_requests_published_in_the_selected_journals() -> None:
    selected = modelfactory.journal(title="Selected Journal")
    other = modelfactory.journal(title="Other Journal")

    matching = modelfactory.fundingrequest("Paper in selected journal")
    matching.publication.article_journal = selected
    matching.publication.save()

    _ = modelfactory.fundingrequest("Paper in other journal")
    _.publication.article_journal = other
    _.publication.save()

    results = fundingrequest_query.search(
        fundingrequest_query.JournalCriteria(journals=[selected.pk])
    )

    assert list(results) == [matching]


@pytest.mark.django_db
def test__searching_by_funder__returns_only_requests_with_external_funding_from_the_selected_funders() -> (
    None
):

    funder_a = modelfactory.funding_organization(name="Funder A")
    funder_b = modelfactory.funding_organization(name="Funder B")

    matching = modelfactory.fundingrequest("Externally funded by A")
    ExternalFunding.objects.filter(funding_request=matching).update(organization=funder_a)

    _ = modelfactory.fundingrequest("Externally funded by B")
    ExternalFunding.objects.filter(funding_request=_).update(organization=funder_b)

    results = fundingrequest_query.search(
        fundingrequest_query.FunderCriteria(funders=[funder_a.pk])
    )

    assert list(results) == [matching]


@pytest.mark.django_db
def test__searching_by_subject_area__returns_only_requests_with_the_selected_concept_entity_ids() -> (
    None
):
    selected_area = uuid.uuid4()

    matching = modelfactory.fundingrequest("Subject X paper")
    matching.publication.subject_area.entity_id = selected_area
    matching.publication.subject_area.save()

    _ = modelfactory.fundingrequest("Subject Y paper")
    _.publication.subject_area.entity_id = uuid.uuid4()
    _.publication.subject_area.save()

    results = fundingrequest_query.search(
        fundingrequest_query.SubjectAreaCriteria(subject_areas=[selected_area])
    )

    assert list(results) == [matching]


@pytest.mark.django_db
def test__searching_by_license__returns_only_requests_with_the_selected_licenses() -> None:
    matching = modelfactory.fundingrequest("CC-BY paper")
    matching.publication.license = License.CC_BY.name
    matching.publication.save()

    _ = modelfactory.fundingrequest("CC0 paper")
    _.publication.license = License.CC0.name
    _.publication.save()

    results = fundingrequest_query.search(
        fundingrequest_query.LicenseCriteria(licenses=[License.CC_BY])
    )

    assert list(results) == [matching]


@pytest.mark.django_db
def test__searching_by_open_access_type__returns_only_requests_with_the_selected_types() -> None:
    matching = modelfactory.fundingrequest("Gold open access paper")
    matching.publication.open_access_type = OpenAccessType.Gold.name
    matching.publication.save()

    _ = modelfactory.fundingrequest("Closed paper")
    _.publication.open_access_type = OpenAccessType.Closed.name
    _.publication.save()

    results = fundingrequest_query.search(
        fundingrequest_query.OpenAccessTypeCriteria(open_access_types=[OpenAccessType.Gold])
    )

    assert list(results) == [matching]


@pytest.mark.django_db
def test__searching_by_publication_form__splits_articles_and_monographs_on_the_shared_rule() -> (
    None
):
    article = modelfactory.fundingrequest("Journal article")

    monograph = modelfactory.fundingrequest("Monograph")
    monograph.publication.article_journal = None
    monograph.publication.monograph_publisher = modelfactory.publisher(name="Form Publisher")
    monograph.publication.save()

    articles = fundingrequest_query.search(
        fundingrequest_query.PublicationFormCriteria(
            publication_form=fundingrequest_query.PublicationForm.article
        )
    )
    monographs = fundingrequest_query.search(
        fundingrequest_query.PublicationFormCriteria(
            publication_form=fundingrequest_query.PublicationForm.monograph
        )
    )

    assert list(articles) == [article]
    assert list(monographs) == [monograph]


def _invoice_with_publication_position(
    funding_request: Any, cost_type: PublicationCostType, source_name: str
) -> None:
    """One invoice holding a single publication-scoped position, fully assigned."""
    position = domainfactory.publication_position(
        PublicationId(funding_request.publication.pk), cost_type=cost_type
    )
    position.assign_remaining(
        domainfactory.budget(FundingSourceId(modelfactory.budget(name=source_name).pk))
    )
    invoice = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().pk), positions=[position]
    )
    invoice_service.save(invoice)


@pytest.mark.django_db
def test__searching_by_cost_type__returns_only_requests_with_a_publication_position_of_that_cost_type() -> (
    None
):
    matching = modelfactory.fundingrequest("VAT position paper")
    _invoice_with_publication_position(matching, PublicationCostType.Vat, "VAT Budget")

    _ = modelfactory.fundingrequest("Cover charge paper")
    _invoice_with_publication_position(_, PublicationCostType.Cover_Charge, "Cover Budget")

    results = fundingrequest_query.search(
        fundingrequest_query.CostTypeCriteria(cost_types=[PublicationCostType.Vat])
    )

    assert list(results) == [matching]


@pytest.mark.django_db
def test__searching_by_funding_source__returns_only_requests_with_assignments_to_the_selected_sources() -> (
    None
):
    matching = modelfactory.fundingrequest("Budget A paper")
    budget_a = modelfactory.budget(name="Facet Budget A")
    position = domainfactory.publication_position(PublicationId(matching.publication.pk))
    position.assign_remaining(domainfactory.budget(FundingSourceId(budget_a.pk)))
    invoice = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().pk), positions=[position]
    )
    invoice_service.save(invoice)

    other = modelfactory.fundingrequest("Budget B paper")
    budget_b = modelfactory.budget(name="Facet Budget B")
    other_position = domainfactory.publication_position(PublicationId(other.publication.pk))
    other_position.assign_remaining(domainfactory.budget(FundingSourceId(budget_b.pk)))
    other_invoice = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().pk), positions=[other_position]
    )
    invoice_service.save(other_invoice)

    results = fundingrequest_query.search(
        fundingrequest_query.FundingSourcesCriteria(funding_sources=[FundingSourceId(budget_a.pk)])
    )

    assert list(results) == [matching]


def test__search_params_with_facet_selections__build_criteria__produces_one_criterion_per_facet() -> (
    None
):
    subject = uuid.uuid4()
    params = fq.FundingRequestSearchParams(
        institutions=[InstitutionId(1)],
        publishers=[2],
        journals=[3],
        funders=[4],
        subject_areas=[subject],
        licenses=[License.CC_BY],
        publication_form=fq.PublicationForm.monograph,
        cost_types=[PublicationCostType.Vat],
        funding_sources=[FundingSourceId(5)],
    )

    criteria = fq.build_criteria(params)

    assert InstitutionCriteria(institutions=[InstitutionId(1)]) in criteria
    assert PublisherCriteria(publishers=[2]) in criteria
    assert JournalCriteria(journals=[3]) in criteria
    assert FunderCriteria(funders=[4]) in criteria
    assert SubjectAreaCriteria(subject_areas=[subject]) in criteria
    assert LicenseCriteria(licenses=[License.CC_BY]) in criteria
    assert fq.PublicationFormCriteria(publication_form=fq.PublicationForm.monograph) in criteria
    assert CostTypeCriteria(cost_types=[PublicationCostType.Vat]) in criteria
    assert FundingSourcesCriteria(funding_sources=[FundingSourceId(5)]) in criteria


def test__empty_search_params__build_criteria__produces_no_facet_criteria() -> None:
    criteria = fq.build_criteria(fq.FundingRequestSearchParams())

    facet_types = (
        InstitutionCriteria,
        PublisherCriteria,
        JournalCriteria,
        FunderCriteria,
        SubjectAreaCriteria,
        LicenseCriteria,
        fq.PublicationFormCriteria,
        CostTypeCriteria,
        FundingSourcesCriteria,
    )
    assert not [c for c in criteria if isinstance(c, facet_types)]


@pytest.mark.django_db
def test__facet_get_params__search_criteria__produces_the_matching_criteria() -> None:
    institution = modelfactory.institution()
    publisher = modelfactory.publisher(name="Form Publisher")
    journal = modelfactory.journal(title="Form Journal")
    funder = modelfactory.funding_organization(name="Form Funder")
    budget = modelfactory.budget(name="Form Budget")
    subject_vocabulary = modelfactory.vocabulary()
    concept = modelfactory.concept(subject_vocabulary)
    GlobalPreferences.set_subject_classification_vocabulary(subject_vocabulary)

    form = FundingRequestListFilterForm(
        MultiValueDict(
            {
                "institution": [str(institution.pk)],
                "publisher": [str(publisher.pk)],
                "journal": [str(journal.pk)],
                "funder": [str(funder.pk)],
                "subject_area": [str(concept.entity_id)],
                "license": [License.CC_BY.value],
                "open_access_type": [OpenAccessType.Gold.value],
                "publication_form": [fq.PublicationForm.monograph.value],
                "cost_type": [PublicationCostType.Vat.value],
                "funding_source": [str(budget.pk)],
            }
        )
    )

    assert form.is_valid(), form.errors

    criteria, _ = form.search_criteria()

    assert InstitutionCriteria(institutions=[InstitutionId(institution.pk)]) in criteria
    assert PublisherCriteria(publishers=[publisher.pk]) in criteria
    assert JournalCriteria(journals=[journal.pk]) in criteria
    assert FunderCriteria(funders=[funder.pk]) in criteria
    assert SubjectAreaCriteria(subject_areas=[concept.entity_id]) in criteria
    assert LicenseCriteria(licenses=[License.CC_BY]) in criteria
    assert OpenAccessTypeCriteria(open_access_types=[OpenAccessType.Gold]) in criteria
    assert fq.PublicationFormCriteria(publication_form=fq.PublicationForm.monograph) in criteria
    assert CostTypeCriteria(cost_types=[PublicationCostType.Vat]) in criteria
    assert FundingSourcesCriteria(funding_sources=[FundingSourceId(budget.pk)]) in criteria


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("param", "value"),
    [
        ("institution", "zzz"),
        ("publisher", "zzz"),
        ("journal", "zzz"),
        ("funder", "zzz"),
        ("subject_area", "not-a-uuid"),
        ("license", "bogus-license"),
        ("publication_form", "bogus-form"),
        ("cost_type", "bogus-cost"),
        ("funding_source", "zzz"),
    ],
)
def test__unparsable_facet_param__search_criteria__drops_the_facet(param: str, value: str) -> None:
    """A value the facet cannot parse narrows nothing, per the form's contract."""
    form = FundingRequestListFilterForm(MultiValueDict({param: [value]}))
    form.is_valid()

    criteria, _ = form.search_criteria()

    assert criteria == []
