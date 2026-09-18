import pytest
from django.conf import settings
from django.core.cache import cache


def clear_own_cache_keys():
    """Delete only the cache keys under this checkout's KEY_PREFIX.

    Django's RedisCache whole-cache clear wipes the entire Redis DB, which would also delete keys owned by
    other worktrees' concurrently running test suites sharing the same Redis DB.
    """
    prefix = settings.CACHES["default"]["KEY_PREFIX"]
    client = cache._cache.get_client(write=True)
    keys = list(client.scan_iter(match=f"{prefix}:*", count=500))
    if keys:
        client.delete(*keys)


@pytest.fixture(autouse=True)
def clear_redis_cache():
    """Isolate cache-backed state (DRF throttles) between tests.

    This clears only keys under the per-checkout KEY_PREFIX set in
    config/settings/test.py (never a whole-DB flush). This fixture - not a settings
    override - is how cache isolation is achieved, because config/settings/test.py
    must keep the real Redis CACHES backend (spec 34.2).
    """
    clear_own_cache_keys()
    yield
    clear_own_cache_keys()


@pytest.fixture
def published_listing_with_snapshot(db):
    """A PUBLISHED listing with one READY photo and a live public snapshot.

    Defined here, at the repo test root, because it is used from BOTH
    listings/tests/ and entitlements/tests/ — a conftest fixture is only visible
    inside its own directory subtree.

    Mirrors listings/tests/test_public_read_api.py's `_published()` helper, which
    stays where it is (it returns a tuple and takes snapshot kwargs that its own
    module needs). Returns the listing alone; the snapshot is
    `listing.current_public_snapshot`.

    NOTE for consumers: this owner already has a brand, named after its own pk by
    `make_private_listing`. `BoatBrand.normalized_name` is unique, so a test that
    builds a SECOND listing for `listing.owner_user` must pass an explicit
    `brand=make_brand(...)`.
    """
    from uuid import uuid4

    from django.utils import timezone

    from accounts.enums import UserRole
    from accounts.tests.factories import make_user
    from listings.enums import ListingStatus, MediaStatus, MediaType
    from listings.tests.factories import make_media, make_private_listing, make_snapshot

    suffix = uuid4().hex[:8]
    owner = make_user(
        f"published-owner-{suffix}@example.com",
        role=UserRole.PRIVATE_SELLER,
        verified=True,
    )
    moderator = make_user(
        f"published-moderator-{suffix}@example.com",
        role=UserRole.STAFF,
        verified=True,
    )
    listing = make_private_listing(owner=owner, status=ListingStatus.PUBLISHED)
    image = make_media(listing, media_type=MediaType.IMAGE, status=MediaStatus.READY)
    snapshot = make_snapshot(
        listing,
        approved_by=moderator,
        media_manifest=[
            {
                "media_id": str(image.pk),
                "media_type": image.media_type,
                "storage_key": image.storage_key,
                "mime_type": image.mime_type,
                "sort_order": image.sort_order,
                "width": image.width,
                "height": image.height,
                "duration_seconds": image.duration_seconds,
                "checksum_sha256": image.checksum_sha256,
            }
        ],
    )
    listing.current_public_snapshot = snapshot
    listing.published_at = timezone.now()
    listing.save(update_fields=["current_public_snapshot", "published_at"])
    return listing
