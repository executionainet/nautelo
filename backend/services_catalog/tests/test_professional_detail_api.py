import pytest
from rest_framework.test import APIClient

from accounts.enums import UserRole
from accounts.tests.factories import make_user
from professionals.enums import ProfessionalProfileStatus
from professionals.tests.factories import make_professional
from services_catalog.tests.factories import (
    disable_combined_directory,
    make_professional_service,
    make_service_category,
)

# No autouse cache fixture here: the project-root backend/conftest.py clears the
# whole cache around every test in the suite — both the feature-flag value and
# the shared `services_directory` throttle bucket, which these API files would
# otherwise exhaust between them.
#
# Category slugs below carry a `-test` suffix because migration
# 0002_seed_seo_service_categories already seeds the real `legal` / `insurance`
# rows, and ServiceCategory.slug is unique.


def build_professional(
    email, *, slug, display_name, status=ProfessionalProfileStatus.ACTIVE, **extra
):
    return make_professional(
        make_user(email, role=UserRole.SERVICE_PROVIDER),
        slug=slug,
        display_name=display_name,
        status=status,
        **extra,
    )


@pytest.mark.django_db
def test_detail_returns_the_profile_and_its_active_services():
    legal = make_service_category(slug="legal-test", name_en="Legal", name_it="Legale")
    pro = build_professional(
        "d@example.com",
        slug="ocean-legal",
        display_name="Ocean Legal",
        short_description="Maritime contracts",
        description="Twenty years of maritime contract work.",
    )
    make_professional_service(
        pro, legal, title_en="Sale contracts", title_it="Contratti di vendita"
    )
    make_professional_service(pro, legal, title_en="Retired service", is_active=False)

    response = APIClient().get("/api/v1/professionals/ocean-legal/", {"locale": "it"})

    assert response.status_code == 200
    assert response.data["slug"] == "ocean-legal"
    assert response.data["description"] == "Twenty years of maritime contract work."
    assert [s["title"] for s in response.data["services"]] == ["Contratti di vendita"]
    assert response.data["services"][0]["category"] == {"slug": "legal-test", "name": "Legale"}


@pytest.mark.django_db
def test_detail_never_contains_contact_details():
    build_professional("c@example.com", slug="contact-pro", display_name="Contact Pro")

    response = APIClient().get("/api/v1/professionals/contact-pro/")

    # Assert the success first: a 404 envelope also lacks these three keys, so
    # without this line the test would keep passing if the endpoint regressed
    # to never returning a profile at all, silently losing its coverage.
    assert response.status_code == 200
    data = response.data

    assert "public_email" not in data
    assert "public_phone" not in data
    assert "website_url" not in data


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status",
    [
        ProfessionalProfileStatus.DRAFT,
        ProfessionalProfileStatus.PENDING,
        ProfessionalProfileStatus.SUSPENDED,
    ],
)
def test_detail_404s_for_every_non_active_status(status):
    build_professional("h@example.com", slug="hidden-pro", display_name="Hidden Pro", status=status)

    assert APIClient().get("/api/v1/professionals/hidden-pro/").status_code == 404


@pytest.mark.django_db
def test_detail_404s_for_an_unknown_slug():
    assert APIClient().get("/api/v1/professionals/nobody/").status_code == 404


@pytest.mark.django_db
def test_related_professionals_share_a_category_and_exclude_the_current_profile():
    legal = make_service_category(slug="legal-test", name_en="Legal")
    insurance = make_service_category(slug="insurance-test", name_en="Insurance")
    subject = build_professional("s@example.com", slug="subject", display_name="Subject")
    peer = build_professional("p@example.com", slug="peer", display_name="Peer")
    stranger = build_professional("t@example.com", slug="stranger", display_name="Stranger")
    make_professional_service(subject, legal, title_en="A")
    make_professional_service(peer, legal, title_en="B")
    make_professional_service(stranger, insurance, title_en="C")

    related = APIClient().get("/api/v1/professionals/subject/").data["related"]

    assert [item["slug"] for item in related] == ["peer"]
    assert related[0]["url"] == "/services/professionals/peer/"


