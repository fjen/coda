# Dashboard Design Ideas — Reporting / Funding Request Statistics

Status: proposal. Nothing here is implemented; this file records the design direction discussed
2026-10-15 so it can be picked up item by item. Every item is independent; the batches at the end
group the ones that belong together.

Baseline (audited 2026-10-15): 13 sections on one scroll, 4 KPI cards, per-section figure above a
full exact-values table, Pico card styling, filter rail on the left.

## 1. Problems with the current design

1. **One endless scroll of 13 equal-weight sections.** Nothing signals hierarchy — "Institution
   hierarchy" (the richest view) looks identical to "License". A user cannot see at a glance which
   dimensions exist.
2. **Chart and table duplicate the same numbers.** Each section shows a figure, then a table of
   exactly the same values. The table wins for exactness, the chart for shape — they should
   cooperate, not stack. This is the bulk of the page's ~10,000 px height.
3. **The headline is static.** Four counters, no comparisons: no share of total, no period context,
   no per-request average (1.53 M€ / 2,584 = 590 € — often the most decision-relevant number, and
   it is missing).
4. **Tables are dense but not scannable.** Left-aligned numbers, exact cents everywhere
   ("157532.74 €") although the chart beside it says "158 k€".
5. **Unequal visual rhythm.** Treemap 480 px, dual-measure bars ~480 px + table, single-measure
   sections half-height — sections have unequal mass and dead space between chart and table.
6. **No facet navigation.** The filter rail filters *data*; nothing jumps to a *dimension group*.
   Thirteen `h3`s with no table of contents on a page this long is a navigation gap.
7. **Section headers are bare.** Once scrolled past, a header tells nothing about its section.

## 2. Proposed changes

### 2.1 Grouped dimension chips (jump nav) — effort S

A sticky chip row under the headline — but not one chip per dimension: twelve chips would be the
table of contents the page already fails to be. The dimensions group into four coherent views, one
chip per group; clicking a chip scrolls to the group's first section.

| Group | Chip label | Sections |
| --- | --- | --- |
| Publication | Publication | Subject area · Publication type · Publication form · License · Open access type |
| Venues | Venues | Journal · Publisher |
| Cost & contracts | Cost | Cost type · Contract · Funding source |
| Attribution | Attribution | Institution hierarchy (treemap) · Institution (corresponding author) · Funder |

Rationale: "Publication" collects the five attributes describing what was published (all
single-valued, both measures); "Venues" separates the outlet dimensions that publisher-level
reporting questions (deals, negotiations) live in; "Cost & contracts" is the finance view
(spend split, agreement attribution); "Attribution" isolates the repeated dimensions that
attribute a request to an external party — the two facets with an Unknown/unattributed caveat,
so the coverage note from 2.5 reads naturally there.

Within a group the page still renders one section per dimension; the group is a navigation and
layout unit only. The chip of the group currently in view is highlighted (IntersectionObserver
in `reporting.js`).

### 2.2 Merge chart and table into one unit — decided: stacked with collapse

Settled 2026-10-21 in the prototype: the chart stays stacked above the table, and the table
collapses into an "Exact values (N rows)" `<details>` carrying the full-precision values. The
side-by-side chart/table split from the original sketch is rejected — the collapse already
removed the duplication cost, and stacked sections survive narrow viewports without a second
breakpoint. The spec's remaining table rules (2.3) are implemented: right-aligned tabular
numerals, compact money with cents in the tooltip, and a CSS share bar under each measure column.

### 2.3 Right-align and compact tables — effort S

Standalone version of 2.2's table rules, if 2.2 is deferred: `text-align: right` on measure
columns, `font-variant-numeric: tabular-nums`, compact money with cents in the tooltip.

### 2.4 Enrich the headline — effort M

