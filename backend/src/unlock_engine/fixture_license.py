"""Publication terms for the specifically authorized original B02 demonstration."""

B02_PROVENANCE = dict(
    author="UNLOCK team (Shreyas Pabbathi and his brother)",
    license="CC-BY-4.0",
    source=(
        "https://github.com/Shrenzoo/unlock; "
        "unlock_engine.fixtures.generate_fixture(B02, held_out=False); deterministic seed 0"
    ),
)

B02_NOTICE = """UNLOCK original B02 synthetic CAD demonstration
Copyright 2026 the UNLOCK team (Shreyas Pabbathi and his brother).

The team's original B02 geometry and its generated demonstration assets,
including original/revised STEP geometry, previews, manifests, paths and
engineering evidence, are licensed under Creative Commons Attribution 4.0
International (CC BY 4.0): https://creativecommons.org/licenses/by/4.0/
Legal terms: https://creativecommons.org/licenses/by/4.0/legalcode
Source: https://github.com/Shrenzoo/unlock

Attribute the UNLOCK team, retain the license link, and identify modifications.
The revised assembly and changed bracket are adaptations of the original B02.
See template_parameters.json and geometry_difference.json for the actual changes.
No endorsement, physical safety, fitness or manufacturing approval is implied.

This grant covers the team's original B02 demonstration assets, not application
source code, third-party software, trademarks, other fixtures or private CAD.
Third-party software retains its own terms; see THIRD_PARTY_NOTICES.txt.
"""

DEPENDENCY_NOTICE = """B02 generation software notices
The geometry is an original synthetic construction, not a third-party CAD model.
No dependency source or executable is included in this engineering export.

Generated with CadQuery 2.6.1 (Apache-2.0):
https://github.com/CadQuery/cadquery/blob/2.6.1/LICENSE
CadQuery's copyright and license notices remain in the installed distribution.

Generated with cadquery-ocp 7.8.1.1.post1 and Open CASCADE Technology 7.8.1:
https://github.com/CadQuery/OCP
https://dev.opencascade.org/resources/licensing
Their own license notices remain in the installed distributions. The CC BY 4.0
grant for B02 does not relicense these libraries or their dependencies.
"""


GALLERY_CODES = ("B04", "B05", "B06", "B07", "B08")

# Written contributor authorization recorded 2026-10-31; the records are private.
GALLERY_NOTICE = """UNLOCK original {code} synthetic CAD demonstration
Copyright 2026 the UNLOCK team (Shreyas Pabbathi and his brother).

The team's original {code} geometry and its generated demonstration assets,
including original STEP geometry, previews, manifests, paths, engineering
evidence and, where a verified redesign exists, revised STEP geometry, are
licensed under Creative Commons Attribution 4.0 International (CC BY 4.0):
https://creativecommons.org/licenses/by/4.0/
Legal terms: https://creativecommons.org/licenses/by/4.0/legalcode
Source: https://github.com/Shrenzoo/unlock
Public release under this license was authorized in writing by the
fixture's contributors. The geometry was authored with AI assistance.

Attribute the UNLOCK team, retain the license link, and identify modifications.
Any revised assembly and changed bracket are adaptations of the original {code}.
See template_parameters.json and geometry_difference.json for the actual changes.
No endorsement, physical safety, fitness or manufacturing approval is implied.

This grant covers the team's original {code} demonstration assets, not application
source code, third-party software, trademarks, other fixtures or private CAD.
Third-party software retains its own terms; see THIRD_PARTY_NOTICES.txt.
"""


def gallery_provenance(code):
    """B04–B08: the team's CC BY 4.0 grant, under written contributor authorization."""
    if code not in GALLERY_CODES:
        raise ValueError(f"{code} has no recorded publication grant")
    return dict(
        B02_PROVENANCE,
        source=(
            "https://github.com/Shrenzoo/unlock; "
            f"unlock_engine.fixtures.generate_fixture({code}); deterministic seed 0"
        ),
    )


GRANTS = {"B02": B02_PROVENANCE} | {c: gallery_provenance(c) for c in GALLERY_CODES}


def granted_code(provenance):
    """The fixture whose exact recorded grant this provenance carries, if any."""
    return next((c for c, p in GRANTS.items() if provenance.model_dump() == p), None)


def license_files(provenance):
    """Never apply the team's grant to uploaded CAD or other fixture sources."""
    code = granted_code(provenance)
    if code is None:
        return {}
    notice = B02_NOTICE if code == "B02" else GALLERY_NOTICE.format(code=code)
    return {
        f"LICENSE-{code}.txt": notice.encode(),
        "THIRD_PARTY_NOTICES.txt": DEPENDENCY_NOTICE.replace("B02", code).encode(),
    }


def rights_line(provenance, pending):
    """Export limitation text: the actual grant, or the caller's pending wording."""
    code = granted_code(provenance)
    if code is None:
        return pending
    return f"Fixture geometry and evidence: CC BY 4.0; see LICENSE-{code}.txt and attribution.txt.\n"
