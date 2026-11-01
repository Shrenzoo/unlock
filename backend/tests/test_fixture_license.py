"""The B02 grant must not silently extend to uploaded or unrelated geometry."""

from unlock_engine.contracts import Provenance
import pytest

from unlock_engine.fixture_license import (
    B02_NOTICE,
    B02_PROVENANCE,
    GALLERY_CODES,
    gallery_provenance,
    license_files,
)


def test_b02_license_requires_the_authorized_source_and_author():
    assert license_files(Provenance(**B02_PROVENANCE))
    for field in ("author", "source", "license"):
        other = dict(B02_PROVENANCE, **{field: "unrelated uploaded geometry"})
        assert license_files(Provenance(**other)) == {}


def test_b02_notice_bytes_are_unchanged_by_the_gallery_grant():
    assert (
        license_files(Provenance(**B02_PROVENANCE))["LICENSE-B02.txt"]
        == B02_NOTICE.encode()
    )


def test_gallery_grant_names_only_its_own_fixture():
    for code in GALLERY_CODES:
        files = license_files(Provenance(**gallery_provenance(code)))
        notice = files[f"LICENSE-{code}.txt"].decode()
        assert set(files) == {f"LICENSE-{code}.txt", "THIRD_PARTY_NOTICES.txt"}
        assert f"original {code}" in notice and "B02" not in notice
        assert "CC BY 4.0" in notice
    for code in ("B01", "B03"):
        with pytest.raises(ValueError, match="no recorded publication grant"):
            gallery_provenance(code)
