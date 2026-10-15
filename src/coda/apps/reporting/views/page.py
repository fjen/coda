"""The statistics page and its HTMX list region (plan §3, §4, §8.5, §9).

``reporting_page`` answers, for the filtered set of funding requests: headline
row, then one section per §7 dimension with a plotly figure (json_script +
``reporting.js``), a table of exact values and drill-down links back into the
funding request list. The filter rail, chips and region mechanics are the
funding request list's own — reused through ``partials/filter_layout.html``.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, QueryDict
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.contracts.models import Contract
from coda.apps.fundingrequests.forms import (
    FundingRequestListFilterForm,
    parse_label_ids,
)
from coda.apps.fundingrequests.models import Label
from coda.apps.institutions.models import Institution
from coda.apps.invoices.models import Invoice
from coda.apps.listfilters import ListRegionMixin, build_filter_summary, build_url
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.reporting import queries
from coda.apps.reporting.dataset import build_facts
from coda.apps.reporting.drilldown import DrilldownLinks, list_view_url
from coda.apps.reporting.treemap import institution_treemap
from coda.contexts.statistics import charts
from coda.contexts.statistics.dimensions import DIMENSIONS
from coda.contexts.statistics.dto import (
    ChartKind,
    ChartSpec,
    Measure,
    RequestFact,
    StatisticsReport,
)

_PAGE_URL = "reporting:stats_fundingrequests"
_REGION_URL = "reporting:stats_fundingrequests_region"
_REGION_ELEMENT_ID = "reporting-region"

# A plotly horizontal bar band needs roughly this much vertical space; the
# table under the chart carries the exact values regardless.
_CHART_ROW_PX = 28
_CHART_BASE_PX = 60


@dataclass(frozen=True)
class DimensionRow:
    """One row of a dimension's shared exact-value table; ``link`` filters the
    statistics page to the row's set (toggle off when already active), None
    when it cannot be expressed as list filters (Other/Unknown/Unassigned)."""

    label: str
    publications: int
    amount: Decimal | None
    link: str | None
    is_other: bool = False


@dataclass(frozen=True)
class MeasureColumn:
    """One value column of the shared table, with its total — or the ADR-0007
    note where the measure is non-additive and no total may be shown."""

    measure: Measure
    label: str
    total: Decimal | int | None
    note: str | None


@dataclass(frozen=True)
class IncompleteInvoice:
    """An invoice whose positions lacked a rate into the report currency; the
    currency-incomplete notice links to each one (plan §9, §10)."""

    pk: int
    number: str


@dataclass(frozen=True)
class ChartPanel:
    """One dimension's figure for ``reporting.js``: one dot per entity,
    publications on x, spend on y."""

    data_id: str
    title: str
    figure: dict[str, Any]


@dataclass(frozen=True)
class DimensionSection:
    """One section of the page: a dimension, its combined figure and one
    count-plus-spend table for the whole facet."""

    dimension_id: str
    label: str
    chart: ChartPanel
    rows: tuple[DimensionRow, ...]
    columns: tuple[MeasureColumn, ...]


@login_required
@breadcrumb("Funding Request Statistics", parent_url_name="reporting:home")
def reporting_page(request: HttpRequest) -> HttpResponse:
    """The page itself; a bare GET first gets the default period in its URL
    (§8.5), so the effective period is visible everywhere, drill-downs included."""
    if not request.GET.get("start_date") and not request.GET.get("end_date"):
        return redirect(_default_period_url(request))
    return render(request, "reporting/reporting.html", reporting_context(request))


class ReportingRegionView(ListRegionMixin, TemplateView):
    """The filter-driven region: sections re-render on every sidebar change,
    and the sidebar itself swaps back out of band so its widgets keep the
    server-owned state (same mechanics as the funding request list)."""

    template_name = "reporting/partials/reporting_region.html"
    list_url_name = _PAGE_URL

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | reporting_context(self.request)


reporting_region = ReportingRegionView.as_view()


def reporting_context(request: HttpRequest) -> dict[str, Any]:
    """The whole page context: filtered facts -> report -> sections, plus the
    shared rail's form/chips state."""
    labels = list(Label.objects.all().order_by("name"))
    contracts = list(Contract.objects.all())
    vocabularies = GlobalPreferences.preloaded()
    filter_form = FundingRequestListFilterForm(
        request.GET, contracts=contracts, labels=labels, vocabularies=vocabularies
    )
    criteria, _sort_order = filter_form.search_criteria()
    facts = build_facts(queries.fetch_requests(criteria), GlobalPreferences.get_home_currency())
    try:
        kind = ChartKind(request.GET.get("chart", ChartKind.SCATTER))
    except ValueError:
        kind = ChartKind.SCATTER
    report = charts.report(facts, DIMENSIONS, kind=kind)

    date_errors = filter_form.errors.get("date_range")
    summary = build_filter_summary(
        request,
        labels,
        contracts,
        list_url_name=_PAGE_URL,
        region_url_name=_REGION_URL,
        included=filter_form.selected_label_ids,
        excluded=filter_form.excluded_label_ids,
        date_range=filter_form.cleaned_data.get("date_range"),
        date_range_error=str(date_errors[0]) if date_errors else None,
    )

    return {
        "filter_form": filter_form,
        "labels": labels,
        "contract_list": contracts,
        "label_state": sorted(parse_label_ids(request.GET.getlist("labels"))),
        "active_filters": summary.chips,
        "filter_count": summary.count,
        "filter_errors": summary.errors,
        "filter_clear_url": reverse(_PAGE_URL),
        "filter_list_id": _REGION_ELEMENT_ID,
        "list_view_url": list_view_url(request),
        "chart_kind": kind,
        "chart_kinds": list(ChartKind),
        "chart_switch_urls": {
            candidate: _chart_switch_url(request, candidate) for candidate in ChartKind
        },
        "headline": report.headline,
        "incomplete_invoices": _incomplete_invoices(facts),
        "sections": _sections(
            report,
            DrilldownLinks.build(request, region_url_name=_REGION_URL, vocabularies=vocabularies),
        ),
        "institution_treemap": institution_treemap(facts, Institution.objects.all()),
    }


