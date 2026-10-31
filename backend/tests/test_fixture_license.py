"""The B02 grant must not silently extend to uploaded or unrelated geometry."""

from unlock_engine.contracts import Provenance
from unlock_engine.fixture_license import B02_PROVENANCE, b02_license_files


def test_b02_license_requires_the_authorized_source_and_author():
    assert b02_license_files(Provenance(**B02_PROVENANCE))
    for field in ("author", "source", "license"):
        other = dict(B02_PROVENANCE, **{field: "unrelated uploaded geometry"})
        assert b02_license_files(Provenance(**other)) == {}
