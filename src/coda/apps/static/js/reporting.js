// Renders the server-built plotly figures of the statistics page (plan §9).
// Each [data-chart] mount names the json_script carrying the figure — the exact
// {data, layout, config} object Plotly.newPlot consumes. No inline JS, no
// escaping work here: the template owns the payloads, this file only paints.
// Runs on first load and after every htmx swap of the statistics region, so a
// filter change re-paints the freshly swapped charts.
const renderChart = (element) => {
    const source = document.getElementById(element.dataset.chart);
    if (!source || element.dataset.plotlyRendered === "true") {
        return;
    }
    const figure = JSON.parse(source.textContent);
    const config = Object.assign({ responsive: true }, figure.config);
    element.dataset.plotlyRendered = "true";
    Plotly.newPlot(element, figure.data, figure.layout, config);
};

const renderCharts = (root) => {
    root.querySelectorAll("[data-chart]").forEach(renderChart);
    // Share bars: the template carries the permille share as data; CSS paints it.
    root.querySelectorAll(".statistics-share[data-share]").forEach((bar) => {
        bar.style.setProperty("--share", bar.dataset.share);
    });
};

// The sticky chip row (2.7) sits outside the swapped region, so a filter
// change leaves it stale. The rail's chips re-render out of band with the
// region — copy them over after every swap.
const syncStickyFilters = () => {
    const sticky = document.querySelector(".statistics-active-filters");
    const source = document.querySelector(".filter-sidebar .active-filters");
    if (!sticky || !source) {
        return;
    }
    sticky.innerHTML = "";
    sticky.append(
        ...[...source.querySelectorAll(".active-filter")].map((chip) => chip.cloneNode(true)),
    );
    // The clones are unknown to htmx — re-process so their remove links swap
    // the region instead of navigating.
    window.htmx?.process(sticky);
};

// The region can accumulate overlapping requests when a second filter
// change fires while the first is still in flight (two quick date edits).
// Responses may then land out of order and the chips render the stale
// request's state. htmx 2 has no public abort; drop stale responses
// instead: each request carries its issue order, and a settle from an
// older request than the last issued one is ignored.
let _regionRequestSeq = 0;
document.addEventListener("htmx:beforeRequest", (event) => {
    if (event.target.id === "reporting-region") {
        event.detail.xhr._regionSeq = ++_regionRequestSeq;
    }
});
document.addEventListener("htmx:beforeSwap", (event) => {
    if (event.target.id === "reporting-region") {
        const issued = Number(event.detail.xhr?._regionSeq ?? 0);
        if (issued < _regionRequestSeq) {
            event.detail.shouldSwap = false;
        }
    }
});

// The tab nav sits outside the swapped region: after every swap, mark the
// tab whose `tab` param matches the current URL as current.
const syncTabState = () => {
    const params = new URLSearchParams(window.location.search);
    const active = params.get("tab") ?? "overview";
    document
        .querySelectorAll('.statistics-groups [role="group"] a[role="button"]')
        .forEach((tab) => {
            const href = new URL(tab.href, window.location.origin);
            const tabValue = href.searchParams.get("tab") ?? "groups";
            if (tabValue === active) {
                tab.setAttribute("aria-current", "true");
            } else {
                tab.removeAttribute("aria-current");
            }
        });
};

document.addEventListener("htmx:afterSettle", (event) => {
    renderCharts(event.target);
    makeHeadersActionable(event.target);
    // afterSettle, not afterSwap: the sidebar's fresh chips arrive in the
    // same exchange as the region, often settled after it.
    syncStickyFilters();
    syncTabState();
});

syncTabState();

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => renderCharts(document));
} else {
    renderCharts(document);
}

// Exact-value tables sort client-side: click (or Enter/Space on) a column
// header. Interaction is delegated to the document, so tables htmx swaps in
// are sortable without re-initialisation; only header affordances (tabindex,
// title) are applied per swap. The "Other" fold row aggregates the tail and
// stays last under any order; ties keep the server's spend-led ranking
// (Array.sort is stable).
const SORTABLE_TABLE = "table.statistics-values";

const cellValue = (cell) => {
    const text = (cell.textContent || "").replace(/\s+/g, " ").trim();
    if (text === "—" || text === "") {
        return 0; // paid out nothing sorts as zero
    }
    const numeric = Number(text.replace(/[€,\s]/g, ""));
    return Number.isNaN(numeric) ? text : numeric;
};

const sortRows = (table, columnIndex, ascending) => {
    const body = table.tBodies[0];
    const folds = [...body.rows].filter((row) => row.classList.contains("statistics-aggregate"));
    const entities = [...body.rows].filter((row) => !folds.includes(row));
    entities.sort((left, right) => {
        const a = cellValue(left.cells[columnIndex]);
        const b = cellValue(right.cells[columnIndex]);
        const order =
            typeof a === "number" && typeof b === "number"
                ? a - b
                : String(a).localeCompare(String(b));
        return ascending ? order : -order;
    });
    for (const row of entities.concat(folds)) {
        body.appendChild(row);
    }
};

const sortByHeader = (header) => {
    const table = header.closest(SORTABLE_TABLE);
    const index = header.cellIndex;
    const isFirstClick = table.dataset.sortColumn !== String(index);
    // Value columns (numbers) invite largest-first; the label column A→Z.
    const ascending = isFirstClick ? index === 0 : table.dataset.sortDirection === "descending";
    table.dataset.sortColumn = String(index);
    table.dataset.sortDirection = ascending ? "ascending" : "descending";
    table.querySelectorAll("thead th").forEach((th) => {
        th.setAttribute("aria-sort", th === header ? (ascending ? "ascending" : "descending") : "none");
    });
    sortRows(table, index, ascending);
};

const actionableHeader = (target) =>
    target instanceof Element ? target.closest(`${SORTABLE_TABLE} thead th`) : null;

document.addEventListener("click", (event) => {
    const header = actionableHeader(event.target);
    if (header) {
        sortByHeader(header);
    }
});

document.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") {
        return;
    }
    const header = actionableHeader(event.target);
    if (header) {
        event.preventDefault();
        sortByHeader(header);
    }
});

function makeHeadersActionable(root) {
    const headers =
        root instanceof HTMLTableElement
            ? root.querySelectorAll("thead th")
            : root.querySelectorAll(`${SORTABLE_TABLE} thead th`);
    // No role="button" — it would override the native columnheader role
    // (a11y.md #2) and pull in Pico's blue button background. tabindex plus
    // the Enter/Space keydown handler and aria-sort are the whole pattern.
    headers.forEach((header) => {
        header.tabIndex = 0;
        header.title = "Sort by this column";
    });
}

makeHeadersActionable(document);
