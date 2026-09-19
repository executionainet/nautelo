from django.core.cache import cache

from platform_settings.services import feature_flag_cache_key, set_feature_flag
from services_catalog.models import (
    LegacyDirectoryMapping,
    ProfessionalService,
    ServiceCategory,
)
from services_catalog.permissions import COMBINED_DIRECTORY_FLAG


def make_service_category(
    *,
    slug="generic-service",
    name_en="Generic Service",
    display_order=0,
    is_active=True,
    has_seo_page=False,
    **extra,
):
    return ServiceCategory.objects.create(
        slug=slug,
        name_en=name_en,
        display_order=display_order,
        is_active=is_active,
        has_seo_page=has_seo_page,
        **extra,
    )


def make_professional_service(
    professional,
    category,
    *,
    title_en="Vessel registration support",
    is_active=True,
    service_area=None,
    **extra,
):
    return ProfessionalService.objects.create(
        professional=professional,
        category=category,
        title_en=title_en,
        is_active=is_active,
        service_area=["IT-52"] if service_area is None else service_area,
        **extra,
    )


def make_legacy_mapping(
    *,
    legacy_identifier,
    target,
    legacy_kind=None,
    legacy_slug="",
    resolution=None,
    **extra,
):
    return LegacyDirectoryMapping.objects.create(
        legacy_kind=legacy_kind or LegacyDirectoryMapping.LegacyKind.PROVIDER,
        legacy_identifier=legacy_identifier,
        legacy_slug=legacy_slug,
        target_type=LegacyDirectoryMapping.TargetType.PROFESSIONAL_PROFILE,
        target_id=target.pk,
        resolution=resolution or LegacyDirectoryMapping.Resolution.MAPPED,
        **extra,
    )


def _set_combined_directory_flag(is_enabled):
    # set_feature_flag()'s own cache invalidation runs inside
    # transaction.on_commit(), which never fires under pytest-django's default
    # (non-transactional) @pytest.mark.django_db — its callbacks are simply
    # discarded when the test's wrapping atomic block rolls back instead of
    # committing. The explicit cache.delete() below is what actually makes the
    # new value visible to is_feature_enabled() within the same test.
    set_feature_flag(key=COMBINED_DIRECTORY_FLAG, is_enabled=is_enabled, actor=None)
    cache.delete(feature_flag_cache_key(COMBINED_DIRECTORY_FLAG))


def disable_combined_directory():
    _set_combined_directory_flag(False)


def enable_combined_directory():
    _set_combined_directory_flag(True)
