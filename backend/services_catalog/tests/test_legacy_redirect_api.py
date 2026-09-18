import pytest
from rest_framework.test import APIClient

from accounts.enums import UserRole
from accounts.tests.factories import make_user
from professionals.enums import ProfessionalProfileStatus
from professionals.tests.factories import make_professional
from services_catalog.models import LegacyDirectoryMapping
from services_catalog.tests.factories import disable_combined_directory, make_legacy_mapping

ENDPOINT = "/api/v1/legacy/professional-redirect/"

# No autouse cache fixture here: the project-root backend/conftest.py clears the
# whole cache around every test in the suite — both the feature-flag value and
# the shared `services_directory` throttle bucket, which these API files would
# otherwise exhaust between them.


def build_professional(email, *, slug, status=ProfessionalProfileStatus.ACTIVE):
    return make_professional(
        make_user(email, role=UserRole.SERVICE_PROVIDER),
        slug=slug,
        display_name=slug.replace("-", " ").title(),
        status=status,
    )


@pytest.mark.django_db
def test_the_mapping_table_starts_empty():
    assert LegacyDirectoryMapping.objects.count() == 0


@pytest.mark.django_db
def test_a_mapped_legacy_id_resolves_to_the_canonical_url():
    pro = build_professional("m@example.com", slug="ocean-legal")
    make_legacy_mapping(legacy_identifier="4821", target=pro)

    response = APIClient().get(ENDPOINT, {"id": "4821"})

    assert response.status_code == 200
    assert response.data["url"] == "/services/professionals/ocean-legal/"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "resolution",
    [
        LegacyDirectoryMapping.Resolution.DUPLICATE_REVIEW,
        LegacyDirectoryMapping.Resolution.PENDING,
        LegacyDirectoryMapping.Resolution.UNRESOLVED,
    ],
)
def test_an_unmapped_row_does_not_resolve(resolution):
    """Only MAPPED is a decided answer; every other resolution is still an open
    question and must not redirect anyone anywhere (spec §14.3 step 2)."""
    pro = build_professional("p@example.com", slug="pending-map")
    make_legacy_mapping(legacy_identifier="9001", target=pro, resolution=resolution)

    assert APIClient().get(ENDPOINT, {"id": "9001"}).status_code == 404


@pytest.mark.django_db
def test_a_service_kind_row_does_not_resolve_a_professional():
    """The professional resolver reads PROVIDER rows only — a legacy *service*
    record sharing an identifier must not redirect to a professional page."""
    pro = build_professional("k@example.com", slug="kind-pro")
    make_legacy_mapping(
        legacy_identifier="3300",
        target=pro,
        legacy_kind=LegacyDirectoryMapping.LegacyKind.SERVICE,
    )

    assert APIClient().get(ENDPOINT, {"id": "3300"}).status_code == 404


@pytest.mark.django_db
def test_a_category_targeted_row_does_not_resolve_a_professional():
    """A MAPPED row pointing at a SERVICE_CATEGORY must not be read as if its
    target_id were a professional's primary key."""
    pro = build_professional("t@example.com", slug="target-pro")
    LegacyDirectoryMapping.objects.create(
        legacy_kind=LegacyDirectoryMapping.LegacyKind.PROVIDER,
        legacy_identifier="3301",
        target_type=LegacyDirectoryMapping.TargetType.SERVICE_CATEGORY,
        target_id=pro.pk,
        resolution=LegacyDirectoryMapping.Resolution.MAPPED,
    )

    assert APIClient().get(ENDPOINT, {"id": "3301"}).status_code == 404


@pytest.mark.django_db
def test_a_surviving_slug_resolves_without_a_mapping_row():
    build_professional("s@example.com", slug="port-agency")

    # The slug fallback is a genuinely separate branch: no mapping row exists
    # anywhere in the table, so nothing but the slug lookup can answer this.
    assert LegacyDirectoryMapping.objects.count() == 0

    response = APIClient().get(ENDPOINT, {"id": "port-agency"})

    assert response.status_code == 200
    assert response.data["url"] == "/services/professionals/port-agency/"


@pytest.mark.django_db
def test_a_changed_slug_resolves_via_the_mapping_rows_legacy_slug():
    """Spec §14.3 step 4: when a provider's slug changed during migration, the
    mapping row's legacy_slug is what makes the OLD slug redirect
    deterministically — neither the numeric legacy_identifier nor the
    profile's current slug match the old slug directly."""
    pro = build_professional("z@example.com", slug="ocean-legal")
    make_legacy_mapping(
        legacy_identifier="700",
        target=pro,
        legacy_slug="ocean-legal-old",
    )

    response = APIClient().get(ENDPOINT, {"id": "ocean-legal-old"})

    assert response.status_code == 200
    assert response.data["url"] == "/services/professionals/ocean-legal/"


@pytest.mark.django_db
def test_a_mapping_to_a_non_active_profile_does_not_resolve():
    pro = build_professional(
        "x@example.com", slug="suspended-pro", status=ProfessionalProfileStatus.SUSPENDED
    )
    make_legacy_mapping(legacy_identifier="7", target=pro)

    assert APIClient().get(ENDPOINT, {"id": "7"}).status_code == 404


@pytest.mark.django_db
def test_a_surviving_slug_of_a_non_active_profile_does_not_resolve():
    """The status guard has to cover the fallback branch too, not just the
    mapping branch — Task 8's rule is that non-ACTIVE profiles are not public."""
    build_professional(
        "d@example.com", slug="draft-pro", status=ProfessionalProfileStatus.DRAFT
    )

    assert APIClient().get(ENDPOINT, {"id": "draft-pro"}).status_code == 404


@pytest.mark.django_db
def test_an_unknown_id_is_404():
    assert APIClient().get(ENDPOINT, {"id": "does-not-exist"}).status_code == 404


@pytest.mark.django_db
def test_a_missing_or_blank_id_is_400():
    client = APIClient()

    assert client.get(ENDPOINT).status_code == 400
    assert client.get(ENDPOINT, {"id": "   "}).status_code == 400


@pytest.mark.django_db
def test_a_legacy_identifier_is_unique_within_its_kind():
    from django.db import IntegrityError, transaction

    pro = build_professional("u@example.com", slug="unique-pro")
    make_legacy_mapping(legacy_identifier="55", target=pro)

    with pytest.raises(IntegrityError), transaction.atomic():
        make_legacy_mapping(legacy_identifier="55", target=pro)


@pytest.mark.django_db
def test_the_same_legacy_identifier_is_allowed_in_a_different_kind():
    """The constraint is compound — the identifier is unique *within* its kind,
    not globally, so the same number may exist once per legacy record type."""
    pro = build_professional("c@example.com", slug="compound-pro")
    make_legacy_mapping(legacy_identifier="56", target=pro)
    make_legacy_mapping(
        legacy_identifier="56",
        target=pro,
        legacy_kind=LegacyDirectoryMapping.LegacyKind.SERVICE,
    )

    assert LegacyDirectoryMapping.objects.filter(legacy_identifier="56").count() == 2


@pytest.mark.django_db
def test_the_resolver_404s_when_the_rollout_flag_is_off():
    build_professional("f@example.com", slug="flagged-pro")
    disable_combined_directory()

    assert APIClient().get(ENDPOINT, {"id": "flagged-pro"}).status_code == 404
