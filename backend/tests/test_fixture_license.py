"""The B02 grant must not silently extend to uploaded or unrelated geometry."""

from unlock_engine.contracts import Provenance
import pytest

from unlock_engine.fixture_license import (
    B02_NOTICE,
    B02_PROVENANCE,
    GALLERY_CODES,
    gallery_provenance,
    license_files,
    rights_line,
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
        provenance = Provenance(**gallery_provenance(code))
        files = license_files(provenance)
        notice = files[f"LICENSE-{code}.txt"].decode()
        assert set(files) == {f"LICENSE-{code}.txt", "THIRD_PARTY_NOTICES.txt"}
        assert f"original {code}" in notice and "B02" not in notice
        assert "CC BY 4.0" in notice and "authorized in writing" in notice
        # The public notice states that authorization exists, never its contents.
        assert "@" not in notice and "signature" not in notice.lower()
        assert f"LICENSE-{code}.txt" in rights_line(provenance, None)
    for code in ("B01", "B03"):
        with pytest.raises(ValueError, match="no recorded publication grant"):
            gallery_provenance(code)


def test_ungranted_provenance_keeps_the_pending_rights_wording():
    other = Provenance(**dict(B02_PROVENANCE, license="pending author approval"))
    assert rights_line(other, "pending\n") == "pending\n"
