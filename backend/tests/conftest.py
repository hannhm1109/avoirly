import json
from pathlib import Path

import pytest

from recovery.models import DocumentExtractionResult


@pytest.fixture
def pair_dict():
    path = Path(__file__).resolve().parents[2] / "samples" / "pair.json"
    return json.loads(path.read_text(encoding="utf-8"))["extraction"]


@pytest.fixture
def pair(pair_dict):
    return DocumentExtractionResult.model_validate(pair_dict)