@pytest.mark.django_db
def test_related_professionals_are_capped_at_four():
    legal = make_service_category(slug="legal-test", name_en="Legal")
    subject = build_professional("s@example.com", slug="subject", display_name="Subject")
    make_professional_service(subject, legal, title_en="A")
    for index in range(6):
        peer = build_professional(
            f"r{index}@example.com", slug=f"peer-{index}", display_name=f"Peer {index}"
        )
        make_professional_service(peer, legal, title_en=f"Service {index}")

    related = APIClient().get("/api/v1/professionals/subject/").data["related"]

    assert len(related) == 4
    assert [item["slug"] for item in related] == ["peer-0", "peer-1", "peer-2", "peer-3"]


@pytest.mark.django_db
def test_related_professionals_sharing_multiple_categories_are_not_duplicated():
    # Regression test for the same double-count/duplicate-row trap Task 7 had
    # to guard against for active_service_count: a peer who shares TWO
    # categories with the subject joins the `related` filter's
    # services__category_id__in=... condition twice (once per matching
    # service row). Without the queryset-level .distinct() in get_related,
    # that peer would appear twice in the `related` list and would also count
    # twice against RELATED_PROFESSIONAL_LIMIT. It must appear exactly once.
    legal = make_service_category(slug="legal-test", name_en="Legal")
    insurance = make_service_category(slug="insurance-test", name_en="Insurance")
    subject = build_professional("s@example.com", slug="subject", display_name="Subject")
    dual_peer = build_professional("d@example.com", slug="dual-peer", display_name="Dual Peer")
    make_professional_service(subject, legal, title_en="A")
    make_professional_service(subject, insurance, title_en="B")
    make_professional_service(dual_peer, legal, title_en="C")
    make_professional_service(dual_peer, insurance, title_en="D")

    related = APIClient().get("/api/v1/professionals/subject/").data["related"]

    assert [item["slug"] for item in related] == ["dual-peer"]


@pytest.mark.django_db
def test_related_professionals_exclude_peers_whose_shared_category_is_inactive():
    # get_categories and get_services both skip a service whose category has
    # been deactivated; get_related must agree. A peer reachable only through
    # a deactivated category is unreachable everywhere else on the site — the
    # grid does not offer that category and ?category= does not match it — so
    # surfacing it here would be a dead end the visitor cannot retrace.
    legal = make_service_category(slug="legal-test", name_en="Legal")
    retired = make_service_category(slug="retired-test", name_en="Retired", is_active=False)
    subject = build_professional("s@example.com", slug="subject", display_name="Subject")
    visible_peer = build_professional("v@example.com", slug="visible-peer", display_name="Alpha")
    hidden_peer = build_professional("x@example.com", slug="hidden-peer", display_name="Beta")
    make_professional_service(subject, legal, title_en="A")
    make_professional_service(subject, retired, title_en="B")
    make_professional_service(visible_peer, legal, title_en="C")
    make_professional_service(hidden_peer, retired, title_en="D")

    response = APIClient().get("/api/v1/professionals/subject/")

    assert response.status_code == 200
    assert [item["slug"] for item in response.data["related"]] == ["visible-peer"]


@pytest.mark.django_db
def test_a_professional_with_no_services_has_no_related_professionals():
    build_professional("l@example.com", slug="lonely", display_name="Lonely")

    assert APIClient().get("/api/v1/professionals/lonely/").data["related"] == []


@pytest.mark.django_db
def test_detail_404s_when_the_rollout_flag_is_off():
    build_professional("f@example.com", slug="flagged", display_name="Flagged")
    disable_combined_directory()

    assert APIClient().get("/api/v1/professionals/flagged/").status_code == 404
