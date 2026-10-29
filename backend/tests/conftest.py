import json

import pytest

from unlock_engine.fixtures import generate_fixture
from unlock_engine.service import construct_candidate, import_revision


@pytest.fixture(scope="session")
def fixture_dirs(tmp_path_factory):
    root = tmp_path_factory.mktemp("cad")
    return {code: generate_fixture(root / code, code) for code in ("B01", "B02", "B03")}


@pytest.fixture(scope="session")
def revision(fixture_dirs):
    p = fixture_dirs["B02"]
    return import_revision(
        p / "assembly.step", json.loads((p / "manifest.json").read_text())
    )


@pytest.fixture(scope="session")
def candidate(revision):
    return construct_candidate(
        revision,
        "bridge",
        "T01",
        dict(center_x_mm=0, center_y_mm=-20, width_mm=40, depth_mm=16),
    )