def _chart_switch_url(request: HttpRequest, kind: ChartKind) -> str:
    """The page URL with only the chart param swapped — filters preserved."""
    params: QueryDict = request.GET.copy()
    params["chart"] = kind
    return build_url(_PAGE_URL, params)


def _default_period_url(request: HttpRequest) -> str:
    """Same URL, current calendar year as the period (§8.5): the redirect makes
    the effective period visible in the URL and in every drill-down link."""
    year = timezone.localdate().year
    params = request.GET.copy()
    params.pop("page", None)
    params["start_date"] = date(year, 1, 1).isoformat()
    params["end_date"] = date(year, 12, 31).isoformat()
    return build_url(_PAGE_URL, params)


def _sections(report: StatisticsReport, links: DrilldownLinks) -> list[DimensionSection]:
    """Figure and shared table under their dimension, in registry order;
    dimensions without a non-empty grouping do not get an empty section."""
    specs = {spec.dimension_id: spec for spec in report.charts}
    sections: list[DimensionSection] = []
    for dimension in DIMENSIONS:
        spec = specs.get(dimension.id)
        if spec is None:
            continue
        rows = tuple(
            DimensionRow(
                label=row.label,
                publications=row.publications,
                amount=row.amount,
                link=links.link(dimension.id, row),
                is_other=row.is_other,
            )
            for row in spec.rows
        )
        sections.append(
            DimensionSection(
                dimension_id=dimension.id,
                label=dimension.label,
                chart=_panel(spec),
                rows=rows,
                columns=tuple(
                    MeasureColumn(
                        measure=column.measure,
                        label=charts.MEASURE_LABELS[column.measure],
                        total=column.total,
                        note=column.note,
                    )
                    for column in spec.columns
                ),
            )
        )
    return sections


def _panel(spec: ChartSpec) -> ChartPanel:
    return ChartPanel(
        data_id=f"chart-{spec.dimension_id}",
        title=spec.title,
        figure=_figure_with_height(spec),
    )


def _figure_with_height(spec: ChartSpec) -> dict[str, Any]:
    """Size figures that don't carry their own height (scatter, pies): one
    bar band per row — the container has no intrinsic height, and Plotly
    honors an explicit layout height. The bars figure sets a fixed height
    itself, so its layout wins here."""
    figure = spec.figure
    if figure.get("layout", {}).get("height") is not None:
        return figure
    layout = {
        **figure.get("layout", {}),
        "height": _CHART_BASE_PX + _CHART_ROW_PX * len(spec.rows),
    }
    return {**figure, "layout": layout}


def _incomplete_invoices(facts: Sequence[RequestFact]) -> tuple[IncompleteInvoice, ...]:
    """The invoices behind the excluded amounts, deduplicated and ordered —
    the notice names the affected requests' invoices, not just their count."""
    ids = {invoice_id for fact in facts for invoice_id in fact.unconvertible_invoice_ids}
    if not ids:
        return ()
    return tuple(
        IncompleteInvoice(pk=invoice.pk, number=invoice.number)
        for invoice in Invoice.objects.filter(pk__in=ids).order_by("number")
    )
