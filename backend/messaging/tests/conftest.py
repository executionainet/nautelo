import pytest
from django.contrib.auth.models import Group
from django.core.cache import cache

from accounts.enums import StaffGroup
from messaging.enums import CONTACT_UNLOCK_FLAG, UNIFIED_INQUIRIES_FLAG
from platform_settings.models import FeatureFlag
from platform_settings.services import (
    SETTINGS_CACHE_KEY,
    feature_flag_cache_key,
    set_feature_flag,
)

#: Flags this app's tests toggle. Listed so the autouse fixture below clears
#: their cache entries: platform_settings.services.is_feature_enabled caches a
#: persisted value indefinitely, so a flag flipped in one test would otherwise
#: leak into the next - including `contact_unlock`, which Phase 7's tests turn
#: on one at a time, hence the second entry.
MESSAGING_FEATURE_FLAG_KEYS = [UNIFIED_INQUIRIES_FLAG, CONTACT_UNLOCK_FLAG]

FLAG_TEST_DESCRIPTION = "Spec 35.1 rollout flag for the shared inquiry form."

#: Phase 7's flag ships DISABLED (spec 35.2 step 4) - the opposite of
#: `unified_inquiries`, so this reference row's default is False.
CONTACT_FLAG_TEST_DESCRIPTION = "Spec 35.1 rollout flag for contact reveal."


@pytest.fixture(autouse=True)
def _clear_messaging_caches():
    """Delete this package's OWN cache keys around every test.

    Never clear the whole cache. Django's RedisCache whole-cache clear wipes the entire Redis DB, and this
    project's test Redis DB is shared by concurrently running worktrees - a
    whole-DB flush has already broken parallel suites here once, which is why
    backend/conftest.py was rewritten to scan and delete only its own
    KEY_PREFIX. This fixture is narrower still: the two key shapes this package
    actually writes, exactly as listings/tests/conftest.py and
    platform_settings/tests/conftest.py do.

    Defined FIRST so it runs before _messaging_reference_rows below: pytest
    executes same-scope autouse fixtures in definition order, and the row-seeding
    fixture writes a flag whose cached value must not be a stale one.
    """

    def _clear():
        cache.delete(SETTINGS_CACHE_KEY)
        for key in MESSAGING_FEATURE_FLAG_KEYS:
            cache.delete(feature_flag_cache_key(key))

    _clear()
    yield
    _clear()


@pytest.fixture(autouse=True)
def _messaging_reference_rows(db):
    """Guarantee the reference rows this app's tests assume, instead of trusting
    a migration seed to still be there.

    Two rows are at stake: the `unified_inquiries` FeatureFlag that
    messaging/0002 seeds (disabled in production), and the `staff_moderator`/`staff_admin` Groups
    that accounts/0003 seeds. Both are created by RunPython data migrations, and
    a `@pytest.mark.django_db(transaction=True)` test anywhere in the session
    ends with a `flush`, which truncates every table and re-emits `post_migrate`
    - and `post_migrate` restores content types and permissions, NOT rows a data
    migration inserted. Whether that actually bites depends on collection order
    and on Django/pytest-django internals; this fixture means it cannot bite
    HERE regardless, which is cheaper than being right about the internals.

    In-repo evidence that the concern is real rather than theoretical:
    `brokers/tests/test_admin.py:35` already writes
    `Group.objects.get_or_create(name=StaffGroup.MODERATOR)` where every other
    call site writes `Group.objects.get(...)` - a defensive spelling somebody
    adopted for exactly this class of problem.

    The production seed is DISABLED (spec 35.2), but tests need the feature on,
    so this fixture forces it ENABLED for the test's duration - it does NOT
    verify the seed; test_seed_migration.py exercises the migration itself.
    `update_or_create`, not `get_or_create`: the test's starting state must be
    ENABLED whatever a previous run left behind. The
    `unified_inquiries_disabled` fixture below is requested explicitly, so
    pytest runs it AFTER this autouse one and its `False` wins where a test asks
    for it.
    """
    FeatureFlag.objects.update_or_create(
        key=UNIFIED_INQUIRIES_FLAG,
        defaults={"is_enabled": True, "description": FLAG_TEST_DESCRIPTION},
    )
    # Same reasoning as the row above, and Phase 7 is what makes it
    # load-bearing: this phase adds `@pytest.mark.django_db(transaction=True)`
    # tests, and such a test ends with a `flush` that truncates every table and
    # re-emits `post_migrate` - which restores content types and permissions,
    # NOT rows a RunPython data migration inserted. Without this row,
    # `messaging/0004`'s seed can be gone by the time a later test reads it and
    # `test_the_flag_ships_disabled` fails with DoesNotExist, depending on
    # collection order. `is_enabled=False` is deliberate: it mirrors the SHIPPED
    # state, and the tests that need the reveal open say so through their own
    # `unlock_enabled` fixture, which pytest runs after this autouse one.
    FeatureFlag.objects.update_or_create(
        key=CONTACT_UNLOCK_FLAG,
        defaults={"is_enabled": False, "description": CONTACT_FLAG_TEST_DESCRIPTION},
    )
    for name in StaffGroup.ALL:
        Group.objects.get_or_create(name=name)
    yield


@pytest.fixture
def unified_inquiries_disabled(db):
    """Flip spec 35.1's flag off for one test. Tests run with the flag forced ON by
    the autouse fixture; this one turns it off for the off-case."""
    set_feature_flag(
        key=UNIFIED_INQUIRIES_FLAG,
        is_enabled=False,
        actor=None,
        description="Disabled by a test.",
    )
    yield
