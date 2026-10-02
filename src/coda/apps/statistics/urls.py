from django.urls import path

from coda.apps.statistics.views.page import statistics_page, statistics_region

app_name = "statistics"

urlpatterns = [
    path("", statistics_page, name="page"),
    path("region/", statistics_region, name="region"),
]
