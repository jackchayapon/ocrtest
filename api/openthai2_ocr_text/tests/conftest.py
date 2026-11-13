import pytest


@pytest.fixture(autouse=True)
def private_test_key(monkeypatch):
    """Existing positive-path cases now use an explicitly configured test secret."""
    monkeypatch.setenv("OPENTHAI_API_KEY", "synthetic-unit-test-key")
