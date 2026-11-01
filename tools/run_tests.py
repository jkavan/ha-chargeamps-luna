"""Run tests on Linux or Windows without emulating Unix process management.

The upstream HA test plugin imports the Linux executable runner. Integration
tests never launch it. On Windows, allow its fcntl/resource imports, but fail
immediately if a test actually tries to use Unix locking or resource limits.
Production integration modules and Home Assistant fixtures are not replaced.
"""

import sys
from pathlib import Path
from types import ModuleType


def unsupported(*args, **kwargs):
    raise RuntimeError("Unix process management cannot run in the Windows test harness")


if sys.platform == "win32":
    for name, constants, methods in (
        ("fcntl", {"LOCK_EX": 2, "LOCK_NB": 4}, ("flock",)),
        ("resource", {"RLIMIT_NOFILE": 7}, ("getrlimit", "setrlimit")),
    ):
        module = ModuleType(name)
        for key, value in constants.items():
            setattr(module, key, value)
        for method in methods:
            setattr(module, method, unsupported)
        sys.modules[name] = module

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

if sys.platform == "win32":
    import pytest_socket

    def restrict_to_loopback(*args, **kwargs):
        # Windows asyncio uses an INET socketpair instead of a Unix socketpair.
        pytest_socket.enable_socket()
        pytest_socket.socket_allow_hosts(["127.0.0.1", "::1"])

    pytest_socket.disable_socket = restrict_to_loopback

raise SystemExit(pytest.main(sys.argv[1:]))
