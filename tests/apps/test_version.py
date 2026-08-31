import pytest
from django.test.utils import override_settings
<<<<<<< HEAD
from tests.apps._doubles import RecordingCache
||||||| parent of 672f31b5 (fix(version): cache the upstream SHA instead of the verdict)
=======
>>>>>>> 672f31b5 (fix(version): cache the upstream SHA instead of the verdict)

<<<<<<< HEAD
from coda.apps import version
from coda.apps.version import FAILURE_TTL, FRESH_TTL, has_newer_commit
||||||| parent of 672f31b5 (fix(version): cache the upstream SHA instead of the verdict)
from tests.apps._doubles import InMemoryVersionInfoProvider
from coda.apps.version import (
    check_update,
    get_branch,
    get_commit_sha,
    get_repo,
    get_version_tag,
    has_newer_commit,
)
=======
from tests.apps._doubles import (
    BrokenCache,
    InMemoryVersionInfoProvider,
    RecordingCache,
)
from coda.apps.version import (
    SystemVersionInfoProvider,
    check_update,
    get_branch,
    get_commit_sha,
    get_repo,
    get_version_tag,
    has_newer_commit,
)
>>>>>>> 672f31b5 (fix(version): cache the upstream SHA instead of the verdict)

# --- has_newer_commit --------------------------------------------------------


def test__has_newer_commit__short_sha_matches_full() -> None:
    assert has_newer_commit("8d68c555e344cad5ec94e735b2be766e39f8e389", "8d68c555") is False


def test__has_newer_commit__different_short_sha() -> None:
    assert has_newer_commit("8d68c555e344cad5ec94e735b2be766e39f8e389", "abcdef1") is True


def test__has_newer_commit__tag_does_not_match_sha() -> None:
    assert has_newer_commit("8d68c555e344cad5ec94e735b2be766e39f8e389", "2026.01") is True


<<<<<<< HEAD
# --- check_update: caching contract ------------------------------------------

LATEST_SHA = "8d68c555e344cad5ec94e735b2be766e39f8e389"


class _FetchStub:
    """Stubbed GitHub call. Consecutive calls return the next of *results*,
    the last entry repeating. Records the branches it was asked about."""

    def __init__(self, *results: tuple[str | None, str | None]) -> None:
        self.requested: list[str] = []
        self._results = list(results) or [(LATEST_SHA, None)]

    def __call__(self, branch: str) -> tuple[str | None, str | None]:
        self.requested.append(branch)
        return self._results.pop(0) if len(self._results) > 1 else self._results[0]


@pytest.fixture
def stubbed_cache(monkeypatch: pytest.MonkeyPatch) -> RecordingCache:
    cache = RecordingCache()
    monkeypatch.setattr(version, "cache", cache)
    return cache


def test__check_update__given_nothing_cached__fetches_and_stores_upstream_sha(
    monkeypatch: pytest.MonkeyPatch,
    stubbed_cache: RecordingCache,
) -> None:
    fetch = _FetchStub()
    monkeypatch.setattr(version, "_fetch_latest_commit", fetch)

    result = version.check_update("develop", "abc1234")

    assert result is True
    assert fetch.requested == ["develop"]
    assert stubbed_cache.values[version._sha_key("develop")] == LATEST_SHA
    assert stubbed_cache.timeouts[version._sha_key("develop")] == FRESH_TTL
    assert FRESH_TTL > FAILURE_TTL


def test__check_update__given_branch_with_slash__cache_key_stays_separator_free() -> None:
    """Branch names may contain "/"; a cache key may not."""
    assert "/" not in version._sha_key("feature/my-feature")


def test__check_update__given_cached_sha__skips_fetch_and_recompares_per_commit(
    monkeypatch: pytest.MonkeyPatch,
    stubbed_cache: RecordingCache,
) -> None:
    """The cached value is the upstream SHA, not a verdict: a deploy inside the
    cache window must not inherit the previous commit's answer."""
    stubbed_cache.values[version._sha_key("develop")] = LATEST_SHA
    fetch = _FetchStub()
    monkeypatch.setattr(version, "_fetch_latest_commit", fetch)

    up_to_date = version.check_update("develop", LATEST_SHA[:8])
    behind = version.check_update("develop", "abcdef1")

    assert fetch.requested == []
    assert up_to_date is False
    assert behind is True


def test__check_update__given_failed_fetch__returns_false_and_backs_off(
    monkeypatch: pytest.MonkeyPatch,
    stubbed_cache: RecordingCache,
) -> None:
    """An outage may not be retried on every page view."""
    fetch = _FetchStub((None, "502 Bad Gateway"))
    monkeypatch.setattr(version, "_fetch_latest_commit", fetch)

    result = version.check_update("develop", "abcdef1")

    assert result is False
    assert stubbed_cache.timeouts[version._error_key("develop")] == FAILURE_TTL
    assert version._sha_key("develop") not in stubbed_cache.values

    version.check_update("develop", "abcdef1")
    version.check_update("develop", "abcdef1")
    assert fetch.requested == ["develop"]  # throttled for FAILURE_TTL, not retried