Keep the four cards, add: **Ø spend per request**, **Top-5 share** (concentration: the five largest
rows' spend as a share of the total). Period deltas on publications and spend, coloured
success/warning, belong to the comparison toggle (2.8) — they are not permanently on the page.
Needs a small `Headline` dto extension (`avg_per_request`, `top5_share`, optional
`delta_publications` / `delta_spend`).

### 2.5 Section headers carry coverage and value count — effort S

The global totals (2,584 pubs · 1.53 M€) are identical in every section — each section aggregates
the same request set by a different key — so a header repeating them says nothing. What differs per
section is its internal shape. Start with the cheap, unambiguous pair:

- **value count**: how many distinct values the facet produced, "Other" fold included —
  "Publisher — 11 values" vs "License — 7 values";
- **coverage**: how much of the request set the facet can attribute —
  "covers 2,584 of 2,584 requests" vs "Institution (CA) — covers 2,098 of 2,584; 486 unattributed".

The coverage line doubles as a data-quality flag: a facet that leaves requests unattributed (no
corresponding-author affiliation, no publication form, unknown license) shows the gap in its own
header instead of hiding it in an "Unknown" row.

Data source: already available per `Grouping` — `len(rows)` minus the fold for the value count;
the unattributed count is the requests that landed in the `Unknown`/`FORM_UNKNOWN`-class row. No
new queries; a small `DimensionSection` dto extension. A later iteration may add the dominant
share ("Elsevier 20% of spend") — deliberately deferred: for non-additive measures the spend share
is the double-counted number, which would need a per-measure decision first.

### 2.6 Grouped section layout — decided: single column

Settled 2026-10-21 in the prototype: sections stack in one column at every width — the
two-column grid was implemented and reverted (charts need the full width to stay readable;
half-width figures squeeze the category labels). The grouping from 2.1 remains: a group's
sections sit together under a group sub-heading, and the institution hierarchy treemap opens
the "Attribution" group, full-width, before its two chip sections.

### 2.7 Sticky active-filter chip row — effort M

The rail already computes removable filter chips (`build_filter_summary`). Duplicate that chip row
sticky above the sections (below the dimension chips) so the active filters stay visible after
scrolling. Read-only duplicates; removal links keep working (they re-point at the page URL).

### 2.8 Filters in a drawer on all viewports — effort S

The filter rail currently renders inline beside the content on viewports ≥ 1400px and as a
slide-in drawer (opened by the toolbar's "Filters" button) below that. Drop the inline mode: the
drawer becomes the only presentation, at every width.

The machinery already exists and is viewport-agnostic — `partials/filter_drawer.html` renders the
rail as a non-modal `<dialog>`, `filter-drawer.js` toggles modal/non-modal on the media query, and
`filter-sidebar.css` only hides the toggle button and pins the static layout above 1400px. The
change is confined to CSS and one media query in the JS:

- delete the `position: static` flex-row mode and the ≥ 1400px blocks in `filter-sidebar.css`
  (sidebar, toggle, close-button visibility);
- always `showModal()` the dialog from the "Filters" button; close on apply, on backdrop click,
  and on `Esc` (the existing modal-close path);
- keep the active-filter count on the toggle button (`filter_toolbar_count.html`) so the closed
  state still communicates what is active — paired with 2.7's sticky chip row, the closed drawer
  loses nothing.

This frees the full content width on wide screens (the statistics grid in 2.6 gets ~300px back)
and unifies the filter interaction across every page that shares the rail. The list pages
(funding requests, invoices) inherit the change — verify their layouts don't depend on the
sidebar column.

**Exception: the period.** The date range is not a filter like the others — it defines what the
page is about (the request-date period, ADR-0002) and is the one control every user touches. It
stays out of the drawer, rendered in the toolbar right after the search input (a new
`filter_toolbar_period_template` include slot beside `filter_toolbar_extra_template`, or fixed
markup in `filter_toolbar.html` bound to `filter_form.date_range`). The drawer's copy of the two
date fields is removed so the values live in exactly one place; `hx-include` already pulls both
forms, so no wiring changes. The date error (`filter_date_error.html`) renders in the toolbar
too — visible without opening anything.

**Period comparison toggle.** Beside the period fields, a switch ("compare with previous
period") — off by default, remembered in the URL (`compare=1`), so it survives drill-down links
and shares. On, it extends every number with the previous period of the same length: the KPI
cards show deltas (the 2.4 deltas become real — they need this toggle, not a permanent second
fetch), each section's table gains a delta column (▲/▼, coloured success/warning), and the bars
figures render a muted companion bar per row for the previous period. Off, nothing changes
visually and no second query runs.

Mechanics: the toggle only re-issues the page URL with `compare=1` — the view then fetches the
preceding window (`end − length … end`) through the same `fetch_requests` and labels it the
comparison set. Sections whose comparison set is empty show "no data in the previous period"
instead of zeros. Non-additive measures (Institution, Funder) compare publications only — spend
deltas would compare double-counted numbers. The URL carries the whole comparison state, so the
region swap, the chip row (2.1), and the section links all keep it with the rest of the filter
set; nothing is stored server-side.

## 3. Layout sketch

```
┌─ headline ──────────────────────────────────────────────────┐
│ KPI cards: pubs ▲Δ · spend ▲Δ · Ø/request · top-5 share ·   │
│ no-invoice count                                            │
├─ group chip row (sticky): Publication · Venues · Cost ·     │
│    Attribution                                ← 2.1         │
├─ [search ________] [start 2000-01-01 · end 2030-12-31]     │
│    [⇄ compare] [Filters (n)]                  ← 2.8        │
│    sticky filter chip row when filters active (2.7) ────────┤
├─ GROUP: Publication ────────────────────────────────────────┤
│ ┌─ Subject area ──────┐ ┌─ Publication type ────────────┐ │
│ │ chart + table (2.2) │ │ …                             │ │
│ └─────────────────────┘ └───────────────────────────────┘ │
│ ┌─ Publication form ──┐ ┌─ License ─────────────────────┐ │
│ └─────────────────────┘ └───────────────────────────────┘ │
│ ┌─ Open access type ──┐                                   │
├─ GROUP: Venues ─────────────────────────────────────────────┤
│ ┌─ Journal ───────────┐ ┌─ Publisher ───────────────────┐ │
├─ GROUP: Cost & contracts ───────────────────────────────────┤
│ ┌─ Cost type ─────────┐ ┌─ Contract ────────────────────┐ │
│ └─────────────────────┘ └───────────────────────────────┘ │
│ ┌─ Funding source ────┐                                   │
├─ GROUP: Attribution ────────────────────────────────────────┤
│ ┌─ Institution hierarchy treemap (full width) ───────────┐ │
│ └────────────────────────────────────────────────────────┘ │
│ ┌─ Institution (CA) ──┐ ┌─ Funder ──────────────────────┐ │
└─────────────────────────────────────────────────────────────┘
```

A rendered wireframe of the pre-grouping layout lives beside this file (`../prototypes/` served
from the session artifacts, `local://reporting-redesign.svg` in the 2026-10-15 session); its
12-chip row is superseded by the four group chips above.

## 4. Suggested batches

| Batch | Items | Theme |
| --- | --- | --- |
| Tables first | 2.2 + 2.3 + 2.5 | Biggest page shrink; template/CSS plus a small `DimensionSection` dto extension for 2.5 |
| Navigation | 2.1 + 2.6 + 2.7 + 2.8 | Discoverability and long-page usability; 2.8 touches the shared filter rail (list pages inherit it) |
| Headline | 2.4 + comparison toggle (in 2.8) | Needs the `Headline` dto extension; the toggle fetches the prior period through the same `fetch_requests` |

Each batch is independently shippable.
