import pytest

from solver import event_log


@pytest.fixture(autouse=True)
def unsealed_cases():
    """Tests reuse case ids; a decision logged by one test must not seal the case for the next."""
    event_log._sealed.clear()
    yield
    event_log._sealed.clear()
