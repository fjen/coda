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
};

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => renderCharts(document));
} else {
    renderCharts(document);
}

document.addEventListener("htmx:afterSwap", (event) => renderCharts(event.target));