def test__check_update__given_unreachable_cache__fetches_and_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dead cache backend must not 500 the banner; behave like a miss."""

    class BrokenCache:
        def get(self, key: str, default: object = None) -> object:
            raise RuntimeError("cache backend is down")

        def set(self, key: str, value: str, timeout: int | None = None) -> None:
            raise RuntimeError("cache backend is down")

    fetch = _FetchStub()
    monkeypatch.setattr(version, "cache", BrokenCache())
    monkeypatch.setattr(version, "_fetch_latest_commit", fetch)

    assert version.check_update("develop", "abc1234") is True
    assert fetch.requested == ["develop"]


def test__check_update__given_cached_sha_from_previous_failure_window__recovers(
    monkeypatch: pytest.MonkeyPatch,
    stubbed_cache: RecordingCache,
) -> None:
    """After the backoff lapses, a successful fetch is retried and cached."""
    fetch = _FetchStub((None, "502 Bad Gateway"), (LATEST_SHA, None))
    monkeypatch.setattr(version, "_fetch_latest_commit", fetch)
    assert version.check_update("develop", "abcdef1") is False

    del stubbed_cache.values[version._error_key("develop")]  # backoff lapses

    assert version.check_update("develop", "abc1234") is True
    assert fetch.requested == ["develop", "develop"]
    assert stubbed_cache.values[version._sha_key("develop")] == LATEST_SHA


@override_settings(CODA_UPDATE_CHECK=False)
def test__check_update__given_update_check_disabled__skips_cache_and_network(
    monkeypatch: pytest.MonkeyPatch,
    stubbed_cache: RecordingCache,
) -> None:
    fetch = _FetchStub()
    monkeypatch.setattr(version, "_fetch_latest_commit", fetch)

    assert version.check_update("develop", "abc1234") is False
    assert fetch.requested == []
    assert stubbed_cache.values == {}
||||||| parent of 672f31b5 (fix(version): cache the upstream SHA instead of the verdict)
=======
# --- SystemVersionInfoProvider.check_update: caching contract ----------------

LATEST_SHA = "8d68c555e344cad5ec94e735b2be766e39f8e389"


def _system_provider(
    monkeypatch: pytest.MonkeyPatch,
    cache: RecordingCache | BrokenCache,
    *fetch_results: tuple[str | None, str | None],
) -> tuple[SystemVersionInfoProvider, list[str]]:
    """Provider with an injected cache and a stubbed GitHub call.

    Consecutive calls return the next of *fetch_results*, the last entry
    repeating. Returns the provider and the branches the stub was asked about.
    """
    provider = SystemVersionInfoProvider()
    requested: list[str] = []
    results = list(fetch_results) or [(LATEST_SHA, None)]

    def fake_fetch(branch: str) -> tuple[str | None, str | None]:
        requested.append(branch)
        return results.pop(0) if len(results) > 1 else results[0]

    monkeypatch.setattr(provider, "_cache", cache)
    monkeypatch.setattr(provider, "_fetch_latest_commit", fake_fetch)
    return provider, requested


def test__check_update__given_nothing_cached__stores_upstream_sha_fresh_and_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys = SystemVersionInfoProvider
    cache = RecordingCache()
    provider, requested = _system_provider(monkeypatch, cache)

    result = provider.check_update("develop", "abc1234")

    assert requested == ["develop"]
    assert result == {"update_available": True, "latest_commit": LATEST_SHA}
    assert cache.values[keys._fresh_key("develop")] == LATEST_SHA
    assert cache.timeouts[keys._fresh_key("develop")] == keys.FRESH_TTL
    assert cache.timeouts[keys._stale_key("develop")] == keys.STALE_TTL
    # The stale mirror only exists to outlive the fresh entry; equal TTLs make it dead weight.
    assert keys.STALE_TTL > keys.FRESH_TTL > keys.FAILURE_TTL


def test__check_update__given_branch_with_slash__cache_key_stays_separator_free() -> None:
    """Branch names may contain "/"; a cache key may not."""
    assert "/" not in SystemVersionInfoProvider._fresh_key("feature/my-feature")


def test__check_update__given_cached_sha__skips_fetch_and_recompares_per_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cached value is the upstream SHA, not a verdict: a deploy inside the
    cache window must not inherit the previous commit's answer."""
    cache = RecordingCache({SystemVersionInfoProvider._fresh_key("develop"): LATEST_SHA})
    provider, requested = _system_provider(monkeypatch, cache)

    up_to_date = provider.check_update("develop", LATEST_SHA[:8])
    behind = provider.check_update("develop", "abcdef1")

    assert requested == []
    assert up_to_date == {"update_available": False, "latest_commit": LATEST_SHA}
    assert behind == {"update_available": True, "latest_commit": LATEST_SHA}


def test__check_update__given_expired_cache_and_failed_fetch__degrades_and_backs_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One outage may not blank the banner for an hour, nor be retried per view."""
    keys = SystemVersionInfoProvider
    cache = RecordingCache()
    provider, requested = _system_provider(
        monkeypatch, cache, (LATEST_SHA, None), (None, "502 Bad Gateway")
    )
    assert provider.check_update("develop", "abc1234")["update_available"] is True

    del cache.values[keys._fresh_key("develop")]  # its TTL lapses during the outage
    result = provider.check_update("develop", "abcdef1")

    assert result == {
        "update_available": True,  # served from the last known-good SHA
        "latest_commit": LATEST_SHA,
        "error": "502 Bad Gateway",
    }
    assert cache.timeouts[keys._error_key("develop")] == keys.FAILURE_TTL
    assert keys._fresh_key("develop") not in cache.values

    provider.check_update("develop", "abcdef1")
    assert requested == ["develop", "develop"]  # throttled for FAILURE_TTL, not retried


def test__check_update__given_unreachable_cache__still_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, requested = _system_provider(monkeypatch, BrokenCache())

    result = provider.check_update("develop", "abc1234")

    assert requested == ["develop"]
    assert result == {"update_available": True, "latest_commit": LATEST_SHA}


@override_settings(CODA_UPDATE_CHECK=False)
def test__check_update__given_update_check_disabled__skips_cache_and_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = RecordingCache()
    provider, requested = _system_provider(monkeypatch, cache)

    assert provider.check_update("develop", "abc1234") == {"update_available": False}
    assert requested == []
    assert cache.values == {}
>>>>>>> 672f31b5 (fix(version): cache the upstream SHA instead of the verdict)
