from pathlib import Path

import pytest

MEDIA = Path(__file__).parent / "fixtures" / "media"


@pytest.fixture
def media() -> Path:
    return MEDIA
