import re
import uuid
from pathlib import Path

import redis
from django.conf import settings
from django.core.cache import cache

from conftest import clear_own_cache_keys


def test_cache_keys_are_namespaced_per_checkout():
    assert settings.CACHES["default"]["KEY_PREFIX"].startswith("test_")


def test_clearing_own_cache_leaves_other_checkouts_keys_alone():
    """Concurrent pytest runs from other worktrees share one Redis DB; flushing the
    whole DB (Django's RedisCache.clear()) would delete their throttle/flag keys."""
    foreign = redis.Redis.from_url(settings.CACHES["default"]["LOCATION"])
    # Unique per run: two worktrees running this very test concurrently must not share
    # (and delete) each other's probe.
    probe = f"test_someotherworktree_{uuid.uuid4().hex}:1:probe"
    foreign.set(probe, "x", ex=60)
    cache.set("mine", 1, timeout=60)
    try:
        clear_own_cache_keys()
        assert cache.get("mine") is None
        assert foreign.get(probe) == b"x"
    finally:
        foreign.delete(probe)


def test_no_test_flushes_the_shared_redis_db():
    """cache.clear() on RedisCache is a FLUSHDB: any test calling it wipes every other
    concurrently running worktree's keys. Tests must use clear_own_cache_keys()."""
    backend_root = Path(__file__).resolve().parents[2]
    pattern = re.compile(r"cache\.clear\(|flushdb|flushall", re.IGNORECASE)
    offenders = [
        str(path.relative_to(backend_root))
        for path in list(backend_root.rglob("test_*.py")) + list(backend_root.rglob("conftest.py"))
        if ".venv" not in path.parts
        and path != Path(__file__).resolve()
        and pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
