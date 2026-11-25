import pytest

from app.core.listing_intel import image_load


@pytest.fixture(autouse=True)
def _fresh_image_memory():
    image_load._MEMORY.clear()
    yield
    image_load._MEMORY.clear()
