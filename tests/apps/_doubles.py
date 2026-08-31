"""Test doubles for version module tests."""

<<<<<<< HEAD
||||||| parent of 672f31b5 (fix(version): cache the upstream SHA instead of the verdict)
from coda.apps.version import UpdateCheckResult
=======
from coda.apps.version import UpdateCheckResult, VersionInfoProvider
>>>>>>> 672f31b5 (fix(version): cache the upstream SHA instead of the verdict)

class RecordingCache:
    """Cache double that also records the timeout each key was stored with."""

<<<<<<< HEAD
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values: dict[str, str] = dict(values or {})
        self.timeouts: dict[str, int] = {}
||||||| parent of 672f31b5 (fix(version): cache the upstream SHA instead of the verdict)
class InMemoryVersionInfoProvider:
    """In-memory implementation of VersionInfoProvider for testing."""
=======
class InMemoryVersionInfoProvider(VersionInfoProvider):
    """In-memory implementation of VersionInfoProvider for testing."""
>>>>>>> 672f31b5 (fix(version): cache the upstream SHA instead of the verdict)

    def get(self, key: str, default: object = None) -> object:
        return self.values.get(key, default)

<<<<<<< HEAD
    def set(self, key: str, value: str, timeout: int | None = None) -> None:
        self.values[key] = value
        self.timeouts[key] = int(timeout) if timeout is not None else 0
||||||| parent of 672f31b5 (fix(version): cache the upstream SHA instead of the verdict)
    def get_branch(self) -> str:
        return self.branch

    def get_repo(self) -> str:
        return self.repo

    def get_version(self) -> str:
        return self.version

    def get_version_tag(self) -> str | None:
        return self.version_tag

    def get_commit_sha(self) -> str:
        return self.commit_sha

    def check_update(self, branch: str, current_commit: str) -> UpdateCheckResult:
        return self.update_info
=======
    def get_branch(self) -> str:
        return self.branch

    def get_repo(self) -> str:
        return self.repo

    def get_version(self) -> str:
        return self.version

    def get_version_tag(self) -> str | None:
        return self.version_tag

    def get_commit_sha(self) -> str:
        return self.commit_sha

    def check_update(self, branch: str, current_commit: str) -> UpdateCheckResult:
        return self.update_info


class RecordingCache:
    """Cache double that also records the timeout each key was stored with."""

    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values: dict[str, str] = dict(values or {})
        self.timeouts: dict[str, int] = {}

    def get(self, key: str, default: object = None) -> object:
        return self.values.get(key, default)

    def set(self, key: str, value: str, timeout: int | None = None) -> None:
        self.values[key] = value
        self.timeouts[key] = int(timeout) if timeout is not None else 0


class BrokenCache:
    """Cache double that fails the way an unreachable backend does."""

    def get(self, key: str, default: object = None) -> object:
        raise RuntimeError("cache backend is down")

    def set(self, key: str, value: str, timeout: int | None = None) -> None:
        raise RuntimeError("cache backend is down")
>>>>>>> 672f31b5 (fix(version): cache the upstream SHA instead of the verdict)
