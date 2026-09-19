import pytest
from rest_framework.test import APIClient

from common.throttling import HashedIPScopedRateThrottle
from platform_settings.models import FeatureFlag
from services_catalog.permissions import COMBINED_DIRECTORY_FLAG
from services_catalog.tests.factories import disable_combined_directory, make_service_category

# No autouse cache fixture here: the project-root backend/conftest.py clears the
# cache around every test in the suite (flag values and throttle counters alike).


@pytest.mark.django_db
def test_the_rollout_flag_is_seeded_enabled():
    assert FeatureFlag.objects.get(key=COMBINED_DIRECTORY_FLAG).is_enabled is True


@pytest.mark.django_db
def test_category_list_returns_only_active_categories_in_display_order():
    make_service_category(slug="zeta", name_en="Zeta", display_order=900)
    make_service_category(slug="hidden", name_en="Hidden", display_order=1, is_active=False)

    response = APIClient().get("/api/v1/service-categories/")

    assert response.status_code == 200
    slugs = [item["slug"] for item in response.data]
    assert "hidden" not in slugs
    assert slugs[0] == "full-brokerage"   # seeded, display_order 10
    assert slugs[-1] == "zeta"


@pytest.mark.django_db
def test_category_list_is_unpaginated_and_publicly_accessible():
    response = APIClient().get("/api/v1/service-categories/")

    assert response.status_code == 200
    assert isinstance(response.data, list)


@pytest.mark.django_db
def test_category_list_returns_the_requested_locale():
    response = APIClient().get("/api/v1/service-categories/", {"locale": "it"})

    legal = next(item for item in response.data if item["slug"] == "legal")
    assert legal["name"] == "Legale"


@pytest.mark.django_db
def test_category_list_falls_back_to_english_for_a_blank_translation():
    make_service_category(slug="surveying", name_en="Surveying", name_it="")

    response = APIClient().get("/api/v1/service-categories/", {"locale": "it"})

    surveying = next(item for item in response.data if item["slug"] == "surveying")
    assert surveying["name"] == "Surveying"


@pytest.mark.django_db
def test_category_list_exposes_the_seo_page_url_only_for_seo_categories():
    make_service_category(slug="surveying", name_en="Surveying")

    response = APIClient().get("/api/v1/service-categories/")
    by_slug = {item["slug"]: item for item in response.data}

    assert by_slug["legal"]["has_seo_page"] is True
    assert by_slug["legal"]["url"] == "/services/legal/"
    assert by_slug["surveying"]["has_seo_page"] is False
    assert by_slug["surveying"]["url"] is None


@pytest.mark.django_db
def test_category_detail_returns_seo_metadata():
    response = APIClient().get("/api/v1/service-categories/insurance/")

    assert response.status_code == 200
    assert response.data["slug"] == "insurance"
    assert response.data["name"] == "Insurance"
    assert response.data["seo_title"] == ""
    assert response.data["seo_description"] == ""


@pytest.mark.django_db
def test_category_detail_404s_for_unknown_and_inactive_slugs():
    make_service_category(slug="retired", name_en="Retired", is_active=False)
    client = APIClient()

    assert client.get("/api/v1/service-categories/retired/").status_code == 404
    assert client.get("/api/v1/service-categories/nope/").status_code == 404


@pytest.mark.django_db
def test_both_category_endpoints_404_when_the_rollout_flag_is_off():
    disable_combined_directory()
    client = APIClient()

    assert client.get("/api/v1/service-categories/").status_code == 404
    assert client.get("/api/v1/service-categories/legal/").status_code == 404


@pytest.mark.django_db
def test_category_list_is_rate_limited(monkeypatch):
    # Overriding settings.REST_FRAMEWORK would NOT work: DRF binds
    # SimpleRateThrottle.THROTTLE_RATES once from api_settings at import time,
    # and Django's setting_changed signal does not retroactively update that
    # already-bound dict. Monkeypatching the scope entry is the reliable way,
    # and is the pattern taxonomy/tests/test_boat_brand_search_api.py already
    # established in this repo. conftest.py has already emptied the bucket.
    monkeypatch.setitem(
        HashedIPScopedRateThrottle.THROTTLE_RATES, "services_directory", "2/min"
    )
    client = APIClient()
    client.get("/api/v1/service-categories/")
    client.get("/api/v1/service-categories/")

    assert client.get("/api/v1/service-categories/").status_code == 429


@pytest.mark.django_db
def test_two_visitors_behind_the_shared_next_js_server_get_independent_budgets(
    monkeypatch, settings
):
    # Regression test for the SSR throttle-sharing gap: two different SSR page
    # loads from the same Next.js server (same REMOTE_ADDR as far as Django is
    # concerned) must not share one throttle budget once each carries its own
    # visitor's forwarded IP.
    monkeypatch.setitem(
        HashedIPScopedRateThrottle.THROTTLE_RATES, "services_directory", "1/min"
    )
    settings.INTERNAL_SERVICE_SECRET = "test-internal-secret"
    client = APIClient()
    secret_header = {"HTTP_X_INTERNAL_SERVICE_SECRET": "test-internal-secret"}

    first_visitor = client.get(
        "/api/v1/service-categories/", **secret_header, HTTP_X_INTERNAL_CLIENT_IP="198.51.100.1"
    )
    second_visitor = client.get(
        "/api/v1/service-categories/", **secret_header, HTTP_X_INTERNAL_CLIENT_IP="198.51.100.2"
    )
    first_visitor_again = client.get(
        "/api/v1/service-categories/", **secret_header, HTTP_X_INTERNAL_CLIENT_IP="198.51.100.1"
    )

    assert first_visitor.status_code == 200
    assert second_visitor.status_code == 200
    assert first_visitor_again.status_code == 429
