import pytest

from app import main


@pytest.fixture(autouse=True)
def fresh_request_counts():
    """Every test starts with a clean per-minute request count."""
    main.recent.clear()
    yield
    main.recent.clear()
