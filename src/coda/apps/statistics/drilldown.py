"""Chart row -> funding-request list URL (plan §2 #7, §8).

A chart row's drill-down is literally a list-view URL: the shared form's facet
params plus the row's value, so loading it reproduces exactly the chart's set —
the active filters are preserved, the row's value is added (multi-valued facets)
or set (single-valued facets).

Rows grouped by *name* resolve to facet values by name — every model row sharing
the name contributes its id, so the link covers precisely the chart's merged set.
The synthetic rows ("Other", "Unknown", "Unassigned") and dimensions without a
facet in the shared form have no drill-down: the list view could not reproduce
their set. The publication-type concept registry (§7) is such a dimension — §8's
settled facet list carries no facet for it.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from django.http import HttpRequest, QueryDict

from coda.apps.contracts.models import Contract
from coda.apps.fundingrequests.models import FundingOrganization
from coda.apps.institutions.models import Institution
from coda.apps.invoices.models import FundingSource
from coda.apps.journals.models import Journal
from coda.apps.listfilters import build_url
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publishers.models import Publisher
from coda.contexts.statistics.dto import GroupRow
from coda.domain.publication import License, OpenAccessType

_LIST_URL = "fundingrequests:list"

# dimension id -> (facet param, multi-valued facet?)
_FACETS: Mapping[str, tuple[str, bool]] = {
    "institution": ("institution", True),
    "subject_area": ("subject_area", True),
    "publication_form": ("publication_form", False),
    "license": ("license", True),
    "open_access_type": ("open_access_type", True),
    "journal": ("journal", True),
    "publisher": ("publisher", True),
    "cost_type": ("cost_type", True),
    "funder": ("funder", True),
    "funding_source": ("funding_source", True),
}

# Dimensions whose chart label is already the facet's accepted value.
_IDENTITY_DIMENSIONS = frozenset({"publication_form", "cost_type"})

_NO_DRILLDOWN = frozenset({"publication_type"})


@dataclass(frozen=True)
class DrilldownLinks:
    """Resolves chart rows to list URLs; the per-dimension lookup tables are
    built once per page render."""

    request: HttpRequest
    _by_name: Mapping[str, dict[str, list[str]]]

    @classmethod
    def build(cls, request: HttpRequest) -> "DrilldownLinks":
        return cls(request=request, _by_name=_lookup_tables())

    def link(self, dimension_id: str, row: GroupRow) -> str | None:
        if row.is_other or row.is_unknown or row.is_unassigned:
            return None
        if dimension_id in _NO_DRILLDOWN:
            return None
        if dimension_id == "contract":
            return self._contract_link(row.label)
        values = self._facet_values(dimension_id, row.label)
        if not values:
            return None
        param, multi = _FACETS[dimension_id]
        return self._url({param: (values, multi)})

    def _facet_values(self, dimension_id: str, label: str) -> list[str]:
        if dimension_id in _IDENTITY_DIMENSIONS:
            return [label]
        return self._by_name[dimension_id].get(label, [])

    def _contract_link(self, label: str) -> str | None:
        """A contract row is "(name) (year)"; both parts must be filters, or the
        link would widen the chart's set to every year of the contract."""
        name, _, year = label.rpartition(" (")
        if not name or not year.endswith(")"):
            return None
        pks = [str(pk) for pk in Contract.objects.filter(name=name).values_list("pk", flat=True)]
        if len(pks) != 1:
            return None
        return self._url(
            {
                "contract_name": (pks, False),
                "contract_year": ([year[:-1]], False),
            }
        )

    def _url(self, filters: Mapping[str, tuple[list[str], bool]]) -> str:
        params: QueryDict = self.request.GET.copy()
        params.pop("page", None)
        for key, (values, multi) in filters.items():
            if multi:
                existing = params.getlist(key)
                params.setlist(key, existing + [v for v in values if v not in existing])
            else:
                params.setlist(key, values)
        return build_url(_LIST_URL, params)


def _lookup_tables() -> dict[str, dict[str, list[str]]]:
    return {
        "institution": _group_pks(Institution.objects.values_list("pk", "name")),
        "journal": _group_pks(Journal.objects.values_list("pk", "title")),
        "publisher": _group_pks(Publisher.objects.values_list("pk", "name")),
        "funder": _group_pks(FundingOrganization.objects.values_list("pk", "name")),
        "funding_source": _group_pks(FundingSource.objects.values_list("pk", "name")),
        "subject_area": {
            concept.name: [str(concept.id)]
            for concept in GlobalPreferences.get_subject_classification_vocabulary().concepts
        },
        "license": {license.name: [license.value] for license in License},
        "open_access_type": {access.name: [access.value] for access in OpenAccessType},
    }


def _group_pks(rows: Iterable[tuple[int, str]]) -> dict[str, list[str]]:
    """Map each display name to every row id carrying it — a chart merges
    same-named rows, so the drill-down must select them all."""
    grouped: dict[str, list[str]] = defaultdict(list)
    for pk, name in rows:
        grouped[name].append(str(pk))
    return grouped
